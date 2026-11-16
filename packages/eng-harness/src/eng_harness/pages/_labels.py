"""The label catalog of the pages (spec 0006 4.4.6): every fixed word a screen shows, never taken from data.

Purpose: one place for the screen texts, so that no text of a run reaches a label. Units: none. Errors: none.
"""

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
