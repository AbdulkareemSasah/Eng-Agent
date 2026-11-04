"""Strict YAML 1.2 loader tests (plan 0004 task T2; spec 0004 AC7).

Every YAML text here is synthetic and holds no engineering value. The loader reads a file and returns plain data;
it never evaluates anything.
"""

import math
from pathlib import Path

import pytest

from eng_harness.templates import TemplateInvalid
from eng_harness.templates._yaml import MAX_BYTES, MAX_DEPTH, load_strict

REFUSED = {
    "duplicate_key": ("a: 1\na: 2\n", "a"),
    "duplicate_key_nested": ("outer:\n  inner: 1\n  other: 2\n  inner: 3\n", "outer.inner"),
    "duplicate_key_flow": ("{a: 1, a: 2}\n", "a"),
    "anchor": ("a: &x 1\n", "a"),
    "alias": ("a: &x 1\nb: *x\n", "a"),
    "merge_with_alias": ("base: &b {k: 1}\nderived:\n  <<: *b\n", "base"),
    "int_key": ("1: a\n", ""),
    "bool_key": ("true: a\n", ""),
    "null_key": ("null: a\n", ""),
    "empty_key": ("? \n: a\n", ""),
    "collection_key": ("? [a, b]\n: c\n", ""),
    "custom_tag": ("a: !custom x\n", "a"),
    "python_tag": ("a: !!python/object/apply:os.system [x]\n", "a"),
    "standard_tag": ("a: !!str 1\n", "a"),
    "tagged_mapping": ("a: !!map {b: 1}\n", "a"),
    "yaml_1_1_directive": ("%YAML 1.1\n---\na: 1\n", ""),
    "two_documents": ("a: 1\n---\nb: 2\n", ""),
    "empty_file": ("", ""),
    "comment_only": ("# nothing\n", ""),
    "scalar_root": ("just text\n", ""),
    "list_root": ("- a\n- b\n", ""),
    "syntax_error": ("a: [1, 2\n", ""),
    "tab_indent": ("a:\n\tb: 1\n", ""),
}


def _write(tmp_path: Path, text: str | bytes, name: str = "synthetic-x-0.1.0.template.yaml") -> Path:
    path = tmp_path / name
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text, encoding="utf-8", newline="")
    return path


def _nested(levels: int) -> str:
    """A mapping nested `levels` collections deep (the root counts as level 1)."""
    return "".join(f"{'  ' * i}k{i}:\n" for i in range(levels - 1)) + f"{'  ' * (levels - 1)}k: 1\n"


def _refused(path: Path) -> TemplateInvalid:
    with pytest.raises(TemplateInvalid) as caught:
        load_strict(path)
    assert caught.value.reason == "yaml_invalid"
    assert caught.value.file == str(path)
    return caught.value


@pytest.mark.parametrize("case", sorted(REFUSED))
def test_strict_loader(tmp_path: Path, case: str) -> None:
    text, key_path = REFUSED[case]
    error = _refused(_write(tmp_path, text))
    assert error.path == key_path
    assert "a: 1" not in str(error)  # the message holds the reason and the path, never file contents


def test_size_limit(tmp_path: Path) -> None:
    head = "a: 1\n# "
    exact = _write(tmp_path, head + "x" * (MAX_BYTES - len(head) - 1) + "\n", "exact.yaml")
    assert exact.stat().st_size == MAX_BYTES == 1024 * 1024
    assert load_strict(exact) == {"a": 1}
    over = _write(tmp_path, head + "x" * (MAX_BYTES - len(head)) + "\n", "over.yaml")
    assert over.stat().st_size == MAX_BYTES + 1
    _refused(over)


def test_depth_limit(tmp_path: Path) -> None:
    assert MAX_DEPTH == 8
    assert load_strict(_write(tmp_path, _nested(MAX_DEPTH), "ok.yaml"))
    deep = _refused(_write(tmp_path, _nested(MAX_DEPTH + 1), "deep.yaml"))
    assert deep.path.count(".") == MAX_DEPTH - 1
    _refused(_write(tmp_path, "a: " + "[" * 9 + "]" * 9 + "\n", "flow.yaml"))


def test_yaml_12_scalars(tmp_path: Path) -> None:
    text = "a: no\nb: on\nc: 1:30\nd: 010\ne: yes\nf: off\ng: y\nh: 0o17\ni: 0x1F\nj: 2026-11-04\nk: 1_000\n"
    data = load_strict(_write(tmp_path, text))
    assert data == {
        "a": "no",
        "b": "on",
        "c": "1:30",
        "d": 10,
        "e": "yes",
        "f": "off",
        "g": "y",
        "h": 15,
        "i": 31,
        "j": "2026-11-04",
        "k": "1_000",
    }
    assert type(data["d"]) is int
    assert data["c"] == "1:30"  # a string, not the sexagesimal number 90


def test_core_schema_scalars_and_collections(tmp_path: Path) -> None:
    text = (
        "n: null\ntilde: ~\nempty:\nt: true\nf: False\ni: -12\np: +3\nx: 1.5\ne: 2e3\nq: '010'\ndq: \"true\"\n"
        "block: |\n  line one\n  line two\nfolded: >\n  a\n  b\nlst: [1, two, {k: v}]\nseq:\n  - 1\n  - - nested\n"
        "'quoted key': 1\n"
    )
    data = load_strict(_write(tmp_path, text))
    expected = {
        "n": None,
        "tilde": None,
        "empty": None,
        "t": True,
        "f": False,
        "i": -12,
        "p": 3,
        "x": 1.5,
        "e": 2000.0,
        "q": "010",
        "dq": "true",
        "block": "line one\nline two\n",
        "folded": "a b\n",
        "lst": [1, "two", {"k": "v"}],
        "seq": [1, ["nested"]],
        "quoted key": 1,
    }
    assert data == expected
    assert list(data) == list(expected)  # the file's key order is kept
    assert type(data["t"]) is bool
    assert type(data["e"]) is float


def test_non_finite_floats_load_for_the_model_to_refuse(tmp_path: Path) -> None:
    data = load_strict(_write(tmp_path, "a: .inf\nb: -.INF\nc: .nan\n"))
    assert data["a"] == math.inf
    assert data["b"] == -math.inf
    nan = data["c"]
    assert isinstance(nan, float)
    assert math.isnan(nan)


def test_encoding_and_line_endings(tmp_path: Path) -> None:
    assert load_strict(_write(tmp_path, b"\xef\xbb\xbfa: 1\r\nb: caf\xc3\xa9\r\n")) == {"a": 1, "b": "caf\u00e9"}
    _refused(_write(tmp_path, b"a: \xff\xfe\n", "latin.yaml"))


def test_missing_file_is_not_hidden(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_strict(tmp_path / "absent.yaml")


def test_loader_is_general(tmp_path: Path) -> None:
    """Plan 0003 T3 reuses the loader for another schema: nothing here depends on template keys."""
    text = "schema: other/1\nitems: []\n"
    assert load_strict(_write(tmp_path, text, "other.yaml")) == {"schema": "other/1", "items": []}
