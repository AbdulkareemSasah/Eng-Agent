"""Calc internals (spec 0003 4.1): the content hash and the lock file."""


class CalcRegistryError(ValueError):
    """A registration rule is broken; `rule` names it. Defined here so the hash can raise it without an import cycle."""

    def __init__(self, rule: str, calc_id: str, why: str) -> None:
        """Keep `rule` for callers and tests."""
        super().__init__(f"{calc_id}: {rule}: {why}")
        self.rule = rule


__all__ = ["CalcRegistryError"]
