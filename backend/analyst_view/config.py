"""
Search queries for the Analyst View live feed (Brave-backed web snippets).
Keep queries targeted toward recent analyst activity and EMS sector coverage.
"""

ANALYST_SIGNAL_QUERIES: list[str] = [
    # Recent rating / price-target actions across EMS names
    "Flex Jabil Celestica Sanmina Plexus analyst upgrade downgrade 2025",
    # Earnings season analyst commentary
    "EMS electronics manufacturing earnings analyst note price target 2025",
    # Sector-level sell-side research
    "electronics manufacturing services Wall Street research coverage outlook",
    # Hyperscaler CapEx and AI infrastructure analyst views
    "hyperscaler CapEx AI infrastructure analyst forecast 2025 Amazon Microsoft Google",
    # Broad EMS sell-side mentions
    "Celestica Jabil Flex Sanmina Plexus analyst note rating",
]
