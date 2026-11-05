# Local testing: eng-harness

No host program is involved. These checks need the owner's machine (plan 0001 section 4; completed by T16 and T19):
1. The overhead benchmark and the fsync cost on the owner's workstation disk, with antivirus active, against the 20 ms target.
2. The run lock is released after killing the engine from Task Manager (`uv run pytest tests/unit/test_journal_reader.py tests/windows/test_run_lock_windows.py -m windows`; the second file starts a holder process, kills it, and checks that the engine's lock refuses a second process while a run is under way; the Windows job runs only `tests/windows`, so also run `tests/replay/test_resume.py::test_resume_holds_the_run_lock` there: the same for `Engine.resume`).
3. A resume after a forced power-off of a virtual machine (power loss is not covered by tests).
4. File-copy promotion onto a folder the engineer uses, including a target file open in another program.

Plan 0002 (servers and adapters; spec 0002 section 12). Nothing here runs in CI:
1. `csi_launch` on the owner's machine: which process is the ETABS parent, the pid the reply names, and that the instance survives the server job's closure.
2. A second server (`long` role) attaching by pid to a server-launched instance.
3. The live `tools/list` fingerprint against the allowlist's.
4. The `serverInfo` the Sasaah server reports.
5. Every table key and reply field of spec 0002 sections 4.6.2 and 4.6.4, and the reply fields of every mapped list tool.
6. A server `timeout` during a write and during an analysis, the units afterwards, each reconciliation rule, `locked` after a completed analysis, and a proof-of-end mechanism for an abandoned analysis call; after a `timeout` on a role, re-attachment with `launched: false`, `csi_exit` refused, and what `csi_status` reports.
7. Fingerprint stability and the blind spots of the read set.
8. `close_started` closing a hidden launched instance and leaving a visible one.
9. The host-instance lock across two engine processes.
10. `dxf-prep/prepare` and `etabs-model/build` through the adapter, including the configuration rewrite and the build-artifact hash.
11. `eng-harness doctor` on the owner's machine, including the integrity level and installed products.
12. Record mode on a copy, and the owner's review of the recordings before commit.
13. `uv run pytest tests/windows` on the owner's machine, with the antivirus and endpoint tools it runs: Job Object nesting under the engineer's terminal or scheduler, and the breakaway case with a real server and host program (none of the tests in `tests/windows` that start real processes has ever run on Windows: the container CI is Linux only and runs only the fake-based ones; the owner runs the whole folder, `uv run pytest tests/windows -m windows`, including the breakaway case (a host program started by a server survives the server's job) and the engine-kill case (every member of a server's job ends when the engine is killed), before relying on the launcher).
14. `ProcessTransport` and `ServerManager` over the Windows launcher with the real Sasaah server: the MCP handshake on the launcher's pipes (raw handle-backed files, read and written by worker threads), a complete uncached `tools/list`, a call that outlasts the client backstop, a server killed during a call (read and write codes, restart, re-attach by pid), and a shutdown that ends the server on end-of-file of its standard input without ending a running host program (only the Linux fakes have run it).

Plan 0004 (templates and basis; completed by T9). Nothing here runs in CI:
1. The owner fills a values file and uses the spec 0006 approval page on a real template.
2. The owner writes a template by hand in the user folder on Windows and checks the path, the encoding and the line endings.

Plan 0006 T3b (spec 0006 AC61): the opener on the owner machine.
15. `eng_harness.cli._opener.open_address` opens the launch address in the default browser on Windows (`os.startfile`), macOS and Linux with `BROWSER` set to a capture program (it must not run), and `write_to_terminal` reaches the controlling terminal (`CONOUT$`, `/dev/tty`); with no terminal it returns False and nothing is printed on stdout or stderr.
