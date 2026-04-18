"""New company onboarding: fixed rule query template generation (Phase 1).

Two-step flow (both steps are exposed as API endpoints in routes.py):

Step 1 — POST /api/news/companies/preview
    Accepts company info, applies fixed rules, returns 4 generated templates.
    Nothing is written to the database.

Step 2 — POST /api/news/companies
    Accepts (possibly human-edited) company info + templates and writes
    them to the database via registry.save_company().

Phase 1 rule: preview uses the same fixed template family as the formal
company templates — no LLM, no external calls.

The preview is still editable before confirmation, but it should already be
close to the Phase 1 "official" template style used by seeded companies.

Fixed generation rules (§6.2):
  official_name:    '"<full_name>" news'
  industry_news:    "<short_name> manufacturing <industry phrase> news"
                    (fallback: "<short_name> manufacturing supply chain news")
  stock_news:       <ticker> earnings results quarterly
  supporting_query: "<first_alias> news"
                    (fallback: "<short_name> <industry phrase> news")
"""

from __future__ import annotations

import logging

from backend.news.models import QueryTemplate

logger = logging.getLogger(__name__)

# Phase 3: raised from 40 to 50 (Brave News API max is 50 per request).
_COUNT_OFFICIAL = 50
_COUNT_DEFAULT = 50


def _derive_industry_phrase(industry: str) -> str:
    """Map operator input into a low-risk Phase 1 supporting phrase.

    The goal is not to infer a company-specific perfect query. The goal is to
    generate a stable default that looks like the current seeded templates:
    short company anchor + a lightweight manufacturing/domain phrase + news.
    """
    raw = (industry or "").strip()
    if not raw:
        return "supply chain"

    lowered = raw.lower()
    if lowered == "ems":
        return "supply chain"
    return lowered


def generate_template_preview(
    full_name: str,
    ticker: str,
    industry: str = "",
    aliases: str = "",
    **_kwargs,  # absorb extra keyword args for forward-compatibility
) -> list[dict]:
    """Generate 4 fixed query template drafts for a new company.

    Does NOT write to the database.
    Returns a list of dicts with keys: intent, query_template, freshness, count.
    """
    ticker = ticker.upper()
    name_quoted = f'"{full_name}"'

    # 1. official_name — company name + "news" ensures Brave returns articles, not profile pages
    official_name = f"{name_quoted} news"

    # 2. industry_news — seeded-company style: short anchor + manufacturing + domain phrase + news
    industry_phrase = _derive_industry_phrase(industry)
    short_name = full_name.split()[0]  # e.g. "Flex" from "Flex Ltd"
    industry_news = f"{short_name} manufacturing {industry_phrase} news"

    # 3. stock_news — earnings/results keywords target financial articles, not ticker aggregator pages
    stock_news = f"{ticker} earnings results quarterly"

    # 4. supporting_query — must include "news" signal word
    first_alias = ""
    if aliases:
        parts = [a.strip() for a in aliases.split(",") if a.strip()]
        # Skip aliases that look like exchange prefixes (e.g. "NYSE:JBL", "NASDAQ:FLEX")
        non_exchange = [a for a in parts if ":" not in a]
        if non_exchange:
            first_alias = non_exchange[0]

    if first_alias:
        supporting_query = f"{first_alias} news"
    else:
        supporting_query = f"{short_name} {industry_phrase} news"

    preview: list[dict] = [
        {"intent": "official_name",    "query_template": official_name,    "freshness": None, "count": _COUNT_OFFICIAL},
        {"intent": "industry_news",    "query_template": industry_news,    "freshness": None, "count": _COUNT_DEFAULT},
        {"intent": "stock_news",       "query_template": stock_news,       "freshness": None, "count": _COUNT_DEFAULT},
        {"intent": "supporting_query", "query_template": supporting_query, "freshness": None, "count": _COUNT_DEFAULT},
    ]

    logger.debug("Generated preview templates for %s: %s", ticker, [p["query_template"] for p in preview])
    return preview


def build_query_templates_from_preview(
    ticker: str,
    preview: list[dict],
) -> list[QueryTemplate]:
    """Convert a list of preview dicts (from the frontend) into QueryTemplate objects."""
    templates: list[QueryTemplate] = []
    for item in preview:
        intent = (item.get("intent") or "").strip()
        query_template = (item.get("query_template") or "").strip()
        if not intent or not query_template:
            continue
        templates.append(
            QueryTemplate(
                ticker=ticker.upper(),
                intent=intent,
                query_template=query_template,
                freshness=item.get("freshness") or None,
                count=int(item.get("count") or _COUNT_DEFAULT),
            )
        )
    return templates
