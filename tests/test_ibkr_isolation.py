"""The IBKR client library stays an optional, exactly pinned extra, and no credential leaks.

These guards read pyproject.toml, the git index and the CI workflow files only.
They never read the real .env and never reach the IBKR gateway.
"""

import ast
import re
import subprocess
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT_TEXT = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
WORKFLOWS = ROOT / ".github" / "workflows"


@pytest.mark.unit
def test_ibkr_extra_pins_the_client_library_exactly():
    project = tomllib.loads(PYPROJECT_TEXT)["project"]
    extra = project["optional-dependencies"]["ibkr"]
    assert "ib_async==2.1.0" in extra
    assert "tzdata>=2025.2,<2026.0" in extra
    assert not any("ib_async" in dep for dep in project["dependencies"])


@pytest.mark.unit
def test_tzdata_cap_carries_its_reason():
    comment = re.compile(r"^\s*#.*tzdata>=2025\.2,<2026\.0.*\bunresolvable\b", re.M)
    assert comment.search(PYPROJECT_TEXT), (
        "the tzdata cap needs a comment naming the bound and why it is unresolvable without it"
    )


@pytest.mark.unit
def test_env_file_is_not_tracked():
    if not (ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    result = subprocess.run(
        ["git", "ls-files", ".env"], cwd=ROOT, capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == ""


@pytest.mark.unit
def test_ci_workflows_reference_no_ibkr_secret():
    files = sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml"))
    assert files, "no workflow files found, so this guard would check nothing"
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert "IBKR" not in text.upper(), f"{path.name} mentions IBKR"


# --- the adapter is the one place that talks to the client library -------------------

CLIENT_LIBRARY = "ib_async"
ADAPTER = ROOT / "scripts" / "ibkr_broker.py"


def _imports(path: Path) -> set[str]:
    names = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names.add(node.module.split(".")[0])
    return names


@pytest.mark.unit
def test_only_the_adapter_imports_the_client_library():
    importers = sorted(
        path.relative_to(ROOT).as_posix()
        for package in ("tradingagents", "cli", "scripts")
        for path in (ROOT / package).rglob("*.py")
        if CLIENT_LIBRARY in _imports(path)
    )
    assert importers == ["scripts/ibkr_broker.py"]


@pytest.mark.unit
def test_adapter_has_at_most_ten_public_methods():
    tree = ast.parse(ADAPTER.read_text(encoding="utf-8"))
    (cls,) = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "IbkrBroker"]
    public = {
        n.name
        for n in cls.body
        if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef) and not n.name.startswith("_")
    }
    assert len(public) <= 10
    assert public == {"connect", "positions", "health"}


@pytest.mark.unit
def test_adapter_hard_codes_no_order_id():
    source = ADAPTER.read_text(encoding="utf-8")
    assert "orderId=" not in source
    assert ".orderId =" not in source
