"""Keyword-based display category classification (Phase 1).

Phase 1 rule: fixed keyword matching only — no LLM, no vector search.

Matching order per article:
  1. title (case-insensitive substring)
  2. description (case-insensitive substring)
  3. intent / url / source used only as weak auxiliary signals

An article can match multiple categories simultaneously.
Articles that match nothing receive an empty categories list [].

Fixed category enum (these are the only valid values for NewsItem.categories):
  ai_data_center         — AI, data center, server, networking, storage, liquid cooling
  supply_chain           — supply chain, logistics, components, delivery
  manufacturing_operations — factory, manufacturing, automation, capacity, expansion
  earnings_financials    — earnings, revenue, guidance, profit, quarterly
  strategy_partnerships  — partnership, acquisition, customer program, restructuring
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Keyword tables — maintain these directly; do not make them runtime-configurable
# ---------------------------------------------------------------------------

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "ai_data_center": [
        "artificial intelligence",
        " ai ",          # space-padded to avoid matching "rail", "mail", etc.
        "data center",
        "datacenter",
        "server",
        "storage",
        "networking",
        "liquid cooling",
        "immersion cooling",
        "hyperscaler",
        "hyperscale",
        "cloud computing",
        "gpu",
        "semiconductor",
    ],
    "supply_chain": [
        "supply chain",
        "logistics",
        "component",
        "delivery",
        "bottleneck",
        "inventory",
        "procurement",
        "sourcing",
    ],
    "manufacturing_operations": [
        "factory",
        "manufacturing",
        "automation",
        "capacity",
        "expansion",
        "production",
        "assembly",
        "plant",
        "operations",
        "facility",
    ],
    "earnings_financials": [
        "earnings",
        "revenue",
        "guidance",
        "profit",
        "quarterly",
        "fiscal",
        "results",
        "outlook",
        "eps",
        "forecast",
        "financial",
        "income",
    ],
    "strategy_partnerships": [
        "partnership",
        "acquisition",
        "customer",
        "program",
        "restructuring",
        "merger",
        "agreement",
        "deal",
        "contract",
        "collaborate",
        "joint venture",
        "strategic",
        "divest",
    ],
}


def classify_article(
    title: str,
    description: str,
    intent: str | None = None,
    url: str = "",
    source: str = "",
) -> list[str]:
    """Return the list of matching category labels for a single news article.

    Matching is case-insensitive. The primary signal is title + description.
    intent / url / source are used only as weak auxiliary fallback.
    """
    title_text = f" {title.lower()} "
    desc_text = f" {description.lower()} "
    aux_text = f" {(intent or '').lower()} {url.lower()} {source.lower()} "

    matched: list[str] = []

    for category, keywords in CATEGORY_KEYWORDS.items():
        # Step 1: title only
        hit = any(kw in title_text for kw in keywords)
        # Step 2: description (only if title miss)
        if not hit:
            hit = any(kw in desc_text for kw in keywords)
        # Step 3: weak auxiliary (intent / url / source)
        if not hit:
            hit = any(kw in aux_text for kw in keywords)
        if hit:
            matched.append(category)

    return matched
