# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — native stream validation handshake and actual I/O failures

"""Exercise native protocol refusals and real operating-system stream boundaries."""

from __future__ import annotations

import os
import selectors
import subprocess
from pathlib import Path

import pytest
from test_controller_parity import DEFAULT


@pytest.mark.parametrize(
    "row",
    [
        "+",
        "-",
        "0",
        "1,2",
        "no-number",
        "999999999999999999999",
        "4294967296",
        "-2147483649",
        "2147483648,0,0,0,0,0,0,-1,1,-1,1",
        "-1,0,0,0,0,0,0,-1,1,-1,1",
        "0,-1,0,0,0,0,0,-1,1,-1,1",
        "0,0,-1,0,0,0,0,-1,1,-1,1",
        "0,0,16777217,0,0,0,0,-1,1,-1,1",
        "0,0,0,-1,0,0,0,-1,1,-1,1",
        "0,0,0,0,0,0,0,1,2,-1,1",
        "0,0,0,0,0,0,0,-2,-1,-1,1",
        "0,0,0,0,0,0,0,-1,1,1,2",
        "0,0,0,0,0,0,0,-1,1,-2,-1",
        "0,0,0,0,0,0,0,1,0,-1,1",
        "0,0,0,0,0,0,0,-1,1,1,0",
    ],
)
def test_native_coefficient_refusal(row: str, native_controllers: tuple[Path, Path]) -> None:
    """Reject malformed coefficients and every nonadmissible bound/gain.

    Parameters
    ----------
    row
        Invalid coefficient row.
    native_controllers
        Public native programs.
    """
    for program in native_controllers:
        result = subprocess.run(
            [str(program), "pid"],
            input=row + "\n0,0,0,0\n",
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 1
        assert result.stdout == ""


def test_commands_arrive_before_input_eof(native_controllers: tuple[Path, Path]) -> None:
    """Prove that each real public program responds while its input remains open.

    Parameters
    ----------
    native_controllers
        Public native programs.
    """
    configuration = ",".join(map(str, DEFAULT)) + "\n"
    for program in native_controllers:
        with subprocess.Popen(
            [str(program), "pid"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ) as process:
            assert process.stdin is not None
            assert process.stdout is not None
            try:
                process.stdin.write(configuration + "0,16777216,0,0\n")
                process.stdin.flush()
                with selectors.DefaultSelector() as selector:
                    selector.register(process.stdout, selectors.EVENT_READ)
                    assert selector.select(timeout=5), "command buffered until EOF"
                assert process.stdout.readline() == "0,33571209,16777,0,0,0\n"
            finally:
                process.stdin.close()
            assert process.wait(timeout=5) == 0


def test_output_failure_is_refused(native_controllers: tuple[Path, Path]) -> None:
    """A real full output device must not turn a failed command write into success.

    Parameters
    ----------
    native_controllers
        Public native programs.
    """
    payload = ",".join(map(str, DEFAULT)) + "\n0,0,0,0\n"
    for program in native_controllers:
        with Path("/dev/full").open("wb") as output:
            result = subprocess.run(
                [str(program), "pid"],
                input=payload,
                text=True,
                stdout=output,
                stderr=subprocess.PIPE,
                check=False,
            )
        assert result.returncode == 1


def test_input_read_failure_after_configuration(native_controllers: tuple[Path, Path]) -> None:
    """Use a real nonblocking pipe to refuse an I/O failure after valid setup.

    Parameters
    ----------
    native_controllers
        Public native programs.
    """
    for program in native_controllers:
        read_fd, write_fd = os.pipe()
        try:
            os.write(write_fd, (",".join(map(str, DEFAULT)) + "\n").encode())
            os.set_blocking(read_fd, False)
            result = subprocess.run(
                [str(program), "pid"], stdin=read_fd, capture_output=True, check=False
            )
            assert result.returncode == 1
            assert result.stdout == b""
        finally:
            os.close(read_fd)
            os.close(write_fd)


@pytest.mark.parametrize(
    "payload",
    [
        b"\xff\n",
        (",".join(map(str, DEFAULT)) + "\n").encode() + b"\xff\n",
        (",".join(map(str, DEFAULT))).encode() + b"\0junk\n",
        (",".join(map(str, DEFAULT)) + "\n").encode() + b"0,0,0,0\0junk\n",
        b"0" * 1024 + b"\n",
        (",".join(map(str, DEFAULT)) + "\n").encode() + b"0" * 1024 + b"\n",
    ],
)
def test_corrupt_text_is_refused(payload: bytes, native_controllers: tuple[Path, Path]) -> None:
    """Unreadable input text fails in both implementations.

    Parameters
    ----------
    payload
        Invalid encoded or malformed input bytes.
    native_controllers
        Public native programs.
    """
    for program in native_controllers:
        result = subprocess.run(
            [str(program), "pid"], input=payload, capture_output=True, check=False
        )
        assert result.returncode == 1


@pytest.mark.parametrize("arguments", [[], ["bad"], ["pid", "extra"]])
def test_invalid_command_line(arguments: list[str], native_controllers: tuple[Path, Path]) -> None:
    """Refuse a missing, unknown or surplus controller selector.

    Parameters
    ----------
    arguments
        Invalid public argument vector.
    native_controllers
        Actual native programs.
    """
    for program in native_controllers:
        result = subprocess.run(
            [str(program), *arguments], input="", capture_output=True, text=True, check=False
        )
        assert result.returncode == 1
        assert "usage:" in result.stderr


@pytest.mark.parametrize("ending", ["\n", "\r\n", ""])
def test_decimal_sign_and_line_endings(ending: str, native_controllers: tuple[Path, Path]) -> None:
    """Accept positive signs, LF/CRLF and an EOF-terminated final sample.

    Parameters
    ----------
    ending
        LF, CRLF or final EOF protocol terminator.
    native_controllers
        Actual native streaming entry points.
    """
    configuration = ",".join(f"{value:+d}" for value in DEFAULT)
    payload = configuration + "\n" + "+0,+16777216,+0,+0" + ending
    for program in native_controllers:
        result = subprocess.run(
            [str(program), "pid"], input=payload, capture_output=True, text=True, check=False
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout == "0,33571209,16777,0,0,0\n"


def test_missing_configuration(native_controllers: tuple[Path, Path]) -> None:
    """Refuse an empty stream before issuing a command.

    Parameters
    ----------
    native_controllers
        Actual native streaming entry points.
    """
    for program in native_controllers:
        result = subprocess.run(
            [str(program), "pid"], input="", capture_output=True, text=True, check=False
        )
        assert result.returncode == 1
        assert result.stdout == ""


@pytest.mark.parametrize("ending", ["\r\n", ""])
def test_reset_record_terminators(ending: str, native_controllers: tuple[Path, Path]) -> None:
    """Recognize CRLF and EOF reset records without treating them as samples.

    Parameters
    ----------
    ending
        CRLF or final EOF terminator.
    native_controllers
        Actual native streaming entry points.
    """
    payload = ",".join(map(str, DEFAULT)) + "\n0,16777216,0,0\nreset" + ending
    for program in native_controllers:
        result = subprocess.run(
            [str(program), "pid"], input=payload, capture_output=True, text=True, check=False
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout == "0,33571209,16777,0,0,0\n"


def test_long_valid_decimal_record(native_controllers: tuple[Path, Path]) -> None:
    """Accept a complete valid record even when decimal zero has many digits.

    Parameters
    ----------
    native_controllers
        Actual native streaming entry points.
    """
    payload = ",".join(map(str, DEFAULT)) + "\n" + "0" * 2048 + ",16777216,0,0\n"
    for program in native_controllers:
        result = subprocess.run(
            [str(program), "pid"], input=payload, capture_output=True, text=True, check=False
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout == "0,33571209,16777,0,0,0\n"
