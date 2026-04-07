"""Source-parsing helpers for News fetch pipelines."""

from __future__ import annotations

from html import unescape
import re
from urllib.parse import urlparse

from backend.news.normalizer import SOURCE_DOMAIN_LABELS

SOURCE_CANDIDATE_MAX_LENGTH = 70
SOURCE_CANDIDATE_MAX_WORDS = 8
SOURCE_PUBLISHER_CONNECTORS = {"&", "and", "of", "the", "for", "in", "on", "at", "to"}
GOOGLE_OWNED_DOMAINS = (
    "news.google.com",
    "google.com",
    "googleusercontent.com",
    "ggpht.com",
    "googleapis.com",
    "gstatic.com",
    "google-analytics.com",
    "googletagmanager.com",
    "doubleclick.net",
)
SOURCE_INVALID_LABELS = {
    "google news",
    "full coverage",
    "read more",
    "continue reading",
    "learn more",
}
SOURCE_MONTH_PATTERN = re.compile(
    r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b",
    flags=re.IGNORECASE,
)
SOURCE_WEEKDAY_PATTERN = re.compile(
    r"\b(?:mon(?:day)?|tue(?:s(?:day)?)?|wed(?:nesday)?|thu(?:rs(?:day)?)?|"
    r"fri(?:day)?|sat(?:urday)?|sun(?:day)?)\b",
    flags=re.IGNORECASE,
)
SOURCE_RELATIVE_TIME_PATTERN = re.compile(
    r"\b\d+\s+(?:min(?:ute)?s?|hour(?:s)?|hr(?:s)?|day(?:s)?|week(?:s)?|"
    r"month(?:s)?|year(?:s)?)\s+ago\b",
    flags=re.IGNORECASE,
)
SOURCE_TIME_PATTERN = re.compile(
    r"\b(?:\d{1,2}:\d{2}(?::\d{2})?\s*(?:am|pm|gmt|utc)?|\d{1,2}\s*(?:am|pm))\b",
    flags=re.IGNORECASE,
)
SOURCE_DOMAIN_PATTERN = re.compile(r"^(?:[a-z0-9-]+\.)+[a-z]{2,}$", flags=re.IGNORECASE)
SOURCE_WORD_PATTERN = re.compile(r"[A-Za-z0-9&.'-]+")


def _normalize_text(value: str | None) -> str:
    """Normalize optional text inputs into a stripped string."""
    return unescape((value or "").strip())


