"""Keep the safety-critical IBKR tests from skipping silently in CI.

The write-barrier tests on the real ``ib_async.Client`` and the XNYS freshness
tests sit behind ``pytest.importorskip``. A skip there is invisible in a green
run, so in CI (``CI`` set, as GitHub Actions does) a missing optional package
must be a failure, not a skip. Locally the tests skip as before.
"""

from __future__ import annotations

import importlib
import os

import pytest

pytestmark = pytest.mark.unit

#: Imported by an importorskip somewhere in tests/; the ``ibkr`` extra provides them.
REQUIRED_IN_CI = ("ib_async", "exchange_calendars")


def _in_ci(environ=os.environ) -> bool:
    return environ.get("CI", "").strip().lower() not in ("", "0", "false")


@pytest.mark.parametrize("module", REQUIRED_IN_CI)
def test_ibkr_extra_is_installed_in_ci(module):
    if not _in_ci():
        pytest.importorskip(module)
        return
    try:
        importlib.import_module(module)
    except ImportError as exc:
        pytest.fail(
            f"{module} is missing in CI: tests behind importorskip({module!r}) would "
            f"skip silently. Install the ci extra: pip install -e '.[ci]' ({exc})"
        )


@pytest.mark.parametrize(
    "value, expected",
    [(None, False), ("", False), ("0", False), ("false", False), ("true", True), ("1", True)],
)
def test_ci_detection(value, expected):
    environ = {} if value is None else {"CI": value}
    assert _in_ci(environ) is expected


def test_every_importorskip_of_an_ibkr_package_is_covered():
    """A new importorskip of an ibkr-extra package must be added to REQUIRED_IN_CI."""
    import pathlib
    import re

    tests = pathlib.Path(__file__).parent
    found = set()
    for path in tests.glob("test_ibkr_*.py"):
        found |= set(re.findall(r'importorskip\(\s*"([A-Za-z0-9_]+)"', path.read_text("utf-8")))
    assert found <= set(REQUIRED_IN_CI), found - set(REQUIRED_IN_CI)
