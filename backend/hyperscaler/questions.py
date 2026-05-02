BIG5_CAPEX_QUESTION = """
Search for the latest 2026 capital expenditure outlook for these five companies:
Amazon (AWS), Microsoft (Azure), Alphabet (Google Cloud), Meta, and Oracle (OCI).
Note: Oracle's fiscal year ends in May. For Oracle, use their FY2026 CapEx guidance (fiscal year ending May 2026).

For each company return ONLY:
- ticker and name
- 2026 full-year CapEx outlook in USD billions (single number or midpoint of range)
- YoY growth percentage (number only, no text)
- up to 6 AI focus areas (short phrases, no sentences)
- up to 5 recent announcements (one sentence each, max 150 characters)
- up to 5 key metrics (short label: short value)

For Stargate project return ONLY:
- total investment in USD billions
- up to 5 partners (names only)
- planned capacity in gigawatts
- up to 5 locations (city/state only)

Return JSON only. No markdown. No explanation. Do NOT include a sources field.
Use this exact structure:
{
  "companies": [
    {
      "ticker": "AMZN",
      "name": "Amazon",
      "capex_2026_billions": null,
      "yoy_growth_pct": null,
      "ai_focus_areas": [],
      "recent_announcements": [],
      "key_metrics": {}
    }
  ],
  "stargate_project": {
    "total_investment_billions": null,
    "partners": [],
    "planned_capacity_gw": null,
    "locations": []
  }
}

If a value is not available return null or []. Do not estimate. Do not fabricate.
"""
