"""Build the archive's seed universe from locally downloaded ESMA FITRS/FIRDS files.

Inputs are ESMA FITRS ``FULECR`` (equity transparency results: liquidity flag, average
daily turnover, most relevant market) and FIRDS ``FULINS_E`` (reference data: full name,
CFI, issuer LEI, venue MIC), as XML or ZIP files holding XML. This script downloads
nothing from ESMA; scripts/NEWS_ARCHIVE.md describes the download.

The file and field names (FITRS ``Id``/``Lqdty``/``AvrgDalyTrnvr``/``MstRlvntMkt/Id``,
FIRDS ``FinInstrmGnlAttrbts/Id``/``FullNm``/``ClssfctnTp``/``Issr``/
``TradgVnRltdAttrbts/Id``) are assumption A3 of the research: check them against
ESMA65-8-5240 before the first real run. Parsing is streaming and namespace-agnostic.

The output (default ``%LOCALAPPDATA%\\TradingEngineX\\archive\\seed_universe.csv``) stays
outside the repository; an ESMA-derived file enters the repo only after operator review.
"""

from __future__ import annotations

import argparse
import io
import logging
import sys
import xml.etree.ElementTree as ET
import zipfile
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tradingagents.forecast.archive.http import (  # noqa: E402
    FetchError,
    RateLimiter,
    get_with_retry,
    make_session,
    resolve_ca_bundle,
)
from tradingagents.forecast.archive.seed import (  # noqa: E402
    SeedIssuer,
    dump_seed,
    load_seed,
)
from tradingagents.forecast.archive.store import archive_base  # noqa: E402

log = logging.getLogger("build_seed_universe")

GLEIF_URL = "https://api.gleif.org/api/v1/lei-records/{lei}"
ESMA_ATTRIBUTION = (
    "Source: ESMA (registers.esma.europa.eu) - derived from ESMA FITRS/FIRDS, transformed"
)
GLEIF_ATTRIBUTION = "Issuer legal names: GLEIF LEI data (CC0)"

LANGS = {
    "DE": ("german", "english"),
    "AT": ("german", "english"),
    "FR": ("french", "english"),
    "BE": ("french", "dutch", "english"),
    "NL": ("dutch", "english"),
    "IT": ("italian", "english"),
    "ES": ("spanish", "english"),
    "PT": ("portuguese", "english"),
    "CH": ("german", "french", "english"),
    "UK": ("english",),
    "IE": ("english",),
}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child(element, name):
    for child in element:
        if _local(child.tag) == name:
            return child
    return None


def _find(element, *path):
    """First descendant matching the local-name path (searched at any depth for the head)."""
    for candidate in element.iter():
        if _local(candidate.tag) != path[0]:
            continue
        node = candidate
        for name in path[1:]:
            node = _child(node, name)
            if node is None:
                break
        if node is not None:
            return node
    return None


def _text(node) -> str:
    return (node.text or "").strip() if node is not None else ""


def _xml_streams(path):
    path = Path(path)
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                if name.lower().endswith(".xml"):
                    with archive.open(name) as handle:
                        yield io.BytesIO(handle.read())
    else:
        with open(path, "rb") as handle:
            yield handle


def parse_fitrs(paths) -> dict[str, dict]:
    """ISIN -> {liquid, adt, mic} from FITRS equity transparency records."""
    result: dict[str, dict] = {}
    for path in paths:
        for stream in _xml_streams(path):
            for _event, element in ET.iterparse(stream, events=("end",)):
                if _child(element, "Lqdty") is None:
                    continue
                isin = _text(_child(element, "Id"))
                if not isin:
                    element.clear()
                    continue
                adt_text = _text(_find(element, "AvrgDalyTrnvr"))
                try:
                    adt = float(adt_text) if adt_text else 0.0
                except ValueError:
                    adt = 0.0
                result[isin] = {
                    "liquid": _text(_child(element, "Lqdty")).lower() in ("true", "1"),
                    "adt": adt,
                    "mic": _text(_find(element, "MstRlvntMkt", "Id")),
                }
                element.clear()
    return result


