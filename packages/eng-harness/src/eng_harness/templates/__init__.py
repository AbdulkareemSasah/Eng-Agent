"""Templates of the design basis (spec 0004): the template model and its errors.

Purpose: the public surface of `eng_harness.templates`; later plan tasks add loading, resolution and the repository.
"""

from eng_harness.templates._model import AskItem, Bounds, Entry, Meta, Section, Template, TemplateInvalid

__all__ = ["AskItem", "Bounds", "Entry", "Meta", "Section", "Template", "TemplateInvalid"]
