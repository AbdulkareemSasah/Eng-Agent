"""Revit adapter data (spec 0011 section 4.4)."""

from importlib.resources import files

from eng_harness.adapters._allowlist import Allowlist, load_allowlist

__all__ = ["revit_allowlist"]


def revit_allowlist(*, role: str | None = None) -> Allowlist:
    """Load the packaged Revit allowlist; raises `AllowlistError` when it is invalid.

    With no `role`, every entry is returned. A server section passes `role` (`read` or `write`) so only that
    role's tools are served under its pinned fingerprint (spec 0011 section 4.3 item 4, plan 0011 T3).
    """
    text = files("eng_harness.adapters.revit").joinpath("_allowlist.toml").read_text(encoding="utf-8")
    source = "revit/_allowlist.toml"
    if role is not None:
        return load_allowlist(text, source, product=role)
    return load_allowlist(text, source)
