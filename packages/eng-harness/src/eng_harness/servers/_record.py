"""Record mode: the transport wrapper, the sanitizer and the manifest (plan 0002 T17; spec 0002 4.8.1, AC33).

`RecordMode` hands every request and its reply to a `Recording`, which at the end of the session writes
`<seq>-<tool>.json` files, sanitized, and a `manifest.json` of SHA-256 hashes; reads of `Project Information` are
dropped and the name mapping stays in the run folder. Free text cannot be sanitized mechanically: the owner reviews
a recording before committing it. Units: none. Errors: `verify_manifest` returns the problems it finds.
"""

import getpass
import hashlib
import json
import posixpath
import re
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from importlib.metadata import version
from pathlib import Path
from typing import Any, NamedTuple

import anyio
from mcp import types
from mcp.shared.message import SessionMessage
from pydantic import JsonValue

from eng_harness.servers._buildcheck import tool_list_fingerprint
from eng_harness.servers._transport import TransportStreams

__all__ = ["MANIFEST", "NAMES_FILE", "RecordMode", "Recording", "Sanitizer", "verify_manifest"]

MANIFEST = "manifest.json"
NAMES_FILE = "recording-names.json"  # in the run folder: original names to placeholders, never in the recording
# File types of the products' models (CSI .edb/.e2k, .fdb/.f2k, .sdb/.s2k; Revit .rvt) get `<model-N>`;
# any other file `<file-N>`.
_MODEL = ("edb", "e2k", "fdb", "f2k", "sdb", "s2k", "rvt")
_EXTENSIONS = (*_MODEL, "dxf", "dwg", "pdf", "xlsx", "xls", "csv", "ifc")  # file names recognized in free text
_PROJECT_INFORMATION = "projectinformation"
# A value that is one absolute path: spaces are allowed in the folders, and in the name when it ends in an extension.
_WHOLE = re.compile(r"(?:[A-Za-z]:[\\/]|/)(?:[^\r\n\"<>|*?\\/]+[\\/])*(?:[^\s\"<>|*?\\/]+|[^\r\n\"<>|*?\\/]+\.\w{1,5})")
_PATH = re.compile(  # an absolute path inside text: spaces only in the folders of a drive path
    r"(?<![\w.$)\]>])(?:[A-Za-z]:[\\/](?:[^\\/:*?\"<>|\r\n]+[\\/])*|/(?:[\w$.()\-]+/)*)[\w$()\-.]+"
)
_FILE = re.compile(
    rf"(?<![\w<>$])[\w$()\-.]*[\w$()\-]\.(?:{'|'.join(_EXTENSIONS)})(?![\w$])", re.IGNORECASE
)  # a bare file name with a known extension


def _slash(path: str) -> str:
    return path.replace("\\", "/").rstrip("/")


class Sanitizer:
    """Replaces what identifies a person or a project; placeholders are numbered by first appearance.

    A path inside `run_dir` becomes `<run>/<relative>`, any other absolute path `<path>/<name>`, the home folder
    `<home>`, the user name `<user>`. A model or file name (the last component of a path, or a bare name with a known
    extension) becomes `<model-N>` or `<file-N>` and keeps its extension; the same base name is the same placeholder
    wherever it appears, also without its extension. Sanitizing a sanitized value changes nothing.
    """

    def __init__(self, run_dir: Path | str, *, user: str, home: str) -> None:
        """`run_dir` is the run folder; `user` and `home` are the names to remove."""
        self._run, self._home = _slash(str(run_dir)), _slash(home)
        self._users = re.compile(rf"(?<![\w<])({re.escape(user)})(?![\w>])", re.IGNORECASE) if user else None
        self._index: dict[str, str] = {}  # base name (case folded) -> placeholder
        self.names: dict[str, str] = {}  # original file name -> placeholder name: for the run folder, not the recording

    def _name(self, part: str) -> str:
        stem, suffix = posixpath.splitext(part)
        kind = "model" if suffix[1:].casefold() in _MODEL else "file"
        holder = self._index.setdefault(stem.casefold(), f"<{kind}-{len(self._index) + 1}>")
        self.names[part] = holder + suffix
        return holder + suffix

    def _path(self, raw: str) -> str:
        core = raw.rstrip(".)")
        tail, path = raw[len(core) :], _slash(core)
        low = path.casefold()
        if low == self._home.casefold():
            return "<home>" + tail
        if low == self._run.casefold():
            return "<run>" + tail
        if low.startswith(self._run.casefold() + "/"):
            *folders, last = path[len(self._run) + 1 :].split("/")
            return "/".join(["<run>", *folders, self._name(last)]) + tail
        return f"<path>/{self._name(path.rsplit('/', 1)[-1])}{tail}"

    def text(self, value: str) -> str:
        """The text with paths, file names and the user replaced."""
        if _WHOLE.fullmatch(value):
            return self._path(value)
        value = _FILE.sub(lambda m: self._name(m.group(0)), _PATH.sub(lambda m: self._path(m.group(0)), value))
        if self._index:  # a base name quoted without its extension
            bases = "|".join(re.escape(b) for b in sorted(self._index, key=len, reverse=True))
            pattern = re.compile(rf"(?<![\w<$-])({bases})(?![\w>$-])", re.IGNORECASE)
            value = pattern.sub(lambda m: self._index[m.group(1).casefold()], value)
        return value if self._users is None else self._users.sub("<user>", value)

    def value(self, value: JsonValue) -> JsonValue:
        """`value` with every string sanitized (the keys are not)."""
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, list):
            return [self.value(item) for item in value]
        return {key: self.value(item) for key, item in value.items()} if isinstance(value, dict) else value