def clean_html(text: str) -> str:
    """Remove lightweight HTML markup from snippets/titles."""
    text = _normalize_text(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _normalize_domain(domain: str | None) -> str:
    """Normalize domain-like strings into a stable lowercase hostname."""
    text = _normalize_text(domain).lower().strip(".")
    if not text:
        return ""
    if "://" in text:
        parsed = urlparse(text)
        text = parsed.netloc or parsed.path
    text = text.split("@")[-1]
    text = text.split(":", 1)[0]
    return text.replace("www.", "")


def _source_label_from_domain(domain: str | None) -> str | None:
    """Map a hostname or domain-like string to a display label when possible."""
    normalized = _normalize_domain(domain)
    if not normalized or is_google_owned_domain(normalized):
        return None
    for known_domain, label in SOURCE_DOMAIN_LABELS.items():
        if normalized == known_domain or normalized.endswith(f".{known_domain}"):
            return label
    if SOURCE_DOMAIN_PATTERN.fullmatch(normalized):
        return normalized
    return None


def _looks_like_source_metadata(text: str) -> bool:
    """Reject timestamps and feed-control labels that should not become publishers."""
    lowered = text.lower()
    if lowered in SOURCE_INVALID_LABELS:
        return True
    if SOURCE_RELATIVE_TIME_PATTERN.search(text):
        return True
    if SOURCE_TIME_PATTERN.search(text):
        return True
    if re.search(r"\b\d{4}\b", text):
        return True
    if SOURCE_MONTH_PATTERN.search(lowered) and re.search(r"\d", text):
        return True
    if SOURCE_WEEKDAY_PATTERN.search(lowered) and re.search(r"\d", text):
        return True
    return False


def normalize_source_candidate(value: str | None) -> str | None:
    """Normalize a source/publisher candidate into a stable display label."""
    text = clean_html(value or "")
    if not text:
        return None

    text = re.sub(r"^[\s\-–—|•·:;,]+", "", text)
    text = re.sub(r"[\s\-–—|•·:;,.]+$", "", text)
    text = text.strip("()[]{}")
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return None

    if "://" in text or "/" in text:
        return None

    domain_label = _source_label_from_domain(text)
    if domain_label:
        return domain_label

    if len(text) < 2 or len(text) > SOURCE_CANDIDATE_MAX_LENGTH:
        return None
    if not re.search(r"[A-Za-z]", text):
        return None
    if len(SOURCE_WORD_PATTERN.findall(text)) > SOURCE_CANDIDATE_MAX_WORDS:
        return None
    if _looks_like_source_metadata(text):
        return None
    return text


def _looks_like_publisher_tail(value: str | None) -> bool:
    """Check whether a free-text tail fragment looks like a publisher label."""
    normalized = normalize_source_candidate(value)
    if not normalized:
        return False

    if _source_label_from_domain(normalized):
        return True

    tokens = SOURCE_WORD_PATTERN.findall(normalized)
    if not tokens or len(tokens) > 6:
        return False

    has_named_token = False
    for token in tokens:
        lowered = token.lower()
        if lowered in SOURCE_PUBLISHER_CONNECTORS:
            continue

        alpha_chars = [char for char in token if char.isalpha()]
        if not alpha_chars:
            continue

        has_named_token = True
        if token.isupper():
            continue
        if token[0].isupper():
            continue
        if "." in token and any(char.isupper() for char in token):
            continue
        return False

    return has_named_token


def _extract_source_tail_candidate(cleaned_description: str) -> str | None:
    """Extract a publisher-like tail fragment from a cleaned Google description."""
    separator_patterns = [
        r"(?:•|·|\|)\s*([^•·|]{2,80})$",
        r"(?:[–—-])\s*([^–—-]{2,80})$",
    ]
    for pattern in separator_patterns:
        tail_match = re.search(pattern, cleaned_description)
        if not tail_match:
            continue
        candidate = tail_match.group(1).strip()
        if not _looks_like_publisher_tail(candidate):
            continue
        return normalize_source_candidate(candidate)
    return None


def extract_first_image_url(html: str) -> str:
    """Extract the first absolute image URL from an HTML fragment."""
    if not html:
        return ""
    match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html, flags=re.IGNORECASE)
    if not match:
        return ""
    src = (match.group(1) or "").strip()
    if src.startswith("http://") or src.startswith("https://"):
        return src
    return ""


def is_google_owned_domain(domain: str) -> bool:
    """Identify Google-owned infrastructure that should not be treated as the article source."""
    normalized = _normalize_domain(domain)
    if not normalized:
        return False
    return any(
        normalized == owned_domain or normalized.endswith(f".{owned_domain}")
        for owned_domain in GOOGLE_OWNED_DOMAINS
    )


def is_likely_article_url(url: str) -> bool:
    """Filter out obviously invalid article targets without trying to fully classify page type.

    This is intentionally a conservative baseline gate used during source extraction and
    redirect resolution. It removes static assets, Google-owned intermediaries, and obvious
    tracking URLs, but it does not yet try to distinguish article-detail pages from every
    possible index, category, tag, or search page. If those pages start leaking through in
    production, that should be handled as a second-pass article-priority filter rather than
    by making this low-level validity check too aggressive.
    """
    try:
        if not url.startswith(("http://", "https://")):
            return False
        parsed = urlparse(url)
        domain = (parsed.netloc or "").lower().replace("www.", "")
        if not domain:
            return False
        if is_google_owned_domain(domain):
            return False
        path = (parsed.path or "").lower()
        if any(
            path.endswith(ext)
            for ext in [
                ".jpg",
                ".jpeg",
                ".png",
                ".gif",
                ".webp",
                ".svg",
                ".ico",
                ".js",
                ".css",
                ".map",
                ".xml",
                ".json",
                ".txt",
                ".woff",
                ".woff2",
                ".ttf",
                ".otf",
            ]
        ):
            return False
        if path in {"/css", "/css2"}:
            return False
        # Keep this list intentionally small: this function is a baseline sanitizer, not a
        # full article-page classifier, so aggressive path blocking belongs in a later pass.
        if any(token in path for token in ["/analytics", "/tracking", "/tag/"]):
            return False
        return True
    except Exception:
        return False


