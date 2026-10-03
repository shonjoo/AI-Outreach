"""Post-generation validator for cold outreach drafts.

Enforces strict human-like style rules and negative constraints:
1. Word count <= 90 words
2. No em-dashes ('—', '–', or '--')
3. No exclamation marks ('!')
4. No banned openers ('I hope this finds you well', 'I came across', 'I\'m reaching out', 'I noticed that')
5. No AI buzzwords ('leverage', 'streamline', 'elevate', 'unlock', 'game-changer', 'seamless', 'cutting-edge', 'fast-paced', 'in today\'s')
6. No triplet lists ('A, B, and C')
7. No 'not just X, but Y' or 'not only X, but also Y' constructions
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ValidationResult:
    is_valid: bool
    violations: List[str] = field(default_factory=list)
    word_count: int = 0


# 1. Banned Openers (matched at start of text or immediately after greeting line)
BANNED_OPENERS_REGEX = re.compile(
    r"(?i)(?:^|[\r\n]+|\b(?:hi|hello|dear|hey)\s+[^,\.\n]+[,\.]?\s*[\r\n]+)\s*"
    r"(?:i\s+hope\s+this\s+finds\s+you\s+well|hope\s+this\s+finds\s+you\s+well|"
    r"i\s+came\s+across|came\s+across|"
    r"i(?:'m|\s+am)?\s+reaching\s+out|reaching\s+out|"
    r"i\s+noticed\s+that|i\s+noticed\b)"
)

# 2. Banned Buzzwords
BANNED_WORDS = [
    r"\bleverage\w*\b",
    r"\bstreamline\w*\b",
    r"\belevate\w*\b",
    r"\bunlock\w*\b",
    r"\bgame-?chang\w*\b",
    r"\bseamless\w*\b",
    r"\bcutting-?edge\b",
    r"\bfast-?paced\b",
    r"\bin\s+today['’]?s\b",
]
BANNED_WORDS_REGEX = re.compile(r"(?i)(" + "|".join(BANNED_WORDS) + ")")

# 3. Em-Dash and Double Hyphen Pattern
EM_DASH_REGEX = re.compile(r"[\u2014\u2013]|--")

# 4. Exclamation Mark Pattern
EXCLAMATION_REGEX = re.compile(r"!")

# 5. Triplet List Pattern (e.g. "save time, cut costs, and increase revenue")
TRIPLET_LIST_REGEX = re.compile(
    r"(?i)\b[a-z0-9]+(?:\s+[a-z0-9]+)*,\s*[a-z0-9]+(?:\s+[a-z0-9]+)*,\s*(?:and|or)\s+[a-z0-9]+"
)

# 6. "Not just X, but Y" Construction
NOT_JUST_REGEX = re.compile(
    r"(?i)\bnot\s+(?:just|only)\b.*?\bbut\s+(?:also\s+)?"
)


def validate_draft(draft_text: str, max_words: int = 90) -> ValidationResult:
    """Validates an outreach draft against negative constraints and style rules."""
    violations = []

    if not draft_text or not draft_text.strip():
        return ValidationResult(is_valid=False, violations=["Draft is empty"], word_count=0)

    # 1. Word Count Check
    words = draft_text.strip().split()
    word_count = len(words)
    if word_count > max_words:
        violations.append(f"Exceeds max word count: {word_count} words (limit: {max_words})")

    # 2. Em-Dash Check
    if EM_DASH_REGEX.search(draft_text):
        violations.append("Contains em-dash or double-hyphen ('—' or '--')")

    # 3. Exclamation Marks
    if EXCLAMATION_REGEX.search(draft_text):
        violations.append("Contains exclamation mark ('!')")

    # 4. Banned Openers
    if BANNED_OPENERS_REGEX.search(draft_text):
        violations.append("Starts with banned opener ('I hope this finds you well', 'I came across', 'I\\'m reaching out', 'I noticed that')")

    # 5. Banned Words
    found_banned = BANNED_WORDS_REGEX.findall(draft_text)
    if found_banned:
        unique_banned = sorted(set(w.lower() for w in found_banned))
        violations.append(f"Contains banned words: {', '.join(unique_banned)}")

    # 6. Triplet Lists
    if TRIPLET_LIST_REGEX.search(draft_text):
        violations.append("Contains triplet list pattern ('A, B, and C')")

    # 7. 'Not just X, but Y'
    if NOT_JUST_REGEX.search(draft_text):
        violations.append("Contains 'not just X, but Y' construction")

    return ValidationResult(
        is_valid=len(violations) == 0,
        violations=violations,
        word_count=word_count,
    )
