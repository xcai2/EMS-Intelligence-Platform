"""
Search queries for the Analyst View live feed (Brave-backed web snippets).
Keep queries targeted toward recent analyst activity and EMS sector coverage.
"""

ANALYST_SIGNAL_QUERIES: list[str] = [
    # Recent rating / price-target actions across EMS names
    "Flex Jabil Celestica Sanmina Plexus analyst upgrade downgrade price target brokerage 2025",
    # Earnings-season analyst commentary, narrowed toward sell-side notes
    "EMS electronics manufacturing analyst note price target brokerage earnings outlook 2025",
    # Sector-level sell-side research rather than general company news
    "electronics manufacturing services Wall Street analyst rating outlook price target",
    # Hyperscaler CapEx and AI infrastructure analyst views
    "hyperscaler analyst forecast price target AI infrastructure CapEx Amazon Microsoft Google",
    # Broad EMS sell-side mentions with explicit analyst intent
    "Celestica Jabil Flex Sanmina Plexus sell-side analyst rating note brokerage",
]
