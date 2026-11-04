"""The one shared style sheet of the pages and the report (spec 0006 section 4.5).

System fonts only, no `url()`, no import: the page loads nothing, and the sheet's hash goes into the policy.
"""

from typing import Final

from eng_harness._html import Stylesheet, stylesheet

STYLESHEET: Final[Stylesheet] = stylesheet(
    "body{font:16px/1.5 system-ui,sans-serif;margin:1.5rem auto;max-width:60rem;padding:0 1rem;color:#1a1a1a;"
    "background:#fff}"
    "table{border-collapse:collapse;width:100%}th,td{border:1px solid #888;padding:.25rem .5rem;text-align:start}"
    "th{background:#eee}.label{font-weight:600}.note{color:#555}.field{display:inline-block;margin-inline-end:1rem}"
    ".draft{border:3px solid #b00020;padding:.5rem;font-weight:700}"
    "button{font:inherit;padding:.4rem 1rem;margin-inline-end:.5rem}"
    "@media print{.draft::after{content:'DRAFT'}}"
)
