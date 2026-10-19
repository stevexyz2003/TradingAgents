"""The dependency security scan stays in CI and stays blocking.

It was lost once in a rebase (2026-08-18) without anyone noticing; this guard makes
the next loss a red test instead of a silent gap.
"""

from pathlib import Path

import pytest

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "security-audit.yml"


@pytest.mark.unit
def test_the_security_audit_workflow_exists():
    assert WORKFLOW.is_file(), "the dependency security scan workflow is missing"


@pytest.mark.unit
def test_the_security_audit_runs_pip_audit_and_blocks():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "pip-audit -r" in text
    assert "continue-on-error" not in text, "the scan must fail the job on a finding"


@pytest.mark.unit
def test_the_security_audit_runs_on_push_pr_and_a_schedule():
    text = WORKFLOW.read_text(encoding="utf-8")
    for trigger in ("push:", "pull_request:", "schedule:"):
        assert trigger in text, f"missing trigger {trigger}"
