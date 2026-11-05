"""``uv run python -m eng_harness.decisions --write-lock`` (spec 0005 section 4.2)."""

from eng_harness.decisions._points import main

if __name__ == "__main__":
    raise SystemExit(main())
