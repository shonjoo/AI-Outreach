"""Public web search extractor using DuckDuckGo (zero API key needed)."""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

import warnings

warnings.filterwarnings("ignore", category=RuntimeWarning)

try:
    from ddgs import DDGS
    DDGS_AVAILABLE = True
except ImportError:
    try:
        from duckduckgo_search import DDGS
        DDGS_AVAILABLE = True
    except ImportError:
        DDGS_AVAILABLE = False


class WebSearchEngine:
    def __init__(self, max_results: int = 4):
        self.max_results = max_results

    def search_business(self, company: str, location_hint: str = "") -> List[Dict[str, str]]:
        """Searches for business information, reviews, and news."""
        query = f"{company} {location_hint} reviews website".strip()
        results = []

        if not DDGS_AVAILABLE:
            logger.warning("duckduckgo_search package not available, returning empty search results.")
            return results

        try:
            with DDGS() as ddgs:
                ddg_results = ddgs.text(query, max_results=self.max_results)
                if ddg_results:
                    for r in ddg_results:
                        title = r.get("title", "")
                        body = r.get("body", "")
                        href = r.get("href", "")
                        results.append({
                            "title": title,
                            "snippet": body,
                            "url": href,
                        })
        except Exception as e:
            logger.debug(f"DuckDuckGo search error for '{query}': {e}")

        return results

    def search_maps_and_reviews(self, company: str, location_hint: str = "") -> List[Dict[str, str]]:
        """Searches specifically for Google Maps presence, customer reviews, ratings, and customer sentiment."""
        query = f"{company} {location_hint} google maps reviews rating".strip()
        results = []

        if not DDGS_AVAILABLE:
            return results

        try:
            with DDGS() as ddgs:
                ddg_results = ddgs.text(query, max_results=self.max_results)
                if ddg_results:
                    for r in ddg_results:
                        title = r.get("title", "")
                        body = r.get("body", "")
                        href = r.get("href", "")
                        results.append({
                            "title": title,
                            "snippet": body,
                            "url": href,
                        })
        except Exception as e:
            logger.debug(f"DuckDuckGo maps search error for '{query}': {e}")

        return results

    def find_potential_website(self, company: str) -> Optional[str]:
        """Tries to find official website URL if not provided."""
        if not DDGS_AVAILABLE:
            return None
        try:
            with DDGS() as ddgs:
                ddg_results = ddgs.text(f"{company} official website", max_results=3)
                if ddg_results:
                    for r in ddg_results:
                        href = r.get("href", "")
                        # Filter out directories
                        if href and not any(d in href for d in ["yelp.com", "facebook.com", "instagram.com", "linkedin.com", "tripadvisor.com", "yellowpages.com"]):
                            return href
        except Exception as e:
            logger.debug(f"DuckDuckGo search error finding website for {company}: {e}")
        return None