def extract_first_external_url_from_html(html: str) -> str:
    """Find the first baseline-valid outbound URL from an HTML fragment.

    This intentionally returns the first external link that clears the conservative
    `is_likely_article_url(...)` gate. It does not yet rank candidates or try to
    pick the best article-detail URL when multiple external links are present.
    """
    if not html:
        return ""
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', html, flags=re.IGNORECASE)
    for href in hrefs:
        href = (href or "").strip()
        if is_likely_article_url(href):
            return href
    return ""


def is_google_news_domain(url: str) -> bool:
    """Check whether a URL still points at a Google News redirect domain."""
    try:
        domain = (urlparse(url).netloc or "").lower().replace("www.", "")
        return domain.endswith("news.google.com")
    except Exception:
        return False


# Google News title/description parsing
def extract_source_from_title_suffix(title: str) -> tuple[str, str | None]:
    """Split a title like 'Headline - Publisher' into content title and source."""
    text = _normalize_text(title)
    if not text:
        return "", None
    match = None
    for candidate_match in re.finditer(r"\s+[–—-]\s+", text):
        match = candidate_match
    if match is None:
        return text, None

    base = text[: match.start()].strip()
    candidate = text[match.end() :].strip()
    if len(base) < 8:
        return text, None
    normalized_candidate = normalize_source_candidate(candidate)
    if not normalized_candidate:
        return text, None
    return base, normalized_candidate


def extract_source_from_google_title(raw_title: str) -> tuple[str, str | None]:
    """Normalize a Google News title and recover any publisher suffix."""
    title = _normalize_text(raw_title)
    if not title:
        return "", None
    title = re.sub(r"\s+[–—-]\s+Google News\s*$", "", title, flags=re.IGNORECASE)

    base_title, source_candidate = extract_source_from_title_suffix(title)
    if source_candidate:
        return base_title, source_candidate
    return title, None


def extract_source_from_google_description(raw_description: str) -> str | None:
    """Recover a source/publisher label from a Google News RSS description block."""
    raw_description = _normalize_text(raw_description)
    if not raw_description:
        return None

    fonts = re.findall(r"<font[^>]*>([^<]+)</font>", raw_description, flags=re.IGNORECASE)
    for text in reversed(fonts):
        candidate = normalize_source_candidate(text)
        if candidate:
            return candidate

    cleaned = clean_html(raw_description)
    if not cleaned:
        return None
    tail_candidate = _extract_source_tail_candidate(cleaned)
    if tail_candidate:
        return tail_candidate
    domain_tail_match = re.search(r"((?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,})$", cleaned)
    if domain_tail_match:
        candidate = normalize_source_candidate(domain_tail_match.group(1))
        if candidate:
            return candidate
    return None


def title_from_url(url: str) -> str:
    """Generate a readable fallback title from an article URL slug."""
    try:
        path = urlparse(url).path.strip("/")
        if not path:
            return ""
        slug = path.split("/")[-1]
        slug = re.sub(r"[-_]+", " ", slug).strip()
        slug = re.sub(r"\s+", " ", slug)
        if len(slug) < 5:
            return ""
        return slug.title()
    except Exception:
        return ""


def extract_source(url: str) -> str:
    """Resolve a human-readable publisher label from a URL."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc
    except Exception:
        return "Unknown"
    return _source_label_from_domain(domain) or "Unknown"
