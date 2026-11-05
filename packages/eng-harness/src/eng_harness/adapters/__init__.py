"""Adapters from the engine's ports to host tools: allowlists, arguments and envelopes (spec 0002 section 4.5)."""

from eng_harness.adapters._allowlist import Allowlist, AllowlistError, load_allowlist
from eng_harness.adapters._args import HostTarget, convert_quantities, host_arguments, referenced_results, validate_call
from eng_harness.adapters._descriptors import ToolDescriptor
from eng_harness.adapters._envelope import HostReply, make_envelope, parse_reply

__all__ = [
    "Allowlist",
    "AllowlistError",
    "HostReply",
    "HostTarget",
    "ToolDescriptor",
    "convert_quantities",
    "host_arguments",
    "load_allowlist",
    "make_envelope",
    "parse_reply",
    "referenced_results",
    "validate_call",
]
