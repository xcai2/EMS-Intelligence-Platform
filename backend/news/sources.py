"""News source configuration and fallback payloads."""

OFFICIAL_COMPANY_SOURCES = {
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
        "public_news_url": "https://public.com/stocks/flex/news",
        "aliases": ["Flex Ltd", "Flextronics", "NASDAQ:FLEX"],
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
    },
    "BHE": {
        "name": "Benchmark",
        "domain": "bench.com",
        "base_url": "https://www.bench.com",
        "news_url": "https://www.bench.com/newsroom",
        "rss_url": None,
        "public_news_url": None,
        "aliases": ["Benchmark Electronics", "NYSE:BHE"],
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
