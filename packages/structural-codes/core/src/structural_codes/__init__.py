"""Core framework of the structural-codes folder (spec 0001, section 4.1).

Purpose: the public entry points `evaluate` and `evaluate_batch` with their `BatchItem`, `Evaluation` and `Mode`, and
the version constant of the core package.
"""

from structural_codes._runner import BatchItem, Evaluation, Mode, evaluate, evaluate_batch

__version__ = "0.1.0.dev0"

__all__ = ["BatchItem", "Evaluation", "Mode", "__version__", "evaluate", "evaluate_batch"]
