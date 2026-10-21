"""Seed universe of the archive: the issuers GDELT is queried for."""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from pathlib import Path

from tradingagents.forecast.archive.store import archive_base

COLUMNS = (
    "isin",
    "name",
    "country",
    "primary_mic",
    "lei",
    "adt_eur",
    "aliases",
    "negative_terms",
    "gdelt_langs",
    "source",
    "as_of",
)

PROVISIONAL_SEED = Path(__file__).with_name("seed_universe_provisional.csv")

_ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")


class SeedError(ValueError):
    """The seed file is malformed (the message names the line)."""


@dataclass(frozen=True)
class SeedIssuer:
    isin: str
    name: str
    country: str
    primary_mic: str = ""
    lei: str = ""
    adt_eur: float | None = None
    aliases: tuple[str, ...] = ()
    negative_terms: tuple[str, ...] = ()
    gdelt_langs: tuple[str, ...] = ()
    source: str = ""
    as_of: str = ""

    @property
    def key(self) -> str:
        return self.isin if self.isin else f"name:{self.name.casefold()}"


def isin_is_valid(isin: str) -> bool:
    """ISO 6166 check: format plus Luhn over the letters-as-numbers digit string."""
    if not isin or not _ISIN_RE.match(isin):
        return False
    digits = "".join(str(int(ch, 36)) for ch in isin)
    total = 0
    for index, ch in enumerate(reversed(digits)):
        value = int(ch)
        if index % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def isin_country(country: str) -> str:
    """The ISIN prefix of a seed country (UK rows carry GB ISINs)."""
    return "GB" if country == "UK" else country


def _split(value: str | None) -> tuple[str, ...]:
    return tuple(part.strip() for part in (value or "").split("|") if part.strip())


def load_seed(path) -> list[SeedIssuer]:
    """Read a seed CSV (utf-8; lines starting with ``#`` are comments)."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    numbered = [(n, line) for n, line in enumerate(lines, 1) if not line.lstrip().startswith("#")]
    numbered = [(n, line) for n, line in numbered if line.strip()]
    if not numbered:
        raise SeedError(f"{path}: no header line")
    header_no, header = numbered[0]
    columns = next(csv.reader([header]))
    missing = [c for c in COLUMNS if c not in columns]
    if missing:
        raise SeedError(f"{path}: line {header_no}: missing columns {missing}")
    issuers: list[SeedIssuer] = []
    isins: set[str] = set()
    names: set[str] = set()
    for line_no, line in numbered[1:]:
        values = next(csv.reader([line]))
        row = dict(zip(columns, values, strict=False))
        isin = (row.get("isin") or "").strip().upper()
        name = (row.get("name") or "").strip()
        source = (row.get("source") or "").strip()
        if not name:
            raise SeedError(f"{path}: line {line_no}: empty name")
        if isin and not isin_is_valid(isin):
            raise SeedError(f"{path}: line {line_no}: invalid ISIN {isin}")
        if isin and isin in isins:
            raise SeedError(f"{path}: line {line_no}: duplicate ISIN {isin}")
        if name.casefold() in names:
            raise SeedError(f"{path}: line {line_no}: duplicate name {name}")
        if not source:
            raise SeedError(f"{path}: line {line_no}: empty source")
        adt = (row.get("adt_eur") or "").strip()
        try:
            adt_value = float(adt) if adt else None
        except ValueError:
            raise SeedError(f"{path}: line {line_no}: bad adt_eur {adt}") from None
        if isin:
            isins.add(isin)
        names.add(name.casefold())
        issuers.append(
            SeedIssuer(
                isin=isin,
                name=name,
                country=(row.get("country") or "").strip().upper(),
                primary_mic=(row.get("primary_mic") or "").strip(),
                lei=(row.get("lei") or "").strip(),
                adt_eur=adt_value,
                aliases=_split(row.get("aliases")) or (name,),
                negative_terms=_split(row.get("negative_terms")),
                gdelt_langs=_split(row.get("gdelt_langs")),
                source=source,
                as_of=(row.get("as_of") or "").strip(),
            )
        )
    return issuers


def dump_seed(path, issuers, comments=()) -> None:
    """Write issuers in the seed CSV schema, with ``# `` comment lines on top."""
    buffer = io.StringIO()
    for comment in comments:
        buffer.write(f"# {comment}\n")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(COLUMNS)
    for issuer in issuers:
        writer.writerow(
            [
                issuer.isin,
                issuer.name,
                issuer.country,
                issuer.primary_mic,
                issuer.lei,
                "" if issuer.adt_eur is None else f"{issuer.adt_eur:.0f}",
                "|".join(issuer.aliases),
                "|".join(issuer.negative_terms),
                "|".join(issuer.gdelt_langs),
                issuer.source,
                issuer.as_of,
            ]
        )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(buffer.getvalue(), encoding="utf-8")


def default_seed_path(environ=None) -> Path:
    """The built seed under the archive base if present, else the provisional one."""
    built = archive_base(environ) / "seed_universe.csv"
    return built if built.exists() else PROVISIONAL_SEED
