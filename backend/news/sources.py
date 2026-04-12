"""News source configuration and fallback payloads."""

OFFICIAL_COMPANY_SOURCES = {
    # -------------------------------------------------------------------------
    # Per-company filter config fields (used by news_filter_policies.py):
    #   excluded_noise_terms : list[str]
    #       Content patterns that indicate the article is NOT about this company.
    #       Checked against the full title+description before any accept logic.
    #   excluded_domains : list[str]
    #       URL domains whose articles are never relevant for this company.
    #       Suffix-matched (e.g. "chosun.com" blocks "news.chosun.com" too).
    #       Use for known non-industry news sites that frequently produce
    #       false positives due to ticker/name collisions.
    #   strict_title_match : bool (default False)
    #       When True, a single-word alias hit in the description alone is NOT
    #       sufficient to accept an item — the alias must appear in the title or
    #       a multi-word alias must appear in the description.
    #       Use for companies whose short name is a common English word (Flex,
    #       Benchmark) to avoid false positives from unrelated articles.
    # -------------------------------------------------------------------------
    "FLEX": {
        "name": "Flex",
        "domain": "flex.com",
        "base_url": "https://flex.com",
        "news_url": "https://flex.com/newsroom",
        "rss_url": [
            "https://investors.flex.com/rss/pressrelease.aspx",
            "https://investors.flex.com/rss/SECFiling.aspx?Exchange=CIK&Symbol=0000866374",
            "https://investors.flex.com/rss/event.aspx",
        ],
        "public_news_url": None,
        "aliases": ["Flex Ltd", "Flextronics", "NASDAQ:FLEX"],
        # "flex" is a common English word — require a stronger signal in description.
        "strict_title_match": True,
        # Domains that consistently produce false positives for FLEX.
        # Add any non-industry news site whose "flex" mentions are never about Flex Ltd.
        "excluded_domains": [
            "chosun.com",       # Korean national newspaper — not EMS/tech
            "kalw.org",         # SF public radio — arts & community events
            "samsung.com",      # Consumer product pages ("Flex Duo" etc.)
            "chartmill.com",    # Stock screener/static quote pages
            "simplywall.st",    # Static equity profile pages
            "stockstory.org",   # Static earnings-summary pages
            "stockstory.com",
        ],
        "excluded_noise_terms": [
            # Real estate / coworking
            "flex office", "flex workspace", "flex industrial properties",
            "flex industrial property", "flex space", "flex lease", "flex leasing",
            "flex rent", "flex building",
            # Consumer products using "Flex" as brand/model name
            "soundlink flex", "bose flex", "chromeos flex", "chrome os flex",
            "bonds flex", "flex seal", "flex tape",
            # Streaming / entertainment
            "playhouse flex", "watch flex",
            # Gig economy / logistics
            "amazon flex", "amazon flex driver",
            # Energy / industry
            "flex lng", "flex fuel",
            # HR / scheduling / programs
            "flex plan", "flex schedule", "flex day", "flex time",
            "flex hours", "flex work", "flex program", "flex desk",
            # Named product brands that embed "flex"
            "omega flex", "saica flex", "galaxy book flex",
            "flex pass", "peacemaker flex",
            # Other product/brand noise
            "flex award", "flex pricing", "flex modular",
            "flex wing", "flex force", "flex system", "flex pay",
            # Generic fitness/casual usage
            "muscle flex", "flex your", "stay flex", "google me flex",
            "flex duo", "dual door",
            # Ticker-only valuation/compare pages (not company operations news)
            "flex vs.",
            "flex or ",
            "stock price",
            "quote & chart",
            "better value option",
            "shares offer superior value",
            "no better than bus",
            "bmr",
        ],
    },
    "JBL": {
        "name": "Jabil",
        "domain": "jabil.com",
        "base_url": "https://www.jabil.com",
        "news_url": "https://www.jabil.com/about-us/news.html",
        "rss_url": [
            "https://investors.jabil.com/rss/pressrelease.aspx",
            "https://investors.jabil.com/rss/event.aspx",
            "https://investors.jabil.com/rss/SECFiling.aspx?Exchange=CIK&Symbol=0000898293",
        ],
        "disable_html_scan": True,
        "public_news_url": None,
        "aliases": ["Jabil Inc", "NYSE:JBL"],
        # "jbl" conflicts with JBL (Harman audio brand) AND John Bradshaw Layfield (wrestler).
        "strict_title_match": False,
        "excluded_noise_terms": [
            # JBL audio brand (Harman)
            "jbl speakers", "jbl headphones", "jbl audio",
            "jbl bluetooth", "jbl harman", "jbl soundbar",
            "jbl earbuds", "jbl earphones", "jbl charge",
            "jbl flip", "jbl pulse", "jbl boombox",
            # JBL = John Bradshaw Layfield (wrestler)
            "aew", "wwe", "wrestling", "smackdown", "raw is war",
            "john bradshaw", "bradshaw layfield", "jericho",
            "wrestlemania", "royal rumble", "summerslam",
            # SEC form 144 / insider sale filings are not target news content.
            "report of proposed sale of securities",
            " - 144 - ",
        ],
    },
    "BHE": {
        "name": "Benchmark",
        "domain": "bench.com",
        "base_url": "https://www.bench.com",
        "news_url": "https://www.bench.com/newsroom",
        "rss_url": None,
        "public_news_url": None,
        "aliases": ["Benchmark Electronics", "NYSE:BHE"],
        # "benchmark" is a very common English word — require a stronger signal.
        "strict_title_match": True,
        "excluded_noise_terms": [
            "benchmark rate", "benchmark interest", "benchmark index",
            "benchmark performance", "benchmark test", "benchmark study",
            "benchmark comparison", "set the benchmark", "industry benchmark",
            "market benchmark", "benchmark yield", "benchmark score",
            "benchmark awards", "performance benchmark", "benchmark survey",
            "benchmark report", "new benchmark", "benchmark lending",
            # Food/agri companies and sector pages unrelated to Benchmark Electronics.
            "benchmark genetics", "nomad foods", "thai union feedmill",
            "cal-maine foods", "seafoodsource", "livestock", "aquaculture",
            "feedmill", "animal nutrition", "agri",
        ],
    },
    "SANM": {
        "name": "Sanmina",
        "domain": "sanmina.com",
        "base_url": "https://www.sanmina.com",
        "news_url": "https://www.sanmina.com/media-center/press-releases/",
        "rss_url": [
            "https://ir.sanmina.com/rss/pressrelease.aspx",
            "https://ir.sanmina.com/rss/SECFiling.aspx?Exchange=CIK&Symbol=0000897723",
            "https://ir.sanmina.com/rss/event.aspx",
        ],
        "public_news_url": None,
        "aliases": ["Sanmina Corporation", "NASDAQ:SANM"],
        # "sanmina" is a distinctive name — description match is fine.
        "strict_title_match": False,
        "excluded_noise_terms": [],
    },
    "CLS": {
        "name": "Celestica",
        "domain": "celestica.com",
        "base_url": "https://www.celestica.com",
        "news_url": "https://www.celestica.com/about-us/news-events",
        "rss_url": "https://www.globenewswire.com/rssfeed/organization/vlXa3ip4O0JMbJucCiUeUg==",
        "disable_html_scan": True,
        "public_news_url": None,
        "aliases": ["Celestica Inc", "NYSE:CLS", "TSX:CLS"],
        # "celestica" is a distinctive name — description match is fine.
        "strict_title_match": False,
        "excluded_noise_terms": [
            # CLS acronym ambiguity (non-Celestica entities/pages)
            "coupang cls",
            "labor commission rejects first bargaining split bid",
        ],
    },
    "PLXS": {
        "name": "Plexus",
        "domain": "plexus.com",
        "base_url": "https://www.plexus.com",
        "news_url": "https://www.plexus.com/news/",
        "rss_url": [
            "https://ir.plexus.com/rss/pressrelease.aspx",
            "https://ir.plexus.com/rss/SECFiling.aspx?Exchange=CIK&Symbol=0000785786",
            "https://ir.plexus.com/rss/event.aspx",
        ],
        "public_news_url": None,
        "aliases": ["Plexus Corp", "Plexus Corp.", "NASDAQ:PLXS"],
        # "plexus" has medical/MLM usage — description match is fine with noise rejection.
        "strict_title_match": False,
        "excluded_noise_terms": [
            # Anatomy / neurology — plexus as a nerve/tissue structure
            "brachial plexus", "cervical plexus", "solar plexus",
            "lumbar plexus", "sacral plexus", "nerve plexus",
            "choroid plexus", "cardiac plexus", "ventricular plexus",
            # MLM health brand
            "plexus slim", "plexus health", "plexus worldwide",
        ],
    },
}

