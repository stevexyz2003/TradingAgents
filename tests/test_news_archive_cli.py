"""news_archive.py CLI: run with catch-up, status, lock, CA bundle, smoke, max-runtime, PS1."""

from __future__ import annotations

import importlib.util
import io
import json
import tarfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from tradingagents.forecast.archive import amf, gdelt
from tradingagents.forecast.archive.seed import COLUMNS
from tradingagents.forecast.archive.status import (
    ensure_archive_start,
    read_day_status,
    write_heartbeat,
)
from tradingagents.forecast.archive.store import archive_base

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 21, 6, 30, tzinfo=UTC)
DAYS = [date(2026, 10, 18), date(2026, 10, 19), date(2026, 10, 20)]


def _load_cli():
    spec = importlib.util.spec_from_file_location(
        "news_archive", ROOT / "scripts" / "news_archive.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cli = _load_cli()


class FakeResponse:
    def __init__(self, status_code=200, text="", content=b"", content_type="application/json"):
        self.status_code = status_code
        self.text = text
        self.content = content or text.encode()
        self.headers = {"Content-Type": content_type}


def _tarball(day: date) -> bytes:
    xml = f"<info><titre>Synthetic notice {day}</titre></info>".encode()
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        info = tarfile.TarInfo("notice.xml")
        info.size = len(xml)
        archive.addfile(info, io.BytesIO(xml))
    return buffer.getvalue()


def _amf_name(day: date) -> str:
    return f"amf-gz_{day.strftime('%d%m%Y')}_1200.tar.gz"


class FakeNet:
    """Routes GDELT and DILA URLs to synthetic responses."""

    def __init__(self, *, bad_days=(), amf_days=DAYS, on_query=None):
        self.bad_days = {d.strftime("%Y%m%d") for d in bad_days}
        self.amf_files = {_amf_name(d): _tarball(d) for d in amf_days}
        self.on_query = on_query
        self.gdelt_calls: list[dict] = []
        self.urls: list[str] = []

    def __call__(self, url, params=None, timeout=None):
        self.urls.append(url)
        if url == gdelt.GDELT_URL:
            params = dict(params or {})
            self.gdelt_calls.append(params)
            if self.on_query:
                self.on_query(params)
            day = params["startdatetime"][:8]
            if day in self.bad_days:
                return FakeResponse(status_code=503)
            name = params["query"].split('"')[1]
            arts = [
                {
                    "url": f"https://n.example/{day}/{name.replace(' ', '')}/{i}",
                    "title": f"{name} synthetic {i}",
                    "seendate": f"{day}T101500Z",
                }
                for i in range(2)
            ]
            return FakeResponse(text=json.dumps({"articles": arts}))
        if url == amf.AMF_LISTING_URL:
            html = "".join(f'<a href="{n}">{n}</a>' for n in self.amf_files)
            return FakeResponse(text=html, content_type="text/html")
        name = url.rsplit("/", 1)[-1]
        if name in self.amf_files:
            return FakeResponse(content=self.amf_files[name], content_type="application/gzip")
        return FakeResponse(status_code=404)


@pytest.fixture
def seed(tmp_path):
    path = tmp_path / "seed.csv"
    rows = [
        "DE0007164600,Alpha SE,DE,XETR,,,Alpha SE,,,test,2026-10-20",
        "FR0000120271,Beta SA,FR,XPAR,,,Beta SA,,,test,2026-10-20",
    ]
    path.write_text("\n".join([",".join(COLUMNS), *rows]) + "\n", encoding="utf-8")
    return str(path)


def _main(argv, net, *, now=NOW, clock=None, **kw):
    return cli.main(
        argv,
        environ=kw.pop("environ", {}),
        get=net,
        now=lambda: now,
        clock=clock or (lambda: 0.0),
        load_env=False,
        sleep=lambda _s: None,
        **kw,
    )


def _lines(source, day):
    path = archive_base() / source / f"{day:%Y}" / f"{day:%m}" / f"{day.isoformat()}.jsonl"
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def test_run_collects_three_days_then_nothing(seed):
    net = FakeNet()
    assert _main(["run", "--catch-up", "--start", "2026-10-18", "--seed", seed], net) == 0
    for day in DAYS:
        for source in ("gdelt", "amf"):
            assert read_day_status(archive_base(), source, day).status == "ok", (source, day)
        assert len(_lines("gdelt", day)) == 4
        assert len(_lines("amf", day)) == 1
    assert (archive_base() / "heartbeat.json").exists()
    net2 = FakeNet()
    assert _main(["run", "--seed", seed], net2) == 0
    assert net2.urls == []
    assert all(len(_lines("gdelt", d)) == 4 for d in DAYS)


def test_failed_day_is_reported_and_caught_up(seed, capsys):
    assert _main(["run", "--start", "2026-10-18", "--seed", seed], FakeNet(bad_days=[DAYS[1]])) == 2
    capsys.readouterr()
    assert _main(["status", "--days", "14"], FakeNet()) == 1
    out = capsys.readouterr().out
    assert "2026-10-19" in out and "missing" in out
    net = FakeNet()
    assert _main(["run", "--seed", seed], net) == 0
    assert {c["startdatetime"][:8] for c in net.gdelt_calls} == {"20261019"}
    assert read_day_status(archive_base(), "gdelt", DAYS[1]).status == "ok"


def test_broken_day_gives_up_after_three_days_of_attempts(seed, capsys):
    bad = DAYS[1]
    args = ["run", "--start", "2026-10-18", "--seed", seed, "--sources", "gdelt"]
    assert _main(args, FakeNet(bad_days=[bad])) == 2
    assert _main(args, FakeNet(bad_days=[bad]), now=NOW + timedelta(hours=5)) == 2
    assert read_day_status(archive_base(), "gdelt", bad).attempts == 1  # same UTC day
    for offset in (1, 2):
        _main(args, FakeNet(bad_days=[bad]), now=NOW + timedelta(days=offset))
    assert read_day_status(archive_base(), "gdelt", bad).attempts == 3
    net = FakeNet(bad_days=[bad])
    _main(args, net, now=NOW + timedelta(days=3))
    assert "20261019" not in {c["startdatetime"][:8] for c in net.gdelt_calls}
    capsys.readouterr()
    _main(["status"], FakeNet(), now=NOW + timedelta(days=3))
    out = capsys.readouterr().out
    assert "aufgegeben" in out and "2026-10-19.json" in out


def test_status_without_finished_run_is_2(seed):
    assert _main(["status"], FakeNet()) == 2
    write_heartbeat(archive_base(), {"started_at": NOW.isoformat(), "finished_at": None})
    assert _main(["status"], FakeNet()) == 2


def test_run_with_held_lock_is_3(seed):
    base = archive_base()
    base.mkdir(parents=True, exist_ok=True)
    (base / "run.lock").write_text(
        json.dumps({"pid": 4242, "ts": (NOW - timedelta(hours=1)).isoformat()}), encoding="utf-8"
    )
    assert _main(["run", "--seed", seed], FakeNet(), pid_alive=lambda _p: True) == 3


def test_missing_ca_bundle_is_4(seed, tmp_path):
    environ = {"REQUESTS_CA_BUNDLE": str(tmp_path / "missing.pem")}
    assert _main(["run", "--seed", seed], FakeNet(), environ=environ) == 4


def test_smoke_writes_only_to_smoke_area(seed, capsys):
    assert _main(["smoke", "--issuers", "2", "--seed", seed], FakeNet()) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["gdelt"]["http_ok"] and summary["gdelt"]["new"] == 2
    assert summary["amf"]["files"] == 3 and summary["amf"]["listing_ok"]
    base = archive_base()
    assert (base / "smoke" / "index.sqlite").exists()
    assert (base / "smoke" / "gdelt").is_dir()
    for name in ("index.sqlite", "gdelt", "amf", "status", "heartbeat.json", "meta.json"):
        assert not (base / name).exists(), name


def test_max_runtime_ends_cleanly(seed):
    clock = {"t": 0.0}

    def on_query(params):
        if "Alpha SE" in params["query"]:
            clock["t"] = 10_000.0

    net = FakeNet(on_query=on_query)
    code = _main(
        ["run", "--start", "2026-10-20", "--seed", seed, "--max-runtime", "1"],
        net,
        clock=lambda: clock["t"],
    )
    assert code == 1
    st = read_day_status(archive_base(), "gdelt", DAYS[2])
    assert st.status == "partial" and "max_runtime" in st.errors and st.attempts == 0
    assert read_day_status(archive_base(), "amf", DAYS[2]).attempts == 0
    base = archive_base()
    assert not (base / "run.lock").exists()
    (base / "logs" / "news_archive.log").unlink()  # handlers closed, file not held open


def test_backfill_needs_archive_start(seed):
    assert _main(["backfill", "--source", "gdelt", "--seed", seed], FakeNet()) == 4


def test_amf_backfill_stops_before_archive_start(seed):
    base = archive_base()
    ensure_archive_start(base, date(2026, 10, 18))
    net = FakeNet(amf_days=[date(2026, 10, 16), date(2026, 10, 18)])
    assert _main(["backfill", "--source", "amf", "--since", "2026-10-15"], net) == 0
    assert _amf_name(date(2026, 10, 16)) in " ".join(net.urls)
    assert _amf_name(date(2026, 10, 18)) not in " ".join(net.urls)
    for day in (15, 16, 17):
        assert read_day_status(base, "amf", date(2026, 10, day)).status == "ok"
    assert read_day_status(base, "amf", date(2026, 10, 18)).errors == ["no status file"]
    rows = [json.loads(line) for line in _lines("amf", date(2026, 10, 16))]
    assert rows and all(r["backfilled"] for r in rows)


def test_scheduler_script_registers_only_with_switch():
    text = (ROOT / "scripts" / "news_archive_task.ps1").read_text(encoding="utf-8")
    for needle in (
        "StartWhenAvailable",
        "IgnoreNew",
        "-WorkingDirectory",
        "06:30",
        "run --catch-up",
    ):
        assert needle in text, needle
    assert "RestartCount" not in text and "RestartInterval" not in text
    guard = text.index("if ($Register)")
    assert text.index("Register-ScheduledTask") > guard
