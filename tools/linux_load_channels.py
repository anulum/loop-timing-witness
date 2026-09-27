# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — explicitly owned worker control and readiness pipes

"""Own real pipe descriptors separately from the subprocess process handles."""

from __future__ import annotations

import os
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, BinaryIO

if TYPE_CHECKING:
    from collections.abc import Iterator


@dataclass
class _Descriptor:
    """Close an exclusively owned descriptor once, including early endpoint release.

    Parameters
    ----------
    number
        Actual raw descriptor number, exclusively owned by this resource object.
    closed
        Whether the descriptor was already released, preventing reuse-related closure.
    """

    number: int
    closed: bool = False

    def close(self) -> None:
        """Release this actual descriptor without closing a reused descriptor number."""
        if not self.closed:
            os.close(self.number)
            self.closed = True


@dataclass(frozen=True)
class WorkerChannels:
    """Real worker pipe streams whose descriptors belong to the enclosing context.

    Parameters
    ----------
    child_input
        Read end supplied as worker stdin.
    child_output
        Write end supplied as worker stdout.
    readiness
        Parent read end for worker readiness.
    control
        Parent write end whose closure stops the worker.
    _input_descriptor
        Owned child-input descriptor for early parent-copy release.
    _output_descriptor
        Owned child-output descriptor for early parent-copy release.
    _control_descriptor
        Owned parent control descriptor for prompt EOF delivery.
    """

    child_input: BinaryIO
    child_output: BinaryIO
    readiness: BinaryIO
    control: BinaryIO
    _input_descriptor: _Descriptor
    _output_descriptor: _Descriptor
    _control_descriptor: _Descriptor

    def release_child_ends(self) -> None:
        """Close the parent's child-end copies after successful process creation."""
        self.child_input.close()
        self._input_descriptor.close()
        self.child_output.close()
        self._output_descriptor.close()

    def stop(self) -> None:
        """Close the actual parent writer so the worker observes control-pipe EOF."""
        self.control.close()
        self._control_descriptor.close()


def _open_pipe(resources: ExitStack) -> tuple[BinaryIO, BinaryIO, _Descriptor, _Descriptor]:
    """Register both raw descriptors before allocating their buffered streams.

    Parameters
    ----------
    resources
        Owning stack that closes buffered wrappers and the separately held raw endpoints.

    Returns
    -------
    tuple
        Actual read stream, write stream and their two idempotent descriptor owners.
    """
    read_fd, write_fd = os.pipe()
    reader, writer = _Descriptor(read_fd), _Descriptor(write_fd)
    resources.callback(reader.close)
    resources.callback(writer.close)
    read_stream = resources.enter_context(os.fdopen(read_fd, "rb", closefd=False))
    write_stream = resources.enter_context(os.fdopen(write_fd, "wb", closefd=False))
    return read_stream, write_stream, reader, writer


@contextmanager
def worker_channels() -> Iterator[WorkerChannels]:
    """Allocate four owned endpoints and close all streams/descriptors on exit.

    Yields
    ------
    WorkerChannels
        Actual nonoptional binary streams for one exclusively owned worker.

    Raises
    ------
    OSError
        If actual pipe or stream allocation fails.
    """
    with ExitStack() as resources:
        child_input, control, input_descriptor, control_descriptor = _open_pipe(resources)
        readiness, child_output, _, output_descriptor = _open_pipe(resources)
        yield WorkerChannels(
            child_input,
            child_output,
            readiness,
            control,
            input_descriptor,
            output_descriptor,
            control_descriptor,
        )