class _Raw(NamedTuple):
    method: str
    params: dict[str, Any] | None
    result: dict[str, Any] | None
    error: dict[str, Any] | None


class Recording:
    """The exchanges of one session, written to `directory` by `finish` (sanitized, with the manifest)."""

    def __init__(
        self, directory: Path, run_dir: Path, *, adapter: str, build: str,
        tool_names: frozenset[str] | None = None, user: str | None = None, home: str | None = None,
    ) -> None:  # fmt: skip
        """`tool_names` selects the tools of the fingerprint; `user` and `home` default to the environment's."""
        self._directory, self._run_dir, self._adapter, self._build = directory, run_dir, adapter, build
        self._tool_names = tool_names
        self._user = getpass.getuser() if user is None else user
        self._home = str(Path.home()) if home is None else home
        self._raw: list[_Raw] = []

    def add(
        self, method: str, params: dict[str, Any] | None, *, result: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
    ) -> None:  # fmt: skip
        """Note one request with its `result` or `error`; a `Project Information` read is dropped."""
        arguments = (params or {}).get("arguments")
        table = arguments.get("table") if isinstance(arguments, dict) else None
        if not (isinstance(table, str) and re.sub(r"[\s_-]+", "", table).casefold() == _PROJECT_INFORMATION):
            self._raw.append(_Raw(method, params, result, error))

    def _clean(self, sanitizer: Sanitizer, raw: _Raw, seq: int) -> dict[str, Any]:
        """One recorded file; the tool list is the server's own metadata and stays exact (its fingerprint is used)."""
        params = raw.params or {}
        tool = params.get("name") if raw.method == "tools/call" else None
        keep = raw.method == "tools/list"
        request = {k: v if keep or k == "name" else sanitizer.value(v) for k, v in params.items()}
        data: dict[str, Any] = {
            "seq": seq, "method": raw.method, "tool": tool if isinstance(tool, str) else raw.method.replace("/", "-"),
            "request": request,
        }  # fmt: skip
        if raw.error is not None:
            data["error"] = sanitizer.value(raw.error)
        elif raw.result is not None:
            data["reply"] = raw.result if keep else self._reply(sanitizer, raw.result)
        return data

    @staticmethod
    def _reply(sanitizer: Sanitizer, result: dict[str, Any]) -> dict[str, Any]:
        """A result with its text blocks sanitized as JSON when they are JSON (backslashes are then real ones)."""

        def block(item: Any) -> Any:
            if not (isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str)):
                return sanitizer.value(item)
            try:
                shown = json.dumps(sanitizer.value(json.loads(item["text"])), sort_keys=True, ensure_ascii=False)
            except ValueError:
                shown = sanitizer.text(item["text"])
            return {**item, "text": shown}

        return {k: [block(b) for b in v] if k == "content" else sanitizer.value(v) for k, v in result.items()}

    def _fingerprint(self) -> str | None:
        listed: dict[str, Any] = {}
        for raw in self._raw:
            for tool in (raw.result or {}).get("tools", []) if raw.method == "tools/list" else []:
                if self._tool_names is None or tool["name"] in self._tool_names:
                    listed[tool["name"]] = tool["inputSchema"]
        return tool_list_fingerprint(listed) if listed else None

    def finish(self) -> Path:
        """Write the files and the manifest; the name mapping goes to the run folder. Returns the manifest path."""
        sanitizer = Sanitizer(self._run_dir, user=self._user, home=self._home)
        for number, raw in enumerate(self._raw, 1):  # a first pass registers every name, so that an earlier quote of
            self._clean(sanitizer, raw, number)  # a name that appears later in the session is replaced as well
        self._directory.mkdir(parents=True, exist_ok=True)
        files: dict[str, str] = {}
        for number, raw in enumerate(self._raw, 1):
            data = self._clean(sanitizer, raw, number)
            name = f"{number:03d}-{data['tool']}.json"
            content = (json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
            (self._directory / name).write_bytes(content)
            files[name] = hashlib.sha256(content).hexdigest()
        manifest = {
            "adapter": self._adapter, "build": self._build, "harness_version": version("eng-harness"),
            "tool_fingerprint": self._fingerprint(), "files": files,
        }  # fmt: skip
        path = self._directory / MANIFEST
        path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (self._run_dir / NAMES_FILE).write_text(json.dumps(sanitizer.names, indent=2) + "\n", encoding="utf-8")
        return path


def verify_manifest(directory: Path) -> list[str]:
    """The problems of a recording folder: an unreadable manifest, a file that is missing, changed or not listed."""
    try:
        manifest = json.loads((directory / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return [f"{MANIFEST}: {error}"]
    files = manifest.get("files") if isinstance(manifest, dict) else None
    if not isinstance(files, dict):
        return [f"{MANIFEST}: no object with files"]
    problems: list[str] = []
    for name, digest in files.items():
        try:
            actual = hashlib.sha256((directory / name).read_bytes()).hexdigest()
        except OSError:
            problems.append(f"{name}: missing")
            continue
        if actual != digest:
            problems.append(f"{name}: SHA-256 differs")
    problems += [f"{p.name}: not in the manifest" for p in sorted(directory.glob("[0-9]*.json")) if p.name not in files]
    return problems


class RecordMode(AbstractAsyncContextManager[TransportStreams]):
    """The transport of a session, with every request and its reply handed to `recording` on the way.

    Messages pass unchanged. Leaving the context ends the inner transport and then writes the recording.
    """

    def __init__(self, inner: AbstractAsyncContextManager[TransportStreams], recording: Recording) -> None:
        """Wrap `inner` (a `ProcessTransport` in a live run)."""
        self._inner, self._recording = inner, recording
        self._pending: dict[str | int, tuple[str, dict[str, Any] | None]] = {}
        self._context = self._open()

    async def __aenter__(self) -> TransportStreams:
        return await self._context.__aenter__()

    async def __aexit__(self, *exc: Any) -> None:
        await self._context.__aexit__(*exc)

    def _note(self, message: SessionMessage | Exception) -> None:
        """Pair a reply with the request it answers."""
        body = message.message if isinstance(message, SessionMessage) else None
        if not isinstance(body, types.JSONRPCResponse | types.JSONRPCError) or body.id not in self._pending:
            return
        method, params = self._pending.pop(body.id)
        if isinstance(body, types.JSONRPCResponse):
            self._recording.add(method, params, result=body.result)
        else:
            self._recording.add(method, params, error=body.error.model_dump(mode="json", exclude_none=True))

    @asynccontextmanager
    async def _open(self) -> AsyncIterator[TransportStreams]:
        to_client_send, to_client = anyio.create_memory_object_stream[SessionMessage | Exception](0)
        to_server, from_client = anyio.create_memory_object_stream[SessionMessage](0)

        async def replies(read: Any) -> None:
            async with to_client_send:
                async for message in read:
                    self._note(message)
                    await to_client_send.send(message)

        async def requests(write: Any) -> None:
            async with write:  # closing it ends the server's input, as the SDK does
                async for message in from_client:
                    if isinstance(request := message.message, types.JSONRPCRequest):
                        self._pending[request.id] = (request.method, request.params)
                    await write.send(message)

        try:
            async with self._inner as (read, write), anyio.create_task_group() as group:
                group.start_soon(replies, read)
                group.start_soon(requests, write)
                try:
                    yield to_client, to_server
                finally:
                    await to_server.aclose()
                    group.cancel_scope.cancel()
        finally:
            self._recording.finish()
