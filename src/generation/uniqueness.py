"""Uniqueness and diversity validator across generated outreach drafts."""

import re
from typing import List, Set


def tokenize(text: str) -> Set[str]:
    """Tokenizes text into lowercase words, ignoring common stop words."""
    stop_words = {
        "the", "a", "an", "and", "or", "to", "in", "for", "of", "with", "at", 
        "by", "from", "up", "about", "into", "over", "after", "is", "are", 
        "was", "were", "be", "been", "being", "have", "has", "had", "do", 
        "does", "did", "you", "your", "we", "our", "it", "its", "they", "their"
    }
    words = re.findall(r"\b[a-z]{3,}\b", text.lower())
    return {w for w in words if w not in stop_words}


def calculate_jaccard_similarity(text1: str, text2: str) -> float:
    """Calculates Jaccard similarity between two texts."""
    tokens1 = tokenize(text1)
    tokens2 = tokenize(text2)
    if not tokens1 or not tokens2:
        return 0.0
    intersection = len(tokens1.intersection(tokens2))
    union = len(tokens1.union(tokens2))
    return float(intersection) / float(union) if union > 0 else 0.0


def check_batch_uniqueness(new_text: str, existing_texts: List[str], threshold: float = 0.40) -> bool:
    """
    Returns True if the new text is sufficiently unique compared to all existing drafts.
    Returns False if similarity exceeds the threshold.
    """
    for text in existing_texts:
        sim = calculate_jaccard_similarity(new_text, text)
        if sim > threshold:
            return False
    return True
