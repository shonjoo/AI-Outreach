"""Dossier builder and fact verification engine."""

import logging
from typing import List, Optional
from src.db.models import Contact, ResearchDossier
from src.research.crawler import WebsiteCrawler
from src.research.web_search import WebSearchEngine

logger = logging.getLogger(__name__)


class DossierBuilder:
    def __init__(self, crawler: Optional[WebsiteCrawler] = None, searcher: Optional[WebSearchEngine] = None):
        self.crawler = crawler or WebsiteCrawler()
        self.searcher = searcher or WebSearchEngine()

    def build_dossier(self, contact: Contact, user_pasted_linkedin: str = "") -> ResearchDossier:
        """Researches a business and synthesizes verifiable facts and opportunities."""
        verifiable_facts: List[str] = []
        detected_opportunities: List[str] = []
        search_snippets: List[str] = []

        website_url = contact.website.strip() if contact.website else ""
        has_no_website = (
            not website_url
            or "no website" in website_url.lower()
            or "missing" in website_url.lower()
            or (contact.notes and "no website" in contact.notes.lower())
        )

        # Step 1: If website is not provided and not explicitly marked 'no website', search for it
        if not website_url and not has_no_website and contact.company:
            potential_site = self.searcher.find_potential_website(contact.company)
            if potential_site:
                website_url = potential_site

        # Step 2: Incorporate sheet notes as high-confidence human verified context
        area_hint = ""
        if contact.notes:
            note_facts = [n.strip() for n in contact.notes.replace(";", "|").split("|") if n.strip()]
            for nf in note_facts:
                verifiable_facts.append(f"From contact notes: {nf}")
                nf_lower = nf.lower()
                if "area:" in nf_lower or "location:" in nf_lower:
                    area_hint = nf.split(":", 1)[-1].strip()
                if "no online booking" in nf_lower or "scheduling bottleneck" in nf_lower:
                    detected_opportunities.append("Lack of automated online booking / appointment system")
                if "pdf" in nf_lower and "menu" in nf_lower:
                    detected_opportunities.append("Mobile-unfriendly PDF menu")
                if "no website" in nf_lower:
                    detected_opportunities.append("No active official website; relies on local Maps and social discovery")
                if "rating" in nf_lower or "review" in nf_lower:
                    detected_opportunities.append("Strong local customer review reputation ready for automated conversion")
                if "phone" in nf_lower:
                    detected_opportunities.append("Opportunity for automated WhatsApp / SMS booking replies on business line")

        # Step 3: Google Maps & Local Reviews Fallback when no website exists
        if has_no_website:
            website_url = ""  # Do not crawl non-existent website
            verifiable_facts.append(f"{contact.company} operates without an active official website, relying on Google Maps and foot traffic.")
            verifiable_facts.append(f"{contact.company} currently lacks an online booking system, relying on phone calls and walk-in inquiries.")
            detected_opportunities.append("No dedicated mobile website or direct online booking portal for local discovery")
            detected_opportunities.append("Relies on phone calls and walk-in scheduling instead of a 24/7 automated appointment flow")

            # Check if LinkedIn URL field contains Google Maps link
            maps_url = contact.linkedin_url if (contact.linkedin_url and "maps" in contact.linkedin_url.lower()) else ""
            if maps_url:
                verifiable_facts.append(f"Google Maps Listing: {maps_url}")
                detected_opportunities.append("Google Maps listing lacks a direct 1-click booking link or interactive mobile menu")

            # Perform dedicated Google Maps & reviews search
            maps_search_hint = area_hint or contact.job_title or ""
            maps_results = self.searcher.search_maps_and_reviews(contact.company, location_hint=maps_search_hint)
            for item in maps_results:
                snip = f"{item['title']}: {item['snippet']}"
                search_snippets.append(snip)
                if any(w in item['snippet'].lower() for w in ["star", "review", "rating", "service", "appointment", "walk-in", "booking"]):
                    verifiable_facts.append(f"From Google Maps/Reviews: {item['snippet'][:150]}...")

        # Step 4: Crawl website if we have a valid URL
        crawl_results = {}
        if website_url:
            crawl_results = self.crawler.analyze_site(website_url)
            for f in crawl_results.get("facts", []):
                verifiable_facts.append(f"From website ({website_url}): {f}")
                if "lacks mobile viewport" in f.lower():
                    detected_opportunities.append("Website is not mobile-responsive")
                if "does not have an integrated online booking" in f.lower():
                    detected_opportunities.append("No online booking widget on website")
                if "downloadable pdf" in f.lower():
                    detected_opportunities.append("PDF menu instead of interactive mobile page")
                if "copyright footer indicates last update" in f.lower():
                    detected_opportunities.append(f"Outdated website footer ({crawl_results.get('copyright_year')})")

        # Step 5: Web search for presence & press if facts are still light
        if contact.company and len(verifiable_facts) < 4:
            search_results = self.searcher.search_business(contact.company, location_hint=area_hint)
            for item in search_results:
                snip = f"{item['title']}: {item['snippet']}"
                search_snippets.append(snip)
                if len(verifiable_facts) < 4 and len(item['snippet']) > 30:
                    verifiable_facts.append(f"From public search: {item['snippet'][:150]}...")

        # Step 6: Incorporate user pasted LinkedIn profile or post text
        if user_pasted_linkedin.strip():
            verifiable_facts.append(f"From LinkedIn profile/post: {user_pasted_linkedin.strip()}")
            detected_opportunities.append("Specific recent achievement / post on LinkedIn")

        # Deduplicate
        unique_facts = []
        for f in verifiable_facts:
            if f not in unique_facts:
                unique_facts.append(f)

        unique_opps = []
        for o in detected_opportunities:
            if o not in unique_opps:
                unique_opps.append(o)

        has_strong_hook = len(unique_facts) > 0 and (len(unique_opps) > 0 or len(contact.notes) > 10)

        summary_text = crawl_results.get("text_summary", "")
        if has_no_website and not summary_text:
            summary_text = f"No active official website listed for {contact.company}. Sourced from Google Maps listing, local reviews, and notes."

        return ResearchDossier(
            contact_id=contact.id or 0,
            business_name=contact.company,
            website_url=website_url,
            website_title=crawl_results.get("title", ""),
            website_summary=summary_text,
            detected_opportunities=unique_opps,
            search_snippets=search_snippets[:4],
            user_pasted_content=user_pasted_linkedin.strip(),
            verifiable_facts=unique_facts,
            has_strong_hook=has_strong_hook,
        )
