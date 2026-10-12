"""The IBKR client library stays an optional, exactly pinned extra, and no credential leaks.

These guards read pyproject.toml, the git index, the CI workflow files, the IBKR
scripts and their operating manual only. They never read the real .env and never
reach the IBKR gateway.
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


def _handbook_paper_run_dirs() -> list[str]:
    """The --out and --state values of the paper-run command in the IBKR handbook."""
    text = (ROOT / "scripts" / "IBKR_EXECUTION.md").read_text(encoding="utf-8")
    runs = [line for line in text.splitlines() if "daily_paper_run.py" in line and "--out" in line]
    assert runs, "the handbook shows no paper-run command, so this guard would check nothing"
    dirs = []
    for line in runs:
        tail = line.split("daily_paper_run.py", 1)[1]
        dirs += re.findall(r"--(?:out|state) (\S+)", tail)
    return dirs


@pytest.mark.unit
def test_local_paper_run_output_is_ignored_by_git():
    # WR-07: with --portfolio the reports carry cash, positions and average
    # prices. The handbook's relative --out/--state dirs sit inside this public
    # fork, so a `git add -A` must not pick them up.
    if not (ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    relative = [d.replace("\\", "/") for d in _handbook_paper_run_dirs() if "%" not in d]
    assert relative, "expected the handbook to use repo-relative dirs; update this guard"
    # What daily_paper_run.py writes there: the archived complete report
    # (_archive), the decision log, the summaries and the graph logs. The
    # reports/ tree alone is already covered by the generic `reports/` rule.
    names = ("runs/2026-10-12/AAPL.md", "decision-log.md", "summary.json", "logs/state.json")
    for directory in relative:
        for name in names:
            probe = f"{directory}/{name}"
            result = subprocess.run(
                ["git", "check-ignore", "-q", probe], cwd=ROOT, capture_output=True, text=True
            )
            assert result.returncode == 0, f"{probe} is not ignored by git"


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
    assert public == {"connect", "positions", "health", "search_contract", "contract_details"}


@pytest.mark.unit
def test_adapter_hard_codes_no_order_id():
    source = ADAPTER.read_text(encoding="utf-8")
    assert "orderId=" not in source
    assert ".orderId =" not in source


# --- the handbook stays in step with the code -----------------------------------------

HANDBOOK = ROOT / "scripts" / "IBKR_EXECUTION.md"
EXECUTOR = ROOT / "scripts" / "ibkr_executor.py"


def _handbook_text() -> str:
    return HANDBOOK.read_text(encoding="utf-8")


def _load_executor():
    import importlib.util

    spec = importlib.util.spec_from_file_location("ibkr_executor", EXECUTOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.unit
def test_client_id_is_documented_in_the_handbook():
    from tests import ibkr_fakes

    broker = ibkr_fakes.load_broker()
    assert str(broker.EXECUTOR_CLIENT_ID) in _handbook_text()
    assert broker.EXECUTOR_CLIENT_ID > 9999


@pytest.mark.unit
def test_handbook_does_not_name_the_client_library():
    assert CLIENT_LIBRARY not in _handbook_text()


@pytest.mark.unit
def test_handbook_exit_table_matches_executor():
    executor = _load_executor()
    text = _handbook_text()
    codes = {
        name: getattr(executor, name)
        for name in dir(executor)
        if name.startswith("EXIT_") and isinstance(getattr(executor, name), int)
    }
    assert len(codes) == 10
    for name, value in codes.items():
        assert re.search(rf"^\| {value} \| `{name}` \|", text, re.M), f"{name}={value} not in table"


# --- the resolver stays pure: no library, no vendor normalizer, no clock, no trading hours --

CONTRACTS = ROOT / "scripts" / "ibkr_contracts.py"
VENDOR_NORMALIZER_MODULE = "tradingagents.dataflows.symbols"
VENDOR_NORMALIZER_NAME = "normalize_symbol"


def _full_imports(path: Path) -> set[str]:
    """Full dotted module names plus the imported names themselves."""
    names = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names.add(node.module)
            for alias in node.names:
                names.add(f"{node.module}.{alias.name}")
                names.add(alias.name)
    return names


@pytest.mark.unit
def test_resolver_is_library_free():
    top_level = _imports(CONTRACTS)
    assert CLIENT_LIBRARY not in top_level
    assert "tradingagents" not in top_level


@pytest.mark.unit
def test_resolver_does_not_use_the_vendor_normalizer():
    for path in (CONTRACTS, EXECUTOR):
        imports = _full_imports(path)
        offenders = {n for n in imports if n.startswith(VENDOR_NORMALIZER_MODULE)}
        assert not offenders, f"{path.name} imports {offenders}"
        assert VENDOR_NORMALIZER_NAME not in imports, f"{path.name} imports the normalizer"
    assert VENDOR_NORMALIZER_NAME not in CONTRACTS.read_text(encoding="utf-8")


@pytest.mark.unit
def test_no_hard_coded_trading_times_in_execution_code():
    # Patterns are built from parts so this file never contains them as literals.
    patterns = [
        ":".join(parts) for parts in (("13", "30"), ("14", "30"), ("09", "30"), ("16", "00"))
    ]
    files = sorted((ROOT / "scripts").glob("ibkr_*.py"))
    assert len(files) >= 3, "expected broker, executor and contracts; the guard would check nothing"
    hits = [
        (path.name, pattern)
        for path in files
        for pattern in patterns
        if pattern in path.read_text(encoding="utf-8")
    ]
    assert hits == []


@pytest.mark.unit
def test_resolver_takes_the_clock_as_a_parameter():
    source = CONTRACTS.read_text(encoding="utf-8")
    for forbidden in ("datetime.now", "time.time(", "date.today"):
        assert forbidden not in source, f"{forbidden} reads the clock inside the resolver"
