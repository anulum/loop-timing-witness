# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — source documentation and native API website

"""Render publishable Markdown and language-native API documentation for Pages.

Only Git-publishable documents and assets enter the site. Python's own pydoc
renders the installed package; Doxygen and Rustdoc output must already exist.
Missing native documentation refuses the build instead of silently dropping a
maintained language. The website carries the actual source revision and hashes.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import importlib
import json
import os
import pkgutil
import pydoc
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit, urlunsplit

from markdown_it import MarkdownIt

from check_documentation import NOT_SLUG_CHARACTER, audit
from repository_files import candidate_files

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "https://github.com/anulum/loop-timing-witness"
ASSET_SUFFIXES = frozenset({".webp", ".png", ".svg", ".pdf", ".jpg"})


class DocumentationRefusedError(ValueError):
    """A deliberately authored refusal of incomplete documentation input."""


STYLE = """:root{color-scheme:light dark;
--bg:#fafbfc;
--fg:#172b40;
--muted:#526778;
--line:#dbe3eb;
--link:#12669d}
@media(prefers-color-scheme:dark){:root{--bg:#0b1520;
--fg:#d9e6ef;
--muted:#96acbd;
--line:#263b4c;
--link:#7ecdec}}
*{box-sizing:border-box}
body{margin:0;
background:var(--bg);
color:var(--fg);
font:17px/1.7 system-ui,sans-serif}
header{border-bottom:1px solid var(--line);
padding:1rem max(1rem,calc((100vw - 1050px)/2));
display:flex;
gap:1rem;
flex-wrap:wrap}
header a{font-size:.9rem;
white-space:nowrap}
main{max-width:1050px;
margin:auto;
padding:2rem 1.5rem 5rem}
a{color:var(--link);
text-decoration:none}
a:hover{text-decoration:underline}
h1,h2,h3{line-height:1.3}
h1{font-size:2.3rem}
h2{margin-top:2.3rem;
border-bottom:1px solid var(--line);
padding-bottom:.5rem}
img{max-width:100%;
height:auto;
border-radius:12px}
table{border-collapse:collapse;
display:block;
overflow-x:auto}
th,td{border:1px solid var(--line);
padding:.5rem .8rem;
text-align:left}
pre{border:1px solid var(--line);
border-radius:8px;
padding:1.2rem;
overflow:auto;
font-size:.86rem;
line-height:1.6}
code{font-size:.9em}
header img{vertical-align:middle;
border-radius:0}
.brand-logos{display:flex;
flex-wrap:wrap;
gap:1rem;
align-items:center;
margin-bottom:1rem}
.brand-logos img{max-height:64px;
width:auto;
border-radius:0}
footer{color:var(--muted);
border-top:1px solid var(--line);
margin-top:3rem;
padding-top:1rem;
font-size:.8rem}
"""


def destination(relative: str) -> Path:
    """Map a repository Markdown path to its website page.

    Parameters
    ----------
    relative
        Publishable repository-relative Markdown path.

    Returns
    -------
    Path
        Website-relative HTML path; the root README is the landing page.
    """
    return Path("index.html") if relative == "README.md" else Path(relative).with_suffix(".html")


def rewrite_link(target: str, source: Path, documents: set[str]) -> str:
    """Keep fragments and assets while resolving source links to rendered pages.

    Parameters
    ----------
    target
        Original Markdown link or image URL.
    source
        Repository-relative source document.
    documents
        Exact publishable Markdown inventory.

    Returns
    -------
    str
        Website-relative page URL or canonical source URL.
    """
    for prefix in (
        REPOSITORY + "/blob/main/",
        "https://raw.githubusercontent.com/anulum/loop-timing-witness/main/",
    ):
        if target.startswith(prefix):
            target = target.removeprefix(prefix)
            source = Path("README.md")
            break
    parts = urlsplit(target)
    if parts.scheme or parts.netloc or not parts.path:
        return target
    resolved = (ROOT / source.parent / unquote(parts.path)).resolve().relative_to(ROOT).as_posix()
    if resolved in documents:
        page = destination(resolved)
        path = os.path.relpath(page, destination(source.as_posix()).parent)
        return urlunsplit(("", "", path, parts.query, parts.fragment))
    if Path(resolved).suffix in ASSET_SUFFIXES:
        return target
    return urlunsplit(
        (
            "https",
            "github.com",
            "/anulum/loop-timing-witness/"
            + ("tree" if (ROOT / resolved).is_dir() else "blob")
            + "/main/"
            + resolved,
            parts.query,
            parts.fragment,
        )
    )


def write_page(output: Path, relative: Path, title: str, content: str, revision: str) -> None:
    """Write a self-contained page with navigation and source provenance.

    Parameters
    ----------
    output
        Exclusive website directory.
    relative
        Page path inside that directory.
    title
        Plain text page title.
    content
        Rendered repository content or escaped native API text.
    revision
        Actual repository commit SHA.
    """
    prefix = os.path.relpath(Path(), relative.parent)
    links = {
        "Overview": "index.html",
        "Host analysis": "docs/HOST_ANALYSIS.html",
        "AMP simulation": "docs/AMP_SIMULATION.html",
        "Validation": "VALIDATION.html",
        "Python API": "api/python/loop_timing_witness.html",
        "Rust API": "api/rust/witness_controller/index.html",
        "C/C++ API": "api/c/index.html",
    }
    navigation = " ".join(f'<a href="{prefix}/{url}">{label}</a>' for label, url in links.items())
    brand = (
        f'<a href="{prefix}/index.html" aria-label="Loop Timing Witness overview">'
        f'<img src="{prefix}/docs/assets/anulum_logo.png" alt="Anulum" width="32" height="32"></a>'
    )
    logos = (
        '<div class="brand-logos">'
        f'<img src="{prefix}/docs/assets/anulum_logo_company.jpg" alt="Anulum">'
        f'<img src="{prefix}/docs/assets/fortis_studio_logo.jpg" alt="Fortis Studio"></div>'
    )
    page = output / relative
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{html.escape(title)} — Loop Timing Witness</title><style>{STYLE}</style>"
        f"</head><body><header>{brand} {navigation}</header><main>{content}"
        f'<footer>{logos}Source: <a href="{REPOSITORY}/tree/{revision}">{revision[:12]}</a>. '
        "Simulation software and planned hardware instrument; no board qualification is claimed."
        "</footer></main></body></html>\n",
        encoding="utf-8",
    )


def render_document(
    name: str, documents: set[str], renderer: MarkdownIt, output: Path, revision: str
) -> None:
    """Render a publishable document with stable heading anchors and resolved links.

    Parameters
    ----------
    name
        Repository-relative Markdown source path.
    documents
        Exact publishable Markdown inventory.
    renderer
        Configured CommonMark renderer.
    output
        Exclusive website directory.
    revision
        Actual source commit SHA.
    """
    source = Path(name)
    tokens = renderer.parse((ROOT / source).read_text(encoding="utf-8"))
    counts: dict[str, int] = {}
    for index, token in enumerate(tokens):
        if token.type == "heading_open":
            heading = tokens[index + 1].content.replace("`", "")
            base = NOT_SLUG_CHARACTER.sub("", heading.lower()).replace(" ", "-")
            seen = counts.get(base, 0)
            token.attrSet("id", base if seen == 0 else f"{base}-{seen}")
            counts[base] = seen + 1
        for child in token.children or []:
            for attribute in ("href", "src"):
                target = child.attrGet(attribute)
                if target is not None:
                    child.attrSet(attribute, rewrite_link(str(target), source, documents))
    rendered = renderer.renderer.render(tokens, renderer.options, {})
    write_page(output, destination(name), source.stem, rendered, revision)


def build(output: Path) -> None:
    """Build all public documents and actual package/native API references.

    Parameters
    ----------
    output
        New exclusive output directory; existing paths are refused.

    Raises
    ------
    DocumentationRefusedError
        If source links are invalid or a required native reference is missing.
    OSError
        If output creation or a source read fails.
    """
    native = ROOT / "build/native-api"
    findings = audit(ROOT)
    if findings:
        message = "invalid source documentation; run tools/check_documentation.py"
        raise DocumentationRefusedError(message)
    required = [
        native / "c/html/index.html",
        native / "rust/doc/witness_controller/index.html",
        native / "rust/doc/witness_amp_rust_kernel/index.html",
    ]
    if not all(path.is_file() for path in required):
        message = "required C/C++ and both Rust API references are missing; run make native-api"
        raise DocumentationRefusedError(message)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    output.mkdir(parents=True, exist_ok=False)
    paths = candidate_files(ROOT)
    documents = {name for name in paths if name.endswith(".md")}
    renderer = MarkdownIt("commonmark", {"html": True}).enable(["table", "strikethrough"])
    for name in sorted(documents):
        render_document(name, documents, renderer, output, revision)
    for name in paths:
        if Path(name).suffix in ASSET_SUFFIXES:
            asset = output / name
            asset.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, asset)
    package = importlib.import_module("loop_timing_witness")
    modules = [
        package.__name__,
        *(item.name for item in pkgutil.walk_packages(package.__path__, package.__name__ + ".")),
    ]
    for name in modules:
        module = importlib.import_module(name)
        reference = html.escape(pydoc.plain(pydoc.render_doc(module)))
        content = f"<h1>{html.escape(name)}</h1><pre>{reference}</pre>"
        write_page(output, Path("api/python") / (name + ".html"), name, content, revision)
    shutil.copytree(native / "c/html", output / "api/c")
    shutil.copytree(native / "rust/doc", output / "api/rust")
    (output / ".nojekyll").write_text("", encoding="utf-8")
    manifest = {
        "source_revision": revision,
        "documents": sorted(documents),
        "python_api_modules": modules,
        "native_api": ["c", "witness_controller", "witness_amp_rust_kernel"],
        "files": {
            str(path.relative_to(output)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(output.rglob("*"))
            if path.is_file()
        },
    }
    (output / "site-provenance.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


def main(argv: list[str] | None = None) -> int:
    """Build the website through its public command line and fail on missing input.

    Parameters
    ----------
    argv
        Explicit arguments or the process arguments.

    Returns
    -------
    int
        Zero on a complete build, one on an input, native-tool or output failure.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="new website directory")
    args = parser.parse_args(argv)
    try:
        build(args.output)
    except DocumentationRefusedError as error:
        print(f"documentation-site: FAIL: {error}", file=sys.stderr)
        return 1
    except (OSError, ValueError, subprocess.CalledProcessError):
        print("documentation-site: FAIL: could not read inputs or create output", file=sys.stderr)
        return 1
    print(f"documentation-site: PASS: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
