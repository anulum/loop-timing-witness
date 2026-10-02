# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual metrics HTTP, TLS, file and CLI boundaries

"""Exercise the public importer and real owned HTTP/TLS transports without syscall substitutes."""

from __future__ import annotations

import json
import os
import ssl
import subprocess
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import TYPE_CHECKING

import pytest
from pypi_downloads import MAX_BYTES, PACKAGE, main, snapshot

from conftest import REPOSITORY_ROOT

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


def response() -> dict[str, object]:
    """Supply explicit imported observations; these are never published as provider measurements."""
    return {
        "package": PACKAGE,
        "type": "overall_downloads",
        "data": [
            {"category": "with_mirrors", "date": "2001-01-02", "downloads": 7},
            {"category": "without_mirrors", "date": "2001-01-02", "downloads": 3},
            {"category": "with_mirrors", "date": "2001-01-01", "downloads": 0},
        ],
    }


@contextmanager
def endpoint(
    body: bytes,
    status: int = 200,
    content_type: str = "application/json",
    context: ssl.SSLContext | None = None,
) -> Iterator[str]:
    """Serve actual HTTP responses from an owned loopback socket for the public fetch command."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            """Serve declared observations, refusal status or a real closed socket."""
            if status == 0:
                self.close_connection = True
                return
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = HTTPServer(("127.0.0.1", 0), Handler)
    if context is not None:
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"{'https' if context else 'http'}://localhost:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


def command(
    tmp_path: Path, *arguments: str, environment: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Launch the real tool from the supplied working directory with explicit child arguments."""
    return subprocess.run(
        [
            str(REPOSITORY_ROOT / ".venv/bin/python"),
            str(REPOSITORY_ROOT / "tools/pypi_downloads.py"),
            *arguments,
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )


def test_public_import_upsert_and_sparse_history(tmp_path: Path) -> None:
    """Retain sparse dates, order observations and update actual files idempotently."""
    path = tmp_path / "history.csv"
    body = json.dumps(response()).encode()
    assert snapshot(body, path) == 2
    expected = b"date,without_mirrors,with_mirrors\r\n2001-01-01,,0\r\n2001-01-02,3,7\r\n"
    assert path.read_bytes() == expected
    assert snapshot(body, path) == 2
    assert path.read_bytes() == expected
    source = tmp_path / "response.json"
    source.write_bytes(body)
    assert main(["--response", str(source), "--csv", str(path)]) == 0
    assert not list(tmp_path.glob(".history.csv.*"))


def test_first_observation_after_header_only_history(tmp_path: Path) -> None:
    """Populate the actual unavailable-data initial history without inventing earlier dates."""
    path = tmp_path / "history.csv"
    path.write_text("date,without_mirrors,with_mirrors\n")
    assert snapshot(json.dumps(response()).encode(), path) == 2
    assert path.read_text().splitlines() == [
        "date,without_mirrors,with_mirrors",
        "2001-01-01,,0",
        "2001-01-02,3,7",
    ]


@pytest.mark.parametrize(
    "body",
    [
        b"null",
        b"[]",
        b"{}",
        b'{"package":"a","package":"b"}',
        b"{",
        b"\xff",
        json.dumps({**response(), "package": "other"}).encode(),
        json.dumps({**response(), "type": "other"}).encode(),
        json.dumps({**response(), "data": None}).encode(),
        json.dumps({**response(), "data": []}).encode(),
        json.dumps({**response(), "data": [None]}).encode(),
        json.dumps({**response(), "data": [{}]}).encode(),
        b" " * (MAX_BYTES + 1),
    ],
    ids=lambda body: f"payload-{len(body)}",
)
def test_response_envelope_refusal(tmp_path: Path, body: bytes) -> None:
    """Reject untrusted identity/schema/JSON before modifying any actual history."""
    path = tmp_path / "history.csv"
    snapshot(json.dumps(response()).encode(), path)
    before = path.read_bytes()
    source = tmp_path / "response.json"
    source.write_bytes(body)
    result = command(tmp_path, "--response", str(source), "--csv", str(path))
    assert result.returncode == 1
    assert result.stderr.startswith("downloads:")
    assert path.read_bytes() == before
    assert not list(tmp_path.glob(".history.csv.*"))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("category", None),
        ("category", "unknown"),
        ("date", None),
        ("date", "bad"),
        ("date", "20010102"),
        ("date", "9999-01-01"),
        ("downloads", True),
        ("downloads", -1),
        ("downloads", 2**63),
        ("downloads", 1.5),
    ],
)
def test_observation_refusal(tmp_path: Path, field: str, value: object) -> None:
    """Refuse each malformed public observation without creating a CSV."""
    row: dict[str, object] = {"category": "with_mirrors", "date": "2001-01-02", "downloads": 7}
    row[field] = value
    source = tmp_path / "response.json"
    source.write_text(json.dumps({**response(), "data": [row]}))
    path = tmp_path / "history.csv"
    assert command(tmp_path, "--response", str(source), "--csv", str(path)).returncode == 1
    assert not path.exists()


@pytest.mark.parametrize(
    "records",
    [
        [{"category": "without_mirrors", "date": "2001-01-02", "downloads": 1}],
        [{"category": "with_mirrors", "date": "2001-01-02", "downloads": 1}] * 2,
        [
            {"category": "with_mirrors", "date": "2001-01-02", "downloads": 1},
            {"category": "without_mirrors", "date": "2001-01-02", "downloads": 2},
        ],
    ],
)
def test_observation_pair_refusal(tmp_path: Path, records: list[dict[str, object]]) -> None:
    """Require unique date/category pairs and valid mirror ordering at the public import surface."""
    with pytest.raises(ValueError, match=r"duplicate|mirror counts"):
        snapshot(json.dumps({**response(), "data": records}).encode(), tmp_path / "history.csv")


