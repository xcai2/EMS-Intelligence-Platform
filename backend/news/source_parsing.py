"""Source-parsing helpers for News fetch pipelines."""

from __future__ import annotations

from html import unescape
import re


def _normalize_text(value: str | None) -> str:
    """Normalize optional text inputs into a stripped string."""
    return unescape((value or "").strip())


def clean_html(text: str) -> str:
    """Remove lightweight HTML markup from snippets/titles."""
    text = _normalize_text(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


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
