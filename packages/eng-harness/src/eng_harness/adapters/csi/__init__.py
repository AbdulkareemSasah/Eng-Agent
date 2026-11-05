"""CSI (ETABS) adapter data (spec 0002 section 4.6)."""

from importlib.resources import files

from eng_harness.adapters._allowlist import Allowlist, load_allowlist

__all__ = ["csi_allowlist"]


def csi_allowlist() -> Allowlist:
    """Load the packaged CSI allowlist; raises `AllowlistError` when it is invalid."""
    text = files("eng_harness.adapters.csi").joinpath("_allowlist.toml").read_text(encoding="utf-8")
    return load_allowlist(text, "csi/_allowlist.toml")
