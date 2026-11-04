"""MCP transport over a launched server process (plan 0002 T5; spec 0002 section 4.3.3).

Not the SDK's `stdio_client`, which spawns the process itself and, on Windows, assigns its own job after the spawn
(spec section 11 C3): this speaks newline-delimited JSON-RPC over the pipes of a process the harness launched.
"""

import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from types import TracebackType
from typing import IO

import anyio
import anyio.to_thread
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from mcp import types
from mcp.shared.message import SessionMessage

from eng_harness.servers._launcher import LaunchedProcess

logger = logging.getLogger(__name__)

TransportStreams = tuple[MemoryObjectReceiveStream[SessionMessage | Exception], MemoryObjectSendStream[SessionMessage]]

_READ_CHUNK = 65536  # bytes per read of a raw (unbuffered) pipe; a software setting
_REAP_S = 5.0  # seconds to wait for the leader to be reaped after the job was ended; a software setting


def _write_all(pipe: IO[bytes], data: bytes) -> None:
    """Write all of `data` to a raw pipe, which may accept fewer bytes than offered; raises `OSError` when broken."""
    view = memoryview(data)
    while view:
        written = pipe.write(view)
        view = view[written or 0 :]


def _parse(line: bytes) -> SessionMessage | Exception:
    """Parse one stdout line; a bad line is passed on as a value for the session to surface, as the SDK does."""
    try:
        return SessionMessage(types.jsonrpc_message_adapter.validate_json(line, by_name=False))
    except ValueError as error:
        return error


class ProcessTransport(AbstractAsyncContextManager[TransportStreams]):
    """The SDK's `Transport` over the pipes of `launched`; it also stops the process when it is left.

    Worker threads (through `anyio.to_thread`) read standard output and write standard input. End-of-file or a broken
    pipe closes the read stream, which the session sees as the connection ending. Leaving the context closes standard
    input (a server ends on end-of-file), waits `grace_s` seconds, then ends the job; host programs the server started
    in their own session or job are not touched.
    """

    def __init__(self, launched: LaunchedProcess, *, grace_s: float) -> None:
        """Wrap `launched`; `grace_s` is the server's `shutdown_grace_s` (unit: s)."""
        self._launched, self._grace_s = launched, grace_s
        self._context = self._open()

    async def __aenter__(self) -> TransportStreams:
        return await self._context.__aenter__()

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        await self._context.__aexit__(exc_type, exc, tb)

    @asynccontextmanager
    async def _open(self) -> AsyncIterator[TransportStreams]:
        launched = self._launched
        read_send, read_recv = anyio.create_memory_object_stream[SessionMessage | Exception](0)
        write_send, write_recv = anyio.create_memory_object_stream[SessionMessage](0)

        async def reader() -> None:
            buffer = b""
            async with read_send:
                while chunk := await anyio.to_thread.run_sync(
                    launched.stdout.read, _READ_CHUNK, abandon_on_cancel=True
                ):
                    *lines, buffer = (buffer + chunk).split(b"\n")
                    for line in lines:
                        try:
                            await read_send.send(_parse(line))
                        except anyio.ClosedResourceError, anyio.BrokenResourceError:
                            return  # the session is gone

        async def writer() -> None:
            try:
                async with write_recv:
                    async for message in write_recv:
                        line = message.message.model_dump_json(by_alias=True, exclude_unset=True) + "\n"
                        await anyio.to_thread.run_sync(_write_all, launched.stdin, line.encode())
            except OSError as error:  # the process is gone: end the session instead of leaving requests waiting
                logger.warning("cannot write to server pid %d: %s", launched.pid, error)
                await read_send.aclose()
            finally:
                with contextlib.suppress(OSError):  # closing standard input is what ends a cooperative server
                    launched.stdin.close()

        try:
            async with anyio.create_task_group() as group:
                group.start_soon(reader)
                group.start_soon(writer)
                try:
                    yield read_recv, write_send
                finally:
                    with anyio.CancelScope(shield=True):
                        await write_send.aclose()  # the writer drains, then closes standard input
                        await anyio.to_thread.run_sync(launched.wait, self._grace_s)
                        launched.terminate_job()  # always: also ends descendants that stayed in the job
                        await anyio.to_thread.run_sync(launched.wait, _REAP_S)
                    group.cancel_scope.cancel()
        finally:
            launched.close()
