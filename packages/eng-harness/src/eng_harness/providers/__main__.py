"""``python -m eng_harness.providers``: set, delete and inspect credential-store entries (spec 0009 section 4.4)."""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import SecretStr

from eng_harness.cli._config import load_config, resolve_config_path
from eng_harness.providers._config import ProvidersConfig, load_providers_config
from eng_harness.providers._credentials import CredentialStore, KeyringCredentialStore, status_lines


def build_store() -> CredentialStore:
    return KeyringCredentialStore()


def _read_secret() -> str:
    value = getpass.getpass("Key: ") if sys.stdin.isatty() else sys.stdin.readline().rstrip("\n")
    if not value:
        sys.stderr.write("empty key refused\n")
        raise SystemExit(2)
    return value


def _load_providers(config: Path | None) -> ProvidersConfig:
    path = resolve_config_path(config, os.environ, None)
    harness = load_config(path)
    return load_providers_config(harness.providers)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eng_harness.providers")
    parser.add_argument("--config", type=Path, metavar="FILE", help="harness.toml")
    subparsers = parser.add_subparsers(dest="command", required=True)

    set_key = subparsers.add_parser("set-key", help="store a key for NAME")
    set_key.add_argument("name", metavar="NAME")

    delete_key = subparsers.add_parser("delete-key", help="remove a stored key")
    delete_key.add_argument("name", metavar="NAME")

    subparsers.add_parser("status", help="show whether each configured key is present")

    args = parser.parse_args(list(argv) if argv is not None else None)
    store = build_store()

    if args.command == "set-key":
        store.set(args.name, SecretStr(_read_secret()))
        return 0

    if args.command == "delete-key":
        store.delete(args.name)
        return 0

    providers = _load_providers(args.config)
    for line in status_lines(providers, store):
        sys.stdout.write(f"{line}\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except ValueError as error:
        sys.stderr.write(f"{error}\n")
        raise SystemExit(2) from error