def parse_firds(paths) -> dict[str, dict]:
    """ISIN -> {name, cfi, lei, mic} from FIRDS reference data (first venue wins)."""
    result: dict[str, dict] = {}
    for path in paths:
        for stream in _xml_streams(path):
            for _event, element in ET.iterparse(stream, events=("end",)):
                if _child(element, "Issr") is None:
                    continue
                general = _find(element, "FinInstrmGnlAttrbts")
                isin = _text(_child(general, "Id")) if general is not None else ""
                if isin and isin not in result:
                    result[isin] = {
                        "name": _text(_find(element, "FullNm")),
                        "cfi": _text(_find(element, "ClssfctnTp")),
                        "lei": _text(_child(element, "Issr")),
                        "mic": _text(_find(element, "TradgVnRltdAttrbts", "Id")),
                    }
                element.clear()
    return result


def _gleif_name(lei, gleif_get, limiter) -> str | None:
    try:
        response = get_with_retry(gleif_get, GLEIF_URL.format(lei=lei), limiter=limiter)
        data = response.json()
        return data["data"]["attributes"]["entity"]["legalName"]["name"]
    except (FetchError, ValueError, KeyError, TypeError) as exc:
        log.warning("GLEIF lookup failed for %s: %s", lei, exc)
        return None


def build(fitrs_paths, firds_paths, *, top, manual=None, gleif_get=None) -> list[SeedIssuer]:
    fitrs = parse_fitrs(fitrs_paths)
    firds = parse_firds(firds_paths)
    as_of = datetime.now(UTC).date().isoformat()
    limiter = RateLimiter(1.0)
    rows = []
    for isin, trans in fitrs.items():
        ref = firds.get(isin)
        if not trans["liquid"] or ref is None or not ref["name"]:
            continue
        if not ref["cfi"].startswith("ES"):
            continue
        rows.append((trans["adt"], isin, trans, ref))
    rows.sort(key=lambda row: (-row[0], row[1]))
    issuers: list[SeedIssuer] = []
    names: set[str] = set()
    for adt, isin, trans, ref in rows[:top]:
        prefix = isin[:2]
        country = "UK" if prefix == "GB" else prefix
        aliases = [ref["name"]]
        if gleif_get is not None and ref["lei"]:
            legal = _gleif_name(ref["lei"], gleif_get, limiter)
            if legal and legal.casefold() != ref["name"].casefold():
                aliases.append(legal)
        if ref["name"].casefold() in names:
            continue
        names.add(ref["name"].casefold())
        issuers.append(
            SeedIssuer(
                isin=isin,
                name=ref["name"],
                country=country,
                primary_mic=trans["mic"] or ref["mic"],
                lei=ref["lei"],
                adt_eur=adt,
                aliases=tuple(aliases),
                gdelt_langs=LANGS.get(country, ("english",)),
                source="esma-fitrs-firds",
                as_of=as_of,
            )
        )
    if manual:
        overrides = {m.isin: m for m in manual if m.isin}
        issuers = [overrides.pop(i.isin, i) for i in issuers]
        known = {i.name.casefold() for i in issuers}
        for extra in manual:
            if (extra.isin and extra.isin in overrides) or (
                not extra.isin and extra.name.casefold() not in known
            ):
                issuers.append(extra)
    return issuers


def main(argv=None, *, environ=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fitrs", action="append", default=[], help="FITRS FULECR XML/ZIP")
    parser.add_argument("--firds", action="append", default=[], help="FIRDS FULINS_E XML/ZIP")
    parser.add_argument("--top", type=int, default=400)
    parser.add_argument("--manual", help="CSV in seed schema (UK rows, alias overrides)")
    parser.add_argument("--gleif", action="store_true", help="add GLEIF legal names")
    parser.add_argument("--out", help="output CSV (default: archive base)")
    args = parser.parse_args(argv)
    if not args.fitrs or not args.firds:
        parser.error("--fitrs and --firds are required")
    gleif_get = None
    if args.gleif:
        import os

        gleif_get = make_session(resolve_ca_bundle(environ or os.environ)).get
    manual = load_seed(args.manual) if args.manual else None
    issuers = build(args.fitrs, args.firds, top=args.top, manual=manual, gleif_get=gleif_get)
    out = Path(args.out) if args.out else archive_base(environ) / "seed_universe.csv"
    comments = [ESMA_ATTRIBUTION]
    if args.gleif:
        comments.append(GLEIF_ATTRIBUTION)
    comments.append(f"built {datetime.now(UTC).isoformat()} by scripts/build_seed_universe.py")
    dump_seed(out, issuers, comments)
    print(f"wrote {len(issuers)} issuers to {out}")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
