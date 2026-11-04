"""Strict YAML 1.2 loader tests (plan 0004 task T2; spec 0004 AC7).

The documents are synthetic: every value is a placeholder, not an engineering value.
"""

from pathlib import Path

import pytest

from eng_harness.templates import TemplateInvalid
from eng_harness.templates._yaml import MAX_BYTES, MAX_DEPTH, load_strict, loads_strict

MIB = 1024 * 1024


def _write(tmp_path: Path, text: str | bytes, name: str = "sample-0.1.0.template.yaml") -> Path:
    path = tmp_path / name
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text, encoding="utf-8", newline="")
    return path


def _nested(levels: int) -> str:
    """A block document whose deepest mapping sits `levels` collections down (the root counts as level 1)."""
    lines = [f"{'  ' * depth}k{depth}:" for depth in range(levels - 1)]
    lines.append(f"{'  ' * (levels - 1)}leaf: 1")
    return "\n".join(lines) + "\n"


def test_strict_loader(tmp_path: Path) -> None:
    refused = {
        "duplicate key": "a: 1\na: 2\n",
        "duplicate key in a nested mapping": "m:\n  x: 1\n  y: 2\n  x: 3\n",
        "anchor": "a: &x 1\n",
        "alias": "a: &x 1\nb: *x\n",
        "alias to a mapping": "a: &x {p: 1}\nb: *x\n",
        "merge key with alias": "a: &x {p: 1}\nb:\n  <<: *x\n",
        "integer key": "1: a\n",
        "boolean key": "true: a\n",
        "null key": "null: a\n",
        "float key": "1.5: a\n",
        "sequence key": "? [1]\n: 2\n",
        "custom tag": "a: !custom 1\n",
        "language object tag": "a: !!python/object:os.system x\n",
        "standard tag": "a: !!str 5\n",
        "binary tag": "a: !!binary aGk=\n",
        "tagged mapping": "a: !!map {p: 1}\n",
        "two documents": "a: 1\n---\nb: 2\n",
        "syntax error": "a: [1, 2\n",
        "tab indentation": "a:\n\tb: 1\n",
        "empty file": "",
        "comment only": "# nothing here\n",
        "infinity": "a: .inf\n",
        "not a number": "a: .nan\n",
        "overflowing float": "a: 1e999\n",
        "nine levels": _nested(MAX_DEPTH + 1),
    }
    for label, text in refused.items():
        with pytest.raises(TemplateInvalid) as caught:
            load_strict(_write(tmp_path, text))
        assert caught.value.reason == "yaml_invalid", label
        assert caught.value.file == "sample-0.1.0.template.yaml", label

    loaded = load_strict(
        _write(
            tmp_path,
            "negative: no\nswitch: on\nclock: 1:30\noctal_looking: 010\nexplicit_octal: 0o10\nhex: 0x1F\n"
            "date: 2026-01-31\nmerge_word: <<\nunderscored: 1_000\nbinary_looking: 0b11\nyes_word: yes\n"
            "truth: true\nnothing: ~\nreal: 1e3\nsigned: -7\nquoted: '010'\nitems: [no, 1:30, 2]\n",
        )
    )
    assert loaded == {
        "negative": "no",
        "switch": "on",
        "clock": "1:30",
        "octal_looking": 10,
        "explicit_octal": 8,
        "hex": 31,
        "date": "2026-01-31",
        "merge_word": "<<",
        "underscored": "1_000",
        "binary_looking": "0b11",
        "yes_word": "yes",
        "truth": True,
        "nothing": None,
        "real": 1000.0,
        "signed": -7,
        "quoted": "010",
        "items": ["no", "1:30", 2],
    }
    assert isinstance(loaded, dict)
    assert type(loaded["octal_looking"]) is int
    assert type(loaded["truth"]) is bool

    assert load_strict(_write(tmp_path, _nested(MAX_DEPTH))) is not None
    assert MAX_DEPTH == 8
    assert MAX_BYTES == MIB


def test_size_limit(tmp_path: Path) -> None:
    """A file of exactly 1 MiB loads; one byte more is refused before it is parsed."""
    body = b"a: "
    padding = b"x" * (MIB - len(body) - 1) + b"\n"
    at_limit = _write(tmp_path, body + padding, "at-limit-0.1.0.template.yaml")
    assert at_limit.stat().st_size == MIB
    loaded = load_strict(at_limit)
    assert isinstance(loaded, dict)
    assert len(str(loaded["a"])) == MIB - len(body) - 1

    over = _write(tmp_path, body + padding + b"#", "over-0.1.0.template.yaml")
    assert over.stat().st_size == MIB + 1
    with pytest.raises(TemplateInvalid) as caught:
        load_strict(over)
    assert caught.value.reason == "yaml_invalid"


def test_file_errors(tmp_path: Path) -> None:
    with pytest.raises(TemplateInvalid) as missing:
        load_strict(tmp_path / "absent-0.1.0.template.yaml")
    assert missing.value.reason == "not_found"
    assert missing.value.file == "absent-0.1.0.template.yaml"

    with pytest.raises(TemplateInvalid) as not_utf8:
        load_strict(_write(tmp_path, b"a: \xff\xfe\n"))
    assert not_utf8.value.reason == "yaml_invalid"


def test_bytes_and_text_forms(tmp_path: Path) -> None:
    """A byte order mark and Windows line endings do not change the data."""
    plain = load_strict(_write(tmp_path, "a: 1\nb:\n  c: [x, y]\n"))
    assert plain == {"a": 1, "b": {"c": ["x", "y"]}}
    assert load_strict(_write(tmp_path, b"\xef\xbb\xbfa: 1\r\nb:\r\n  c: [x, y]\r\n")) == plain
    assert loads_strict("a: 1\nb:\n  c: [x, y]\n") == plain


def test_error_names_the_path_of_a_bad_key() -> None:
    with pytest.raises(TemplateInvalid) as bad_key:
        loads_strict("outer:\n  inner:\n    7: x\n", file="t.yaml")
    assert (bad_key.value.reason, bad_key.value.path, bad_key.value.file) == ("yaml_invalid", "outer.inner", "t.yaml")

    with pytest.raises(TemplateInvalid) as bad_number:
        loads_strict("outer:\n  limit: .inf\n")
    assert (bad_number.value.reason, bad_number.value.path) == ("yaml_invalid", "outer.limit")
    assert "inf" not in str(bad_number.value)
