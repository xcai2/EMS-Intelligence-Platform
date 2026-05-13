"""Shared constants for job classification — imported by both job_scraper and careers_scraper."""

JOB_CATEGORIES = {
    "ai_ml": ["machine learning", "AI engineer", "data scientist", "deep learning", "ML ops"],
    "software": ["software engineer", "developer", "programmer", "full stack", "backend"],
    "hardware": ["hardware engineer", "electrical engineer", "PCB design", "FPGA", "embedded"],
    "manufacturing": ["manufacturing engineer", "process engineer", "production", "quality"],
    "supply_chain": ["supply chain", "logistics", "procurement", "sourcing", "operations"],
    "data_center": ["data center", "cloud engineer", "infrastructure", "DevOps", "SRE"],
    "leadership": ["director", "VP", "manager", "head of", "chief"],
    "sales": ["sales", "account manager", "business development", "customer success"],
}

LOCATION_REGIONS = {
    "americas": ["USA", "United States", "Mexico", "Brazil", "Canada"],
    "asia_pacific": ["China", "Malaysia", "Singapore", "India", "Vietnam", "Thailand", "Taiwan"],
    "europe": ["Germany", "UK", "Poland", "Hungary", "Czech", "Ireland", "Netherlands"],
}
