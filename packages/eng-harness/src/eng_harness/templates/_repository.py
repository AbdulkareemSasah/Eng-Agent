"""Template repository: the shipped folder and the user folder (spec 0004 section 4.3, AC12).

Purpose: find and list `<name>-<version>.template.yaml` files and load them through the strict loader and the model.
Rules: the same name and version in both folders is `TemplateAmbiguous` (a user file never shadows a shipped one); a
synthetic template is refused unless `allow_synthetic=True` (tests only); a name is never a path; an invalid file is an
error, never skipped. Nothing is converted, defaulted or written; no network, no process.
Errors: `TemplateInvalid` (`not_found` from `get`, `synthetic_not_allowed`, the loader's reasons), `TemplateAmbiguous`.
"""

from pathlib import Path
from typing import Final

from eng_contract.errors import ContractError, ErrorCode

from eng_harness.templates._model import Template, TemplateInvalid
from eng_harness.templates._yaml import load_strict

SUFFIX: Final = ".template.yaml"


class TemplateAmbiguous(ContractError):  # noqa: N818  # B-158: the name is fixed by spec 0004 section 6
    """The same `name@version` exists in the shipped and the user folder."""

    reason = "ambiguous"

    def __init__(self, name: str, version: str) -> None:
        """Build the error; `name` and `version` identify the template."""
        self.name = name
        self.version = version
        super().__init__(ErrorCode.INVALID_ARGUMENT, f"template ambiguous: {name}@{version} is in both folders")


def load_template(path: Path, *, allow_synthetic: bool = False) -> Template:
    """Load one template file; the file name must be `<name>-<version>.template.yaml` of its `meta`.

    Raises:
        TemplateInvalid: the loader's or the model's reason, or `synthetic_not_allowed`.
    """
    template = Template.from_data(load_strict(path), file_name=path.name)
    if template.meta.synthetic and not allow_synthetic:
        raise TemplateInvalid("synthetic_not_allowed", "meta.synthetic", path.name)
    return template


class TemplateRepository:
    """Templates of a shipped folder (package data) and a user folder; it is a `TemplateSource` for `resolve`."""

    def __init__(self, shipped_dir: Path, user_dir: Path, allow_synthetic: bool = False) -> None:
        """Remember the folders; a folder that does not exist holds no template."""
        self._dirs = (shipped_dir, user_dir)
        self._allow_synthetic = allow_synthetic

    def _paths(self, file_name: str) -> list[Path]:
        return [folder / file_name for folder in self._dirs if (folder / file_name).is_file()]

    def _load(self, path: Path) -> Template:
        return load_template(path, allow_synthetic=self._allow_synthetic)

    def find(self, name: str, version: str) -> Template | None:
        """Return `name@version`, or None when neither folder has it.

        Raises:
            TemplateAmbiguous: both folders have it.
            TemplateInvalid: the file is invalid.
        """
        file_name = f"{name}-{version}{SUFFIX}"
        if Path(file_name).name != file_name:
            return None  # a name is never a path
        found = self._paths(file_name)
        if len(found) > 1:
            raise TemplateAmbiguous(name, version)
        return self._load(found[0]) if found else None

    def get(self, name: str, version: str) -> Template:
        """Return `name@version`; `TemplateInvalid` (`not_found`) when there is none, otherwise as `find`."""
        template = self.find(name, version)
        if template is None:
            raise TemplateInvalid("not_found", f"{name}@{version}")
        return template

    def list(self) -> tuple[Template, ...]:
        """Load every template of both folders, ordered by name and version; the errors of `find` apply."""
        names = {p.name for folder in self._dirs if folder.is_dir() for p in folder.glob(f"*{SUFFIX}")}
        templates = []
        for file_name in names:
            found = self._paths(file_name)
            template = self._load(found[0])
            if len(found) > 1:
                raise TemplateAmbiguous(template.meta.name, template.meta.version)
            templates.append(template)
        return tuple(sorted(templates, key=lambda t: (t.meta.name, t.meta.version)))
