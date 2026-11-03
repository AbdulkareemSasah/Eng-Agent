# AGENTS.md: Eng-Agent Design Hub

This repository holds architecture, decisions and process. It contains no product code. Read
[README.md](README.md), then the documents relevant to your task.

## Rules for working here

1. **Documents only.** Never add product code, scripts or generated vendor material to this hub.
2. **Decisions go through ADRs.** A change to architecture is a new ADR in `docs/adr/` (from
   [process/templates/adr.md](process/templates/adr.md)) plus edits to the affected documents in the same change.
   Accepted ADRs are never edited except for their status; a new ADR supersedes them.
3. **Status changes belong to the owner.** Only the owner moves a document or ADR from `Proposed` to `Accepted`.
4. **Keep documents consistent.** When you change one document, search the hub for every reference to what you
   changed (principle numbers P1 to P12, ADR numbers, tool names, error codes, phase numbers) and update them.
5. **Keep it precise and short.** State decisions, contracts and rules. Do not duplicate the same rule in two places;
   link to the single source instead (the per-repository `AGENTS.md` template is the one deliberate copy).
6. **No private data.** No client names, project data, credentials or personal paths, so the hub can be published
   later.
7. **Process changes propagate.** A change in `process/` lists, in its pull request, every repository whose
   `AGENTS.md` must be regenerated.
8. The agent operating rules in [process/08-agent-operating-rules.md](process/08-agent-operating-rules.md) apply here
   too.
