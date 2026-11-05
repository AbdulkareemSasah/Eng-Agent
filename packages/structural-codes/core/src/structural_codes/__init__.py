"""Core framework of the structural-codes folder (spec 0001, section 4.1).

Purpose: the public entry points `evaluate` and `evaluate_batch` with their `BatchItem`, `Evaluation` and `Mode`, and
the version constant of the core package.
"""

# B-262: re-exported with explicit aliases and not added to `__all__`, because tests/unit/test_package.py (T1, outside
# this task's files) still asserts `__all__ == ["__version__"]`; task T14 completes `__all__` and that test.
from structural_codes._runner import BatchItem as BatchItem
from structural_codes._runner import Evaluation as Evaluation
from structural_codes._runner import Mode as Mode
from structural_codes._runner import evaluate as evaluate
from structural_codes._runner import evaluate_batch as evaluate_batch

__version__ = "0.1.0.dev0"

__all__ = ["__version__"]
