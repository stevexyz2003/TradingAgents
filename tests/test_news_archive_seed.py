"""Seed universe: ISIN check, loader, provisional seed and the ESMA seed builder."""

from __future__ import annotations

import importlib.util
from collections import Counter
from pathlib import Path

import pytest

from tradingagents.forecast.archive import seed as aseed
from tradingagents.forecast.archive.store import archive_base

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
HEADER = ",".join(aseed.COLUMNS)


def _load_builder():
    spec = importlib.util.spec_from_file_location(
        "build_seed_universe", ROOT / "scripts" / "build_seed_universe.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(tmp_path, *rows, name="seed.csv"):
    path = tmp_path / name
    path.write_text("\n".join(["# comment", HEADER, *rows]) + "\n", encoding="utf-8")
    return path


ROW_SAP = "DE0007164600,SAP SE,DE,XETR,,,SAP SE|SAP,,german|english,test,2026-10-20"


def test_isin_is_valid():
    assert aseed.isin_is_valid("DE0007164600")
    assert not aseed.isin_is_valid("DE0007164601")
    assert not aseed.isin_is_valid("DE000716460")
    assert not aseed.isin_is_valid("")


def test_load_seed_parses_rows(tmp_path):
    path = _write(tmp_path, ROW_SAP, ",Some Unknown Co,FR,XPAR,,,,,french,test,2026-10-20")
    issuers = aseed.load_seed(path)
    assert issuers[0].aliases == ("SAP SE", "SAP")
    assert issuers[0].gdelt_langs == ("german", "english")
    assert issuers[0].key == "DE0007164600"
    assert issuers[1].isin == "" and issuers[1].key == "name:some unknown co"
    assert issuers[1].aliases == ("Some Unknown Co",)


@pytest.mark.parametrize(
    "rows, message",
    [
        (["DE0007164601,Bad,DE,,,,,,,test,"], "line 3: invalid ISIN"),
        ([ROW_SAP, ROW_SAP.replace("SAP SE,DE", "Other,DE")], "line 4: duplicate ISIN"),
        ([ROW_SAP, ",SAP SE,DE,,,,,,,test,"], "line 4: duplicate name"),
        ([",No Source,DE,,,,,,,,"], "line 3: empty source"),
    ],
)
def test_load_seed_errors(tmp_path, rows, message):
    with pytest.raises(aseed.SeedError, match=message):
        aseed.load_seed(_write(tmp_path, *rows))


def test_provisional_seed_is_consistent():
    text = aseed.PROVISIONAL_SEED.read_text(encoding="utf-8")
    assert "PROVISIONAL" in text.splitlines()[0]
    issuers = aseed.load_seed(aseed.PROVISIONAL_SEED)
    assert 55 <= len(issuers) <= 70
    counts = Counter(i.country for i in issuers)
    for country in ("DE", "FR", "NL", "IT", "ES", "CH", "UK"):
        assert counts[country] >= 5, country
    for issuer in issuers:
        assert issuer.source == "hand-curated-provisional"
        if issuer.isin:
            assert aseed.isin_is_valid(issuer.isin)
            assert issuer.isin[:2] == aseed.isin_country(issuer.country), issuer.name


def test_default_seed_path_prefers_built_seed():
    assert aseed.default_seed_path() == aseed.PROVISIONAL_SEED
    built = archive_base() / "seed_universe.csv"
    built.parent.mkdir(parents=True, exist_ok=True)
    built.write_text("x", encoding="utf-8")
    assert aseed.default_seed_path() == built


NS_T = "urn:iso:std:iso:20022:tech:xsd:auth.044.001.02"
NS_R = "urn:iso:std:iso:20022:tech:xsd:auth.017.001.02"


def _fitrs(rows):
    body = "".join(
        f"<EqtyTrnsprncyData><Id>{isin}</Id><Lqdty>{liq}</Lqdty>"
        f"<Sttstcs><AvrgDalyTrnvr>{adt}</AvrgDalyTrnvr></Sttstcs>"
        f"<MstRlvntMkt><Id>{mic}</Id></MstRlvntMkt></EqtyTrnsprncyData>"
        for isin, liq, adt, mic in rows
    )
    return f'<?xml version="1.0"?><Document xmlns="{NS_T}"><Rpt>{body}</Rpt></Document>'


def _firds(rows):
    body = "".join(
        f"<RefData><FinInstrmGnlAttrbts><Id>{isin}</Id><FullNm>{name}</FullNm>"
        f"<ClssfctnTp>{cfi}</ClssfctnTp></FinInstrmGnlAttrbts><Issr>{lei}</Issr>"
        f"<TradgVnRltdAttrbts><Id>XETR</Id></TradgVnRltdAttrbts></RefData>"
        for isin, name, cfi, lei in rows
    )
    return f'<?xml version="1.0"?><Document xmlns="{NS_R}"><Pyld>{body}</Pyld></Document>'


def test_build_seed_universe(tmp_path):
    builder = _load_builder()
    fitrs = tmp_path / "fitrs.xml"
    fitrs.write_text(
        _fitrs(
            [
                ("DE0007164600", "true", "500000000", "XETR"),
                ("FR0000120271", "true", "300000000", "XPAR"),
                ("DE0007236101", "false", "900000000", "XETR"),
                ("NL0010273215", "true", "800000000", "XAMS"),
                ("IT0003128367", "true", "100000000", "XMIL"),
            ]
        ),
        encoding="utf-8",
    )
    firds = tmp_path / "firds.xml"
    firds.write_text(
        _firds(
            [
                ("DE0007164600", "Synthetic Alpha SE", "ESVUFR", "LEI1"),
                ("FR0000120271", "Synthetic Beta SA", "ESVUFR", "LEI2"),
                ("DE0007236101", "Synthetic Gamma AG", "ESVUFR", "LEI3"),
                ("NL0010273215", "Synthetic Delta NV", "DBFTFR", "LEI4"),
                ("IT0003128367", "Synthetic Epsilon SpA", "ESVUFR", "LEI5"),
            ]
        ),
        encoding="utf-8",
    )
    manual = _write(
        tmp_path,
        "GB0009895292,Synthetic UK plc,UK,XLON,,,Synthetic UK,,english,manual,2026-10-20",
        name="manual.csv",
    )
    issuers = builder.build([fitrs], [firds], top=2, manual=aseed.load_seed(manual))
    assert [i.name for i in issuers] == [
        "Synthetic Alpha SE",
        "Synthetic Beta SA",
        "Synthetic UK plc",
    ]
    assert issuers[0].adt_eur == 500000000 and issuers[0].primary_mic == "XETR"
    assert issuers[1].country == "FR"

    assert builder.main(["--fitrs", str(fitrs), "--firds", str(firds), "--top", "3"]) == 0
    out = archive_base() / "seed_universe.csv"
    text = out.read_text(encoding="utf-8")
    assert "derived from ESMA FITRS/FIRDS, transformed" in text
    assert len(aseed.load_seed(out)) == 3
