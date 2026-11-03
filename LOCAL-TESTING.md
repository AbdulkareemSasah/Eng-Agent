# LOCAL-TESTING: how to test v1 on your Windows machine

Status: skeleton. It is completed as the build progresses ([BUILD-STATUS.md](BUILD-STATUS.md)). Every item in this
file needs a host program, so none of it was run in the build environment.

Sections that will be filled in:

1. Prerequisites on Windows (uv, Python 3.14, the Sasaah server builds and their paths, `harness.toml`), and why
   everything runs from a normal terminal, not an elevated or low-integrity one.
2. The environment check: environment, server builds, tool-list fingerprints, installed host programs.
3. Record mode: capturing real server replies into fixture files and running the tests again on them.
4. Spikes S-02 and S-04, step by step.
5. Acceptance A1 to A7 of the model edit cycle, step by step.
6. How to report a failure back to an agent.
7. Every item marked "needs local test", by package.
