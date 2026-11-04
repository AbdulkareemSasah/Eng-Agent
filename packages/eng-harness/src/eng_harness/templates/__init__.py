"""Templates of the design basis (spec 0004): the model, inheritance, the repository and `check_template`.

Purpose: the public surface of `eng_harness.templates`; later plan tasks add the shipped content and the basis builder.
"""

from eng_harness.templates._check import TemplateIssue, TemplateReport, check_template
from eng_harness.templates._model import AskItem, Bounds, Entry, Meta, Section, Template, TemplateInvalid
from eng_harness.templates._repository import TemplateAmbiguous, TemplateRepository, load_template
from eng_harness.templates._resolve import ResolvedTemplate, TemplateSource, resolve

__all__ = [
    "AskItem",
    "Bounds",
    "Entry",
    "Meta",
    "ResolvedTemplate",
    "Section",
    "Template",
    "TemplateAmbiguous",
    "TemplateInvalid",
    "TemplateIssue",
    "TemplateReport",
    "TemplateRepository",
    "TemplateSource",
    "check_template",
    "load_template",
    "resolve",
]
