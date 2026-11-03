# Release {{package}} vX.Y.Z

- [ ] Every issue in the milestone meets the Definition of Done
- [ ] CI green on `main` at the release commit
- [ ] Host-facing changes since the last release: script-written acceptance records exist for every host version in
      `SUPPORT.md`, at a commit that includes those changes (the release workflow checks this)
- [ ] Changelog section written for readers; breaking changes flagged; code packs and calcs list every changed id
- [ ] Version bumped with `uv version --bump ...`; for code packs, major bump if any output changed
- [ ] Generated documents current (tool catalog, schema snapshot)
- [ ] Dependencies: lock file reviewed; licenses within the allowlist; vulnerability audit clean
- [ ] Release pull request reviewed and merged; tag `<package>-vX.Y.Z` on the merge commit
- [ ] Artifacts built by CI from the tag; software bill of materials attached
- [ ] Published (incubation: GitHub release only; public: PyPI through trusted publishing)
- [ ] Owner approval (G4): {{date}}
