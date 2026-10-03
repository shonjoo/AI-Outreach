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

        # Step 1: If website is not provided, try to detect from company search or notes
        if not website_url and contact.company:
            potential_site = self.searcher.find_potential_website(contact.company)
            if potential_site:
                website_url = potential_site

        # Step 2: Incorporate sheet notes as high-confidence human verified context
        if contact.notes:
            note_facts = [n.strip() for n in contact.notes.split(";") if n.strip()]
            for nf in note_facts:
                verifiable_facts.append(f"From contact notes: {nf}")
                # Analyze opportunities from notes
                nf_lower = nf.lower()
                if "no online booking" in nf_lower or "scheduling bottleneck" in nf_lower:
                    detected_opportunities.append("Lack of automated online booking / appointment system")
                if "pdf" in nf_lower and "menu" in nf_lower:
                    detected_opportunities.append("Mobile-unfriendly PDF menu")
                if "no website" in nf_lower:
                    detected_opportunities.append("No active official website; relies on social media")
                if "review" in nf_lower or "questions" in nf_lower:
                    detected_opportunities.append("High volume of repetitive customer questions in reviews/social")

        # Step 3: Crawl website if we have a URL
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

        # Step 4: Web search for reviews & presence
        if contact.company:
            search_results = self.searcher.search_business(contact.company)
            for item in search_results:
                snip = f"{item['title']}: {item['snippet']}"
                search_snippets.append(snip)
                if len(verifiable_facts) < 4 and len(item['snippet']) > 30:
                    verifiable_facts.append(f"From public search: {item['snippet'][:150]}...")

        # Step 5: Incorporate user pasted LinkedIn profile or post text
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

        return ResearchDossier(
            contact_id=contact.id or 0,
            business_name=contact.company,
            website_url=website_url,
            website_title=crawl_results.get("title", ""),
            website_summary=crawl_results.get("text_summary", ""),
            detected_opportunities=unique_opps,
            search_snippets=search_snippets[:4],
            user_pasted_content=user_pasted_linkedin.strip(),
            verifiable_facts=unique_facts,
            has_strong_hook=has_strong_hook,
        )
