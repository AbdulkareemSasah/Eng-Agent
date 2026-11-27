# Contributing

1. Read [AGENTS.md](AGENTS.md) and the process documents in [design/process](design/process/README.md).
2. Work from a task: a `B-NNN` entry in [BUILD-STATUS.md](BUILD-STATUS.md).
3. Write a spec and a plan first ([lifecycle](design/process/01-lifecycle.md)); in bootstrap mode they are files with
   `status: draft`, reviewed by someone who did not write them.
4. Tests first: the first commit of a task holds the failing tests ([testing](design/process/05-testing-and-verification.md)).
5. Use uv only. Run the local gate (`uv run eng-gate check`, once it exists) before pushing.
6. Use Conventional Commits; agent-written commits carry an `Assisted-by:` trailer.
7. Open a pull request into `build/v1` (bootstrap mode, ADR-0028), not `main`. Use the template and name
   `Work-Item: B-NNN`.
8. Never merge or approve your own work ([review and merge](design/process/06-review-and-merge.md)).
9. Engineering numbers need a cited source; engineering content stays draft until the owner approves it.
