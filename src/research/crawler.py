"""Website crawler and technical signal analyzer for local businesses."""

import logging
import re
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import requests

logger = logging.getLogger(__name__)

BOOKING_SIGNALS = [
    "calendly.com",
    "acuityscheduling.com",
    "fresha.com",
    "opentable.com",
    "resy.com",
    "square.site",
    "squareup.com",
    "booksy.com",
    "mindbodyonline.com",
    "setmore.com",
    "appointlet.com",
    "vagaro.com",
    "timely.com",
    "simplybook.me",
    "zenoti.com",
]


class WebsiteCrawler:
    def __init__(self, timeout: int = 8, max_subpages: int = 3):
        self.timeout = timeout
        self.max_subpages = max_subpages
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
            )
        }

    def fetch_url(self, url: str) -> Optional[str]:
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url
        try:
            resp = requests.get(url, headers=self.headers, timeout=self.timeout, allow_redirects=True)
            if resp.status_code == 200:
                return resp.text
        except Exception as e:
            logger.debug(f"Failed to fetch {url}: {e}")
        return None

    def analyze_site(self, base_url: str) -> Dict[str, any]:
        """Crawls homepage and key subpages, returning facts and technical signals."""
        results = {
            "url": base_url,
            "title": "",
            "description": "",
            "text_summary": "",
            "has_booking_system": False,
            "detected_booking_provider": None,
            "is_mobile_responsive": True,
            "has_pdf_menu": False,
            "copyright_year": None,
            "subpages_checked": [],
            "facts": [],
        }

        if not base_url or base_url.strip() in ("", "None", "N/A"):
            results["facts"].append("No official website found or provided.")
            return results

        html = self.fetch_url(base_url)
        if not html:
            results["facts"].append(f"Website at {base_url} is currently unreachable or offline.")
            return results

        soup = BeautifulSoup(html, "html.parser")

        # Title & Meta Description
        if soup.title and soup.title.string:
            results["title"] = soup.title.string.strip()

        meta_desc = soup.find("meta", attrs={"name": re.compile(r"description", re.I)})
        if meta_desc and meta_desc.get("content"):
            results["description"] = meta_desc["content"].strip()

        # Mobile Responsiveness Check (viewport tag)
        viewport = soup.find("meta", attrs={"name": "viewport"})
        if not viewport:
            results["is_mobile_responsive"] = False
            results["facts"].append("Website lacks mobile viewport meta tag (not mobile-responsive).")

        # Booking Widgets & PDF Menu Detection
        links = soup.find_all("a", href=True)
        for link in links:
            href = link["href"].lower()
            for provider in BOOKING_SIGNALS:
                if provider in href:
                    results["has_booking_system"] = True
                    results["detected_booking_provider"] = provider
                    break
            if href.endswith(".pdf") and any(w in href for w in ["menu", "price", "services", "rates"]):
                results["has_pdf_menu"] = True

        if results["has_pdf_menu"]:
            results["facts"].append("Menu/pricing is served as a downloadable PDF rather than an interactive web page.")

        if not results["has_booking_system"]:
            results["facts"].append("Website does not have an integrated online booking or appointment scheduling system.")
        else:
            results["facts"].append(f"Online booking detected via {results['detected_booking_provider']}.")

        # Copyright year detection
        footer_text = ""
        footer = soup.find(["footer", "div", "p"], class_=re.compile(r"footer|copyright", re.I))
        if footer:
            footer_text = footer.get_text()
        else:
            footer_text = soup.get_text()[-1000:]

        match = re.search(r"©\s*(?:20\d\d\s*-\s*)?(20\d\d)", footer_text)
        if match:
            year = int(match.group(1))
            results["copyright_year"] = year
            if year < 2024:
                results["facts"].append(f"Website copyright footer indicates last update around {year}.")

        # Subpages exploration (About, Services, Menu, Contact)
        subpage_candidates = []
        for link in links:
            href = link["href"]
            text = link.get_text().strip().lower()
            if any(term in href.lower() or term in text for term in ["about", "service", "menu", "contact", "book"]):
                full_url = urljoin(base_url, href)
                parsed_base = urlparse(base_url).netloc
                parsed_full = urlparse(full_url).netloc
                if parsed_base == parsed_full and full_url not in subpage_candidates and full_url != base_url:
                    subpage_candidates.append(full_url)
                if len(subpage_candidates) >= self.max_subpages:
                    break

        results["subpages_checked"] = subpage_candidates

        # Extract summary text from main content
        for script in soup(["script", "style", "noscript", "svg"]):
            script.decompose()
        text_lines = [line.strip() for line in soup.get_text().splitlines() if len(line.strip()) > 30]
        results["text_summary"] = " ".join(text_lines[:8])

        return results
