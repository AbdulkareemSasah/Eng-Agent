# Local testing: eng-harness

No host program is involved. These checks need the owner's machine (plan 0001 section 4; completed by T16 and T19):
1. The overhead benchmark and the fsync cost on the owner's workstation disk, with antivirus active, against the 20 ms target.
2. The run lock is released after killing the engine from Task Manager.
3. A resume after a forced power-off of a virtual machine (power loss is not covered by tests).
4. File-copy promotion onto a folder the engineer uses, including a target file open in another program.
