"""Company identity and alias-query helpers for News pipelines."""

from __future__ import annotations

from backend.core.config import COMPANIES
from backend.news.sources import OFFICIAL_COMPANY_SOURCES


DEFAULT_COMPANY_ALIAS_QUERY_LIMIT = 3
COMPANY_OFFICIAL_SITE_QUERY_SUFFIX = (
    '("news" OR "press release" OR announcement OR earnings OR "investor relations" '
    'OR newsroom OR "media center")'
)


def company_short_names() -> dict[str, str]:
    """Return ticker -> short company label mappings used in content heuristics."""
    return {ticker: config["name"].split()[0] for ticker, config in COMPANIES.items()}


def get_company_aliases(ticker: str, company_name: str) -> list[str]:
    """Build the ordered alias list used across company matching and query fan-out."""
    source = OFFICIAL_COMPANY_SOURCES.get(ticker, {})
    aliases = source.get("aliases") or []
    base = [company_name, company_name.split()[0], ticker]
    merged = [term.strip() for term in [*base, *aliases] if term and term.strip()]
    deduped: list[str] = []
    seen = set()
    for term in merged:
        key = term.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(term)
    return deduped


def build_company_alias_query(
    ticker: str,
    company_name: str,
    limit: int = DEFAULT_COMPANY_ALIAS_QUERY_LIMIT,
) -> str:
    """Build an OR-joined alias query block for external search sources."""
    aliases = get_company_aliases(ticker, company_name)
    quoted_aliases = [f'"{alias}"' if " " in alias else alias for alias in aliases[:limit]]
    return " OR ".join(quoted_aliases)


def build_company_site_query(
    ticker: str,
    company_name: str,
    domain: str,
    limit: int = DEFAULT_COMPANY_ALIAS_QUERY_LIMIT,
) -> str:
    """Build the site-scoped official query used for Google News RSS on company domains."""
    alias_or = build_company_alias_query(ticker, company_name, limit=limit)
    cleaned_alias_or = " ".join((alias_or or "").split()).strip()
    if not cleaned_alias_or:
        return ""
    return f"site:{domain} ({cleaned_alias_or}) {COMPANY_OFFICIAL_SITE_QUERY_SUFFIX}"
