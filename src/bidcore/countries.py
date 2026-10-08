"""Country codes at the agent boundary: whatever an agent sends ('KSA', 'EGY', 'Saudi Arabia', 'uk'),
the ledger and the catalogue only ever see ISO-2 codes.

The third live run passed 'KSA' / 'EGY' to the catalogue tools; they answered "available in NONE of the
requested" for every item, so the catalogue-mapper recorded scope_items as empty. Every tool and validator
that takes countries resolves them here first: a known country becomes its ISO-2 code; one that is not a
catalogue country is reported as unsupported (dropped with a note); an unknown string is reported as such.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

# ISO-2 -> (ISO-3, names / common aliases). Covers the catalogue countries plus the countries RFPs in
# this practice name next to them; anything else is "unknown" and reported back to the agent.
_COUNTRIES: dict[str, tuple[str, tuple[str, ...]]] = {
    "AE": ("ARE", ("United Arab Emirates", "UAE", "Emirates")),
    "AT": ("AUT", ("Austria",)),
    "AU": ("AUS", ("Australia",)),
    "BE": ("BEL", ("Belgium",)),
    "BR": ("BRA", ("Brazil",)),
    "CA": ("CAN", ("Canada",)),
    "CH": ("CHE", ("Switzerland",)),
    "CN": ("CHN", ("China", "PRC")),
    "CZ": ("CZE", ("Czech Republic", "Czechia")),
    "DE": ("DEU", ("Germany",)),
    "DK": ("DNK", ("Denmark",)),
    "ES": ("ESP", ("Spain",)),
    "FI": ("FIN", ("Finland",)),
    "FR": ("FRA", ("France",)),
    "GB": ("GBR", ("United Kingdom", "UK", "Great Britain", "Britain", "England")),
    "HK": ("HKG", ("Hong Kong",)),
    "HU": ("HUN", ("Hungary",)),
    "ID": ("IDN", ("Indonesia",)),
    "IE": ("IRL", ("Ireland",)),
    "IN": ("IND", ("India",)),
    "IT": ("ITA", ("Italy",)),
    "JP": ("JPN", ("Japan",)),
    "KR": ("KOR", ("South Korea", "Korea", "Republic of Korea")),
    "LU": ("LUX", ("Luxembourg",)),
    "MX": ("MEX", ("Mexico",)),
    "MY": ("MYS", ("Malaysia",)),
    "NL": ("NLD", ("Netherlands", "Holland")),
    "NO": ("NOR", ("Norway",)),
    "NZ": ("NZL", ("New Zealand",)),
    "PH": ("PHL", ("Philippines",)),
    "PL": ("POL", ("Poland",)),
    "PT": ("PRT", ("Portugal",)),
    "RO": ("ROU", ("Romania",)),
    "RU": ("RUS", ("Russia", "Russian Federation")),
    "SA": ("SAU", ("Saudi Arabia", "KSA", "Kingdom of Saudi Arabia", "Saudi")),
    "SE": ("SWE", ("Sweden",)),
    "SG": ("SGP", ("Singapore",)),
    "SK": ("SVK", ("Slovakia",)),
    "TH": ("THA", ("Thailand",)),
    "TR": ("TUR", ("Turkey", "Turkiye")),
    "TW": ("TWN", ("Taiwan",)),
    "US": ("USA", ("United States", "United States of America", "USA", "America")),
    "ZA": ("ZAF", ("South Africa",)),
    # not catalogue countries, but named in RFPs alongside them
    "BH": ("BHR", ("Bahrain",)),
    "DZ": ("DZA", ("Algeria",)),
    "EG": ("EGY", ("Egypt",)),
    "IQ": ("IRQ", ("Iraq",)),
    "JO": ("JOR", ("Jordan",)),
    "KE": ("KEN", ("Kenya",)),
    "KW": ("KWT", ("Kuwait",)),
    "LB": ("LBN", ("Lebanon",)),
    "LK": ("LKA", ("Sri Lanka",)),
    "MA": ("MAR", ("Morocco",)),
    "NG": ("NGA", ("Nigeria",)),
    "OM": ("OMN", ("Oman",)),
    "PK": ("PAK", ("Pakistan",)),
    "QA": ("QAT", ("Qatar",)),
    "TN": ("TUN", ("Tunisia",)),
    "VN": ("VNM", ("Vietnam", "Viet Nam")),
    "BD": ("BGD", ("Bangladesh",)),
}


def _key(value: str) -> str:
    return re.sub(r"[^a-z]", "", value.lower())


_LOOKUP: dict[str, str] = {}
for _iso2, (_iso3, _names) in _COUNTRIES.items():
    for _alias in (_iso2, _iso3, *_names):
        _LOOKUP.setdefault(_key(_alias), _iso2)


def to_iso2(value: str) -> str | None:
    """ISO-2 code for a code or name in any common form; None when the country is not known."""
    text = str(value or "").strip()
    if not text:
        return None
    if text.upper().startswith("OTHER:"):
        return None
    return _LOOKUP.get(_key(text))


@dataclass
class CountryCheck:
    codes: list[str] = field(default_factory=list)        # allowed ISO-2 codes, deduplicated, input order
    unsupported: list[str] = field(default_factory=list)  # known countries that are not catalogue countries
    unknown: list[str] = field(default_factory=list)      # strings that name no country we know
    renamed: list[str] = field(default_factory=list)      # "KSA -> SA" for the notes

    def note(self) -> str:
        parts = []
        if self.renamed:
            parts.append("country codes normalised: " + ", ".join(self.renamed))
        if self.unsupported:
            parts.append(f"{self.unsupported} are not catalogue countries (no SAP Best Practice availability) "
                         "and were left out")
        if self.unknown:
            parts.append(f"{self.unknown} are not recognised countries; use ISO-2 codes")
        return "; ".join(parts)


def check_countries(values: Iterable[str] | None, allowed: Iterable[str]) -> CountryCheck:
    allowed_set = {a.upper() for a in allowed}
    out = CountryCheck()
    for raw in values or []:
        text = str(raw or "").strip()
        if not text:
            continue
        code = to_iso2(text)
        if code is None:
            out.unknown.append(text)
            continue
        if text.upper() != code:
            out.renamed.append(f"{text} -> {code}")
        if code not in allowed_set:
            if code not in out.unsupported:
                out.unsupported.append(code)
        elif code not in out.codes:
            out.codes.append(code)
    return out