@pytest.mark.parametrize(
    "csv",
    [
        "",
        "bad\n",
        "date,without_mirrors,with_mirrors\n2001-01-02,1,2,3\n",
        "date,without_mirrors,with_mirrors\n2001-01-02,1\n",
        "date,without_mirrors,with_mirrors\n2001-01-02,01,2\n",
        "date,without_mirrors,with_mirrors\n2001-01-02,bad,2\n",
        "date,without_mirrors,with_mirrors\n2001-01-02,1,2\n2001-01-02,1,2\n",
    ],
)
def test_retained_history_refusal(tmp_path: Path, csv: str) -> None:
    """Keep actual malformed retained history byte-identical on refusal."""
    path = tmp_path / "history.csv"
    path.write_text(csv)
    with pytest.raises(ValueError, match=r"invalid|noncanonical|duplicate|missing"):
        snapshot(json.dumps(response()).encode(), path)
    assert path.read_text() == csv


def test_target_custody_and_actual_write_failure(tmp_path: Path) -> None:
    """Reject a real symlink and clean a temporary file after an actual permission failure."""
    body = json.dumps(response()).encode()
    original = tmp_path / "original.csv"
    snapshot(body, original)
    link = tmp_path / "link.csv"
    link.symlink_to(original)
    with pytest.raises(ValueError, match="symlink"):
        snapshot(body, link)
    before = original.read_bytes()
    tmp_path.chmod(0o500)
    try:
        with pytest.raises(PermissionError):
            snapshot(body, original)
    finally:
        tmp_path.chmod(0o700)
    assert original.read_bytes() == before


@pytest.mark.parametrize("status", [200, 404, 429, 500, 503, 403, 600, 0])
def test_real_http_status_and_unknown_data(tmp_path: Path, status: int) -> None:
    """Exercise actual network response/absence/closure and preserve missing counts."""
    with endpoint(json.dumps(response()).encode(), status) as url:
        result = command(tmp_path, "--url", url, "--allow-missing", "--project-csv-only")
    csv_path = tmp_path / "downloads/loop-timing-witness.csv"
    if status == 200:
        assert result.returncode == 0
        assert json.loads(result.stdout) == {"status": "updated", "observation_dates": 2}
        assert "2001-01-02,3,7" in csv_path.read_text()
    elif status in {404, 429, 500, 503}:
        assert result.returncode == 0
        assert json.loads(result.stdout) == {"status": "unavailable", "observation_dates": 0}
        assert csv_path.read_text() == "date,without_mirrors,with_mirrors\n"
    else:
        assert result.returncode == 1
        assert not csv_path.exists()


def test_missing_data_preserves_history_and_requires_explicit_permission(tmp_path: Path) -> None:
    """Unavailable data never rewrites established counts or silently succeeds in strict mode."""
    path = tmp_path / "history.csv"
    snapshot(json.dumps(response()).encode(), path)
    before = path.read_bytes(), path.stat().st_mtime_ns
    with endpoint(b"", 404) as url:
        assert command(tmp_path, "--url", url, "--csv", str(path)).returncode == 1
        assert (
            command(tmp_path, "--url", url, "--csv", str(path), "--allow-missing").returncode == 0
        )
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


@pytest.mark.parametrize(
    ("body", "content_type"),
    [(b"{}", "text/html"), (b" " * (MAX_BYTES + 1), "application/json")],
    ids=["content-type", "size-limit"],
)
def test_actual_http_payload_boundaries(tmp_path: Path, body: bytes, content_type: str) -> None:
    """Refuse real content-type and size failures before CSV creation."""
    with endpoint(body, content_type=content_type) as url:
        result = command(tmp_path, "--url", url + "/overall?mirrors=true")
    assert result.returncode == 1
    assert not (tmp_path / "downloads").exists()


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/hosts",
        "http://",
        "http://user@localhost/",
        "http://localhost/#fragment",
        "http://localhost/\n",
        "http://localhost:invalid/",
    ],
)
def test_public_source_url_refusal(tmp_path: Path, url: str) -> None:
    """Reject unsupported, credentialed or malformed explicit network endpoints."""
    assert command(tmp_path, "--url", url).returncode == 1
    assert not (tmp_path / "downloads").exists()


def test_project_csv_boundary(tmp_path: Path) -> None:
    """The workflow-only flag cannot select another target path."""
    assert command(tmp_path, "--project-csv-only", "--csv", "other.csv").returncode == 1
    assert not (tmp_path / "other.csv").exists()


def test_real_verified_tls_fetch(tmp_path: Path) -> None:
    """Refuse a real legacy handshake and verify the public command's authenticated TLS."""
    certificate, key = tmp_path / "certificate.pem", tmp_path / "key.pem"
    result = subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-subj",
            "/CN=localhost",
            "-addext",
            "subjectAltName=DNS:localhost",
            "-keyout",
            str(key),
            "-out",
            str(certificate),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    assert result.returncode == 0
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certificate, key)
    environment = {**os.environ, "SSL_CERT_FILE": str(certificate)}
    with endpoint(json.dumps(response()).encode(), context=context) as url:
        legacy = subprocess.run(
            [
                "openssl",
                "s_client",
                "-connect",
                url.removeprefix("https://"),
                "-tls1_1",
                "-cipher",
                "DEFAULT:@SECLEVEL=0",
            ],
            input="",
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        assert legacy.returncode != 0
        assert "alert protocol version" in legacy.stderr.lower()
        actual = command(tmp_path, "--url", url, environment=environment)
    assert actual.returncode == 0, actual.stderr
    assert json.loads(actual.stdout) == {"status": "updated", "observation_dates": 2}