OFFICIAL_NEWS_KEYWORDS = [
    "news",
    "newsroom",
    "press",
    "release",
    "announcement",
    "earnings",
    "news release",
    "investor",
    "relations",
    "investor relations",
    "media",
    "media center",
    "event",
    "events",
]

FALLBACK_COMPANY_NEWS = {
    "FLEX": [
        {
            "title": "Flex expands AI data-center manufacturing collaborations",
            "url": "https://flex.com/newsroom",
            "description": "Flex highlights accelerated demand for AI infrastructure programs and advanced manufacturing services.",
            "source": "Flex Newsroom",
            "categories": ["ai", "operations"],
        },
    ],
    "JBL": [
        {
            "title": "Jabil outlines AI and cloud infrastructure momentum",
            "url": "https://www.jabil.com/about-us/news.html",
            "description": "Jabil updates investors on AI server demand trends and supply-chain execution for hyperscaler customers.",
            "source": "Jabil Newsroom",
            "categories": ["ai", "strategy"],
        },
    ],
    "CLS": [
        {
            "title": "Celestica reports continued growth in CCS segment",
            "url": "https://www.celestica.com/about-us/news-events",
            "description": "Celestica points to sustained cloud and communications demand with AI-related infrastructure tailwinds.",
            "source": "Celestica News",
            "categories": ["earnings", "ai"],
        },
    ],
    "BHE": [
        {
            "title": "Benchmark highlights high-reliability manufacturing programs",
            "url": "https://www.bench.com/newsroom",
            "description": "Benchmark discusses advanced engineering and manufacturing support for compute and industrial customers.",
            "source": "Benchmark Newsroom",
            "categories": ["operations", "strategy"],
        },
    ],
    "SANM": [
        {
            "title": "Sanmina expands focus on complex cloud and networking platforms",
            "url": "https://www.sanmina.com/about/news-events",
            "description": "Sanmina emphasizes execution in compute-heavy and AI-adjacent infrastructure markets.",
            "source": "Sanmina News",
            "categories": ["ai", "operations"],
        },
    ],
    "PLXS": [
        {
            "title": "Plexus reports continued demand across key customer programs",
            "url": "https://www.plexus.com/news/",
            "description": "Plexus highlights customer-program execution, product realization services, and manufacturing demand across its end markets.",
            "source": "Plexus News",
            "categories": ["earnings", "operations"],
        },
    ],
}

FALLBACK_INDUSTRY_NEWS = [
    {
        "title": "AI server demand continues to reshape electronics manufacturing priorities",
        "url": "https://www.eetimes.com/",
        "description": "Industry coverage tracks how EMS providers are adapting capacity plans for AI hardware and data-center systems.",
        "source": "EE Times",
        "categories": ["ai", "capex"],
    },
    {
        "title": "Hyperscaler build-outs keep supply-chain resilience in focus",
        "url": "https://www.supplychaindive.com/",
        "description": "Manufacturing and logistics teams are balancing lead-time pressure as AI infrastructure programs scale globally.",
        "source": "Supply Chain Dive",
        "categories": ["ai", "operations"],
    },
]
