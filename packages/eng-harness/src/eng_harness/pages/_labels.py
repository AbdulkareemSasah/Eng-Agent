"""The label catalog of the pages (spec 0006 4.4.6): every fixed word a screen shows, never taken from data.

Purpose: one place for the screen texts, so that no text of a run reaches a label. Units: none. Errors: none.
"""

from collections.abc import Mapping
from typing import Final

from eng_harness._html import Trusted, trusted

APPROVE: Final[Trusted] = trusted("Approve")
REJECT: Final[Trusted] = trusted("Reject")
ACKNOWLEDGE: Final[Trusted] = trusted("Acknowledge")
NAME: Final[Trusted] = trusted("Your name")
REASON: Final[Trusted] = trusted("Reason")
REJECT_ITEM: Final[Trusted] = trusted("Reject this item")
ITEM_REASON: Final[Trusted] = trusted("Reason of this item")
TITLE: Final[Trusted] = trusted("Request")
PREVIEW_HASH: Final[Trusted] = trusted("Preview")
BACK: Final[Trusted] = trusted("Back")
DAMAGED: Final[Trusted] = trusted("The preview is damaged or cannot be shown: no answer can be given here.")
ITEMS: Final[tuple[Trusted, ...]] = (trusted("Item"), trusted("Label"), trusted("Values"), REJECT_ITEM, ITEM_REASON)
DIFF: Final[tuple[Trusted, ...]] = tuple(
    trusted(w) for w in ("Section", "Key", "Change", "Property", "Before", "After", "Unit")
)  # fmt: skip
DIFF_HEADING: Final[Trusted] = trusted("Differences from the last revision")
DIFF_UNREADABLE: Final[Trusted] = trusted("The difference report cannot be read.")
BINDING_HEADING: Final[Trusted] = trusted("Binding")
BINDING: Final[tuple[Trusted, ...]] = tuple(
    trusted(w) for w in ("Model", "Model id", "Revision", "Fingerprint", "File hash")
)  # fmt: skip
PROMOTION: Final[tuple[Trusted, ...]] = tuple(
    trusted(w) for w in ("Model", "Target", "Backup in the run folder", "Original hash", "Working copy hash")
)  # fmt: skip
NO_WORKING_COPY: Final[Trusted] = trusted("No working copy is recorded for this model; the bound file hash is shown.")
SIGN: Final[Trusted] = trusted("Sign")
REPORT_LINK: Final[Trusted] = trusted("Report so far (DRAFT)")
VERDICTS_HEADING: Final[Trusted] = trusted("Verdicts")
VERDICTS: Final[tuple[Trusted, ...]] = (trusted("Status"), trusted("Count"))
EXCEPTIONS_HEADING: Final[Trusted] = trusted("Exceptions: each needs a written reason to sign")
EXCEPTIONS: Final[tuple[Trusted, ...]] = tuple(
    trusted(w) for w in ("Exception", "Subject", "Check", "Status", "Reason")
)
UNRELEASED_HEADING: Final[Trusted] = trusted("Results that depend on an unreleased tool")
ACKNOWLEDGE_UNRELEASED: Final[Trusted] = trusted("I sign knowing that these results depend on an unreleased tool")
SUBMIT: Final[Trusted] = trusted("Submit")
EVIDENCE: Final[Trusted] = trusted("Evidence")
REFERENCES: Final[Trusted] = trusted("Evidence references")
NOT_SHOWN: Final[Trusted] = trusted("This request cannot be shown safely: no answer can be given here. Cause:")
OPTIONS: Final[Mapping[str, Trusted]] = {
    "accept": trusted("Accept this revision"),
    "more_edits": trusted("Ask for more edits"),
    "hand_edit": trusted("I edited by hand: continue (save the model in the host program first)"),
    "applied": trusted("The change was applied"),
    "not_applied": trusted("The change was not applied"),
    "restore": trusted("Restore the saved copy"),
    "abandon": trusted("Abandon the run"),
}  # the engineer turn (spec 0007) and the engine's own requests (engine 4.5): option id to its label
INPUT_NOTE: Final[Trusted] = trusted(
    "These fields are read-only here: provide the answers with `resume --answers FILE`."
)
INPUT_FIELDS: Final[tuple[Trusted, ...]] = tuple(trusted(w) for w in ("Field", "Type", "Unit", "Bounds"))
NAME_PROPOSED: Final[Trusted] = trusted("Engineer named in the settings")
