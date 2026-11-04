"""POSIX location probe for development and Linux CI (spec 4.5.2): classifies from `/proc/self/mountinfo`.

Units: none. Errors: none raised; an unreadable mount table gives `LOCAL` (logged), as the spec states.
"""

import logging
import re
from pathlib import Path

from eng_contract.store._workspace import LocationClass

_LOG = logging.getLogger(__name__)
_NETWORK_TYPES = frozenset({"nfs", "nfs4", "cifs", "smb3", "smbfs", "afs", "fuse.sshfs", "9p"})
_OCTAL_ESCAPE = re.compile(r"\\([0-7]{3})")


class PosixProbe:
    """Classifies a folder as `NETWORK` when its longest-matching mount has a network file-system type."""

    def __init__(self, mountinfo: Path = Path("/proc/self/mountinfo")) -> None:
        self._mountinfo = mountinfo

    def classify(self, path: Path) -> LocationClass:
        """Return `NETWORK` or `LOCAL`; `LOCAL` also when the mount table is unreadable (logged)."""
        try:
            text = self._mountinfo.read_text(encoding="utf-8")
        except OSError as exc:
            _LOG.warning("mount table unreadable; treating the folder as local", extra={"reason": str(exc)})
            return LocationClass.LOCAL
        target = path.resolve()
        best, best_type = Path("/"), ""
        for line in text.splitlines():
            head, separator, tail = line.partition(" - ")
            fields, rest = head.split(), tail.split()
            if not separator or len(fields) < 5 or not rest:
                continue
            mount = Path(_OCTAL_ESCAPE.sub(lambda m: chr(int(m.group(1), 8)), fields[4]))
            if target.is_relative_to(mount) and len(mount.parts) >= len(best.parts):
                best, best_type = mount, rest[0]
        return LocationClass.NETWORK if best_type in _NETWORK_TYPES else LocationClass.LOCAL
