"""The ``review`` command (spec 4.15, AC61): pinned reviewer prompts and the ``ci-review`` job.

The prompts and their SHA-256 manifest are read from the policy root (the gate root in pull-request context), so a pull
request cannot change the prompts that review it. Provider calls are not part of 0.1: in bootstrap mode the job reports
AW04 after verifying the prompts, otherwise it fails closed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

from eng_dev_gate.config import Mode, awaiting_finding
from eng_dev_gate.gate_root import GateContext
from eng_dev_gate.report import CommandResult, Finding, Severity, StepResult, render
from eng_dev_gate.results import Status, UsageError

PROMPT_DIR = "tools/eng-dev-gate/src/eng_dev_gate/prompts"
PROMPTS = ("general.md", "security.md")
MANIFEST = "manifest.json"


def _error(code: str, message: str, path: str) -> Finding:
    return Finding(code=code, severity=Severity.ERROR, path=path, message=message)


def _read_manifest(context: GateContext) -> dict[str, str] | Finding:
    path = f"{PROMPT_DIR}/{MANIFEST}"
    try:
        loaded = json.loads(context.read_policy(path))
    except json.JSONDecodeError as error:
        return _error("RV001", f"the prompt manifest is not valid JSON: {error.msg}", path)
    if not isinstance(loaded, dict) or not all(isinstance(v, str) for v in loaded.values()):
        return _error("RV001", "the prompt manifest must map each prompt file to its SHA-256 hash", path)
    return {str(k): str(v) for k, v in loaded.items()}


def verify_prompts(context: GateContext) -> list[Finding]:
    """Check the pinned prompts against the manifest (RV001 for each difference).

    Args:
        context: the policy reader; prompts and manifest are read below its policy root.

    Returns:
        One RV001 error per prompt that is missing, changed or not listed, and per unexpected manifest entry.

    Raises:
        UsageError: the manifest file cannot be read.
    """
    manifest = _read_manifest(context)
    if isinstance(manifest, Finding):
        return [manifest]
    findings = [
        _error("RV001", f"the manifest lists {name!r}, which is not a pinned prompt", f"{PROMPT_DIR}/{MANIFEST}")
        for name in manifest
        if name not in PROMPTS
    ]
    for name in PROMPTS:
        path = f"{PROMPT_DIR}/{name}"
        if name not in manifest:
            findings.append(_error("RV001", f"{name!r} is not in the prompt manifest", path))
            continue
        try:
            text = context.read_policy(path)
        except UsageError:
            findings.append(_error("RV001", f"the pinned prompt {name!r} is missing", path))
            continue
        if hashlib.sha256(text.encode("utf-8")).hexdigest() != manifest[name]:
            findings.append(_error("RV001", f"{name!r} does not match its recorded SHA-256 hash", path))
    return findings


def handle(args: argparse.Namespace) -> Status:
    """``review [--check-prompts]``: verify the prompts, then report AW04 (bootstrap) or fail closed (RV002).

    Raises:
        UsageError: the manifest cannot be read.
    """
    context: GateContext = args.gate_context
    steps = [StepResult(name="prompts", findings=verify_prompts(context))]
    if not steps[0].findings and not args.check_prompts:
        if context.config.mode is Mode.BOOTSTRAP:
            message = "no reviewer identity or provider keys yet: CI reviewer verdicts are not verified"
            steps.append(StepResult(name="review", findings=[awaiting_finding(context.config, "AW04", message)]))
        else:
            message = "no CI reviewer provider is configured, so no verdict exists"
            steps.append(StepResult(name="review", findings=[_error("RV002", message, PROMPT_DIR)]))
    result = context.with_findings(CommandResult(command="review", mode=context.config.mode.value, steps=steps))
    render(result, args.format, sys.stdout, os.environ)
    return result.status
