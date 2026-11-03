# 07. Release and Open Source

## 1. Versions

- Semantic versioning ([17-versioning](../docs/architecture/17-versioning-and-compatibility.md)). During `0.x`, a
  breaking change bumps the minor version and is flagged `BREAKING` in the changelog. `1.0.0` is released when the
  package becomes public and its API is considered stable.
- The version is set with `uv version --bump <major|minor|patch>` in the package directory.

## 2. Releases during incubation

- Packages in the `eng-platform` workspace depend on each other as workspace members and are released separately with
  tags `<package>-vX.Y.Z`. Nothing is published to a package index while private.
- A release of a package lists, in its changelog, the versions of the workspace packages it was tested with.

## 3. Release steps

1. Open a release issue from [templates/release-checklist.md](templates/release-checklist.md).
2. Confirm every item for the release is done (Definition of Done).
3. If host-facing code changed since the last release: the owner runs the live acceptance scripts on every host version
   in `SUPPORT.md`; the scripts write and commit their records ([05](05-testing-and-verification.md) §6). The release
   workflow blocks without them.
4. Generate the changelog section from Conventional Commits (`uvx git-cliff`), then edit it for readers: what changed,
   who is affected, what to do. Code-pack and calc releases list every `check_id` or calc whose output changed.
5. Open a pull request `release: <package> vX.Y.Z` with the version bump and the changelog; normal review applies.
6. After merge, tag the merge commit; the owner approves the release (G4).
7. CI builds from the tag (`uv build`; C# add-ins on a Windows runner), generates the software bill of materials, and
   attaches artifacts to the GitHub release. Public packages are published to PyPI with trusted publishing
   (`uv publish`).
8. Update `SUPPORT.md` and the hub's catalog if supported versions changed.

Patch releases follow the same steps from `main`. There are no long-lived release branches.

## 4. Going public: split and checklist

A package becomes a public repository only when every item passes and the owner approves:

- [ ] The package is split from `eng-platform` into its own repository with its history (only its directory), and its
      workspace dependencies are replaced by PyPI version ranges of already-public packages.
- [ ] A secret scan of the split history is clean; otherwise the public repository starts from a fresh, sanitized
      history.
- [ ] No vendor binaries, generated vendor wrappers, client data, personal paths, internal hostnames or usernames.
- [ ] `LICENSE` (Apache-2.0), `NOTICE` if needed, `THIRD_PARTY_NOTICES.md`, SPDX license identifiers in source headers.
- [ ] `README.md` with purpose, install (`uvx ...`), quick start, requirements (host programs and versions), and limits.
- [ ] `CONTRIBUTING.md` (process summary, DCO, how to run the local gate), `CODE_OF_CONDUCT.md`, `SECURITY.md` (how to
      report vulnerabilities and wrong engineering results).
- [ ] Issue and pull request templates; labels; branch protection; identities as in [11](11-repository-standard.md) §6.
- [ ] CI works for outside contributors without secrets; CI reviewers run only after a maintainer label; no
      self-hosted runner is exposed to forks.
- [ ] Examples and fixtures are synthetic or approved for publication.
- [ ] `AGENTS.md` contains nothing private.

Dependencies decide the order: `eng-contract` goes public first, then the packages that depend only on it.

The sanitize-and-package work can use an open-source pipeline (fork, sanitize, package) as listed in the
[tooling map](09-tooling-map.md); the checklist above is the acceptance criterion either way.

## 5. After going public

Outside contributions follow the same lifecycle, gates and reviews, with the DCO sign-off. Engineering-output changes
from outside contributors always require the owner's review and the verification record.
