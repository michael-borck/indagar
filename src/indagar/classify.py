from __future__ import annotations

from urllib.parse import urlparse

ACADEMIC_DOMAINS = {
    "arxiv.org",
    "biorxiv.org",
    "cell.com",
    "crossref.org",
    "doi.org",
    "europepmc.org",
    "frontiersin.org",
    "jstor.org",
    "mdpi.com",
    "medrxiv.org",
    "nature.com",
    "ncbi.nlm.nih.gov",
    "openalex.org",
    "plos.org",
    "pubmed.ncbi.nlm.nih.gov",
    "sagepub.com",
    "science.org",
    "sciencedirect.com",
    "semanticscholar.org",
    "springer.com",
    "tandfonline.com",
    "wiley.com",
}
ACADEMIC_SUFFIXES = (".edu", ".ac.uk", ".edu.au", ".ac.jp", ".ac.nz")

INSTITUTION_DOMAINS = {
    "europa.eu",
    "imf.org",
    "nato.int",
    "oecd.org",
    "un.org",
    "who.int",
    "worldbank.org",
}
INSTITUTION_SUFFIXES = (".gov", ".mil", ".int")

NEWS_DOMAINS = {
    "aljazeera.com",
    "apnews.com",
    "arstechnica.com",
    "axios.com",
    "bbc.co.uk",
    "bbc.com",
    "bloomberg.com",
    "cnn.com",
    "economist.com",
    "ft.com",
    "npr.org",
    "nytimes.com",
    "politico.com",
    "reuters.com",
    "techcrunch.com",
    "theatlantic.com",
    "theguardian.com",
    "thenewyorker.com",
    "theverge.com",
    "washingtonpost.com",
    "wired.com",
    "wsj.com",
}

MEDIA_DOMAINS = {
    "podcasts.apple.com",
    "soundcloud.com",
    "spotify.com",
    "twitch.tv",
    "vimeo.com",
    "youtu.be",
    "youtube.com",
}

PRACTITIONER_DOMAINS = {
    "blogspot.com",
    "dev.to",
    "ghost.io",
    "github.io",
    "hashnode.com",
    "linkedin.com",
    "medium.com",
    "notion.site",
    "substack.com",
    "wordpress.com",
}

CONFIDENCE = {
    "academic": "high",
    "institution": "high",
    "news": "medium",
    "practitioner": "low",
    "media": "low",
    "web": "low",
}


def _matches(host: str, domains: set[str]) -> bool:
    return host in domains or any(host.endswith(f".{domain}") for domain in domains)


def classify_url(url: str) -> tuple[str, str]:
    """Heuristically label a source type and confidence from its URL."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return "web", "low"
    host = (parsed.hostname or "").lower().removeprefix("www.")
    path = parsed.path.lower()
    if not host:
        return "web", "low"

    if _matches(host, MEDIA_DOMAINS):
        return "media", CONFIDENCE["media"]
    if _matches(host, ACADEMIC_DOMAINS) or any(
        host.endswith(suffix) for suffix in ACADEMIC_SUFFIXES
    ):
        return "academic", CONFIDENCE["academic"]
    if _matches(host, INSTITUTION_DOMAINS) or any(
        host.endswith(suffix) for suffix in INSTITUTION_SUFFIXES
    ):
        return "institution", CONFIDENCE["institution"]
    if _matches(host, NEWS_DOMAINS) or host.startswith("news.") or "/news/" in path:
        return "news", CONFIDENCE["news"]
    if _matches(host, PRACTITIONER_DOMAINS):
        return "practitioner", CONFIDENCE["practitioner"]
    return "web", CONFIDENCE["web"]


__all__ = [
    "ACADEMIC_DOMAINS",
    "CONFIDENCE",
    "INSTITUTION_DOMAINS",
    "MEDIA_DOMAINS",
    "NEWS_DOMAINS",
    "PRACTITIONER_DOMAINS",
    "classify_url",
]
