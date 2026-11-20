"""IDEA StatiCa adapter data (spec 0014 section 4.4)."""

from importlib.resources import files

from eng_harness.adapters._allowlist import Allowlist, load_allowlist

__all__ = ["idea_allowlist"]


def idea_allowlist(route: str | None = None) -> Allowlist:
    """Load the packaged IDEA allowlist; raises `AllowlistError` when it is invalid.

    With no `route`, every entry is returned (classification and fingerprint). A server section passes its
    `route` (`native` or `rest`) so only that route is served (AC41).
    """
    text = files("eng_harness.adapters.idea").joinpath("_allowlist.toml").read_text(encoding="utf-8")
    source = "idea/_allowlist.toml"
    if route is not None:
        return load_allowlist(text, source, route=route, product="IDEA")
    # Full catalog: load one route then restore every entry (tool_names / fingerprint stay product-wide).
    loaded = load_allowlist(text, source, route="native", product="IDEA")
    catalog = loaded._catalog or loaded.tools
    full = loaded.model_copy(update={"tools": catalog})
    full._listed = frozenset()
    full._catalog = ()
    full._product = "IDEA"
    return full
