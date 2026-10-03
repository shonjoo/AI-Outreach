"""Unit tests for the post-generation outreach draft validator.

Tests 5 clean, human-like drafts and 10 distinct slop drafts violating negative constraints.
"""

import unittest
from src.generation.validator import validate_draft


class TestDraftValidator(unittest.TestCase):
    # ---------------- 5 CLEAN DRAFTS ----------------
    CLEAN_DRAFTS = [
        # Clean 1: Dental clinic
        (
            "Dental Clinic",
            "Hi Alex,\n\n"
            "Saw that appointment booking at Downtown Dental currently requires a phone call during open hours.\n\n"
            "I build clean websites with simple online booking forms that let clients select a slot directly from their phone.\n\n"
            "Would you be open to a 2-minute preview of how this would look for Downtown Dental?",
        ),
        # Clean 2: Restaurant
        (
            "Restaurant",
            "Hi Marco,\n\n"
            "Saw that Trattoria Bella's online menu opens as a PDF file on phones.\n\n"
            "I build fast restaurant websites with mobile menus and automated replies for reservation inquiries.\n\n"
            "Would you be open to a 2-minute preview of a mobile menu for Trattoria Bella?",
        ),
        # Clean 3: Salon
        (
            "Hair Salon",
            "Hi Sarah,\n\n"
            "Saw that Glow Salon shares services on Instagram without a dedicated website for appointments.\n\n"
            "I build fast websites with automatic booking forms so clients can confirm appointments directly online.\n\n"
            "Would you be open to a 2-minute preview of how this would look for Glow Salon?",
        ),
        # Clean 4: Auto repair
        (
            "Auto Repair",
            "Hi David,\n\n"
            "Saw that Oak Street Auto currently takes repair quote requests only through the front desk phone.\n\n"
            "I build simple web inquiry forms that send photo estimates directly to your email.\n\n"
            "Would you like to see a quick preview of how this works for your shop?",
        ),
        # Clean 5: Veterinary clinic
        (
            "Vet Clinic",
            "Hi Rachel,\n\n"
            "Saw that Highland Vet Clinic does not have an online option for prescription refills.\n\n"
            "I build lightweight clinic websites with simple refill request forms that save front desk time.\n\n"
            "Would you be open to a brief preview for Highland Vet Clinic?",
        ),
    ]

    # ---------------- 10 SLOP DRAFTS ----------------
    SLOP_DRAFTS = [
        # Slop 1: Exceeds 90 words
        (
            "Word Count Exceeded",
            "Hi Alex,\n\n"
            "Saw that appointment booking at Downtown Dental currently requires calling during business hours. "
            "Many potential patients browse for local dentists during their evening commute or over the weekend when your office is closed. "
            "Without an online booking system, these visitors often end up clicking on another local clinic rather than waiting until Monday morning to place a phone call. "
            "I build modern responsive websites with automated booking widgets that confirm appointment slots in real time. "
            "This ensures your clinic captures new patient inquiries twenty-four hours a day without requiring extra reception staff or phone calls during peak clinic hours. "
            "Would you be open to a quick concept preview?",
            "Exceeds max word count",
        ),
        # Slop 2: Em-dash
        (
            "Em-Dash Violation",
            "Hi Marco,\n\n"
            "Saw that Trattoria Bella's online menu opens as a PDF file — which can be hard to read on mobile.\n\n"
            "I build fast mobile restaurant websites with clear menus.\n\n"
            "Would you be open to a 2-minute preview?",
            "Contains em-dash",
        ),
        # Slop 3: Exclamation mark
        (
            "Exclamation Mark Violation",
            "Hi Sarah,\n\n"
            "Saw that Glow Salon shares services on Instagram without a dedicated booking site.\n\n"
            "I build websites with automatic booking forms so clients can book appointments online!\n\n"
            "Would you be open to a 2-minute preview for Glow Salon?",
            "Contains exclamation mark",
        ),
        # Slop 4: Banned opener "I hope this finds you well"
        (
            "Banned Opener: Hope finds you well",
            "Hi Alex,\n\n"
            "I hope this finds you well. Saw that Downtown Dental requires calling for appointments.\n\n"
            "I build clean websites with online booking forms.\n\n"
            "Would you be open to a 2-minute preview?",
            "banned opener",
        ),
        # Slop 5: Banned opener "I came across"
        (
            "Banned Opener: I came across",
            "Hi Marco,\n\n"
            "I came across Trattoria Bella while looking at local Italian spots.\n\n"
            "I build fast restaurant websites with mobile menus.\n\n"
            "Would you be open to a 2-minute preview?",
            "banned opener",
        ),
        # Slop 6: Banned opener "I'm reaching out"
        (
            "Banned Opener: I'm reaching out",
            "Hi Sarah,\n\n"
            "I'm reaching out because I saw Glow Salon does not have an online booking website.\n\n"
            "I build simple websites with automatic appointment forms.\n\n"
            "Would you be open to a 2-minute preview?",
            "banned opener",
        ),
        # Slop 7: Banned opener "I noticed that"
        (
            "Banned Opener: I noticed that",
            "Hi David,\n\n"
            "I noticed that Oak Street Auto currently takes repair quote requests only through the phone.\n\n"
            "I build simple web inquiry forms that send requests to your inbox.\n\n"
            "Would you like to see a quick preview?",
            "banned opener",
        ),
        # Slop 8: Banned buzzwords ("leverage", "streamline", "cutting-edge")
        (
            "Banned Buzzwords Violation",
            "Hi Rachel,\n\n"
            "Saw that Highland Vet Clinic does not have an online refill system.\n\n"
            "Our cutting-edge platform will streamline your operations and leverage automation to elevate your clinic.\n\n"
            "Would you be open to a brief preview?",
            "banned words",
        ),
        # Slop 9: Triplet list ("save time, cut costs, and increase sales")
        (
            "Triplet List Violation",
            "Hi Alex,\n\n"
            "Saw that appointment booking at Downtown Dental requires calling during hours.\n\n"
            "I build web booking pages that save time, cut costs, and get more patients.\n\n"
            "Would you be open to a 2-minute preview?",
            "triplet list",
        ),
        # Slop 10: "Not just X, but Y" construction
        (
            "Not Just X But Y Violation",
            "Hi Marco,\n\n"
            "Saw that Trattoria Bella's menu opens as a PDF file on phones.\n\n"
            "I build websites that are not just an online menu, but a complete reservation engine.\n\n"
            "Would you be open to a 2-minute preview?",
            "not just X, but Y",
        ),
    ]

    def test_clean_drafts_pass_validation(self):
        """Verify that all 5 clean drafts pass with zero violations."""
        for label, draft_text in self.CLEAN_DRAFTS:
            with self.subTest(draft=label):
                res = validate_draft(draft_text, max_words=90)
                self.assertTrue(
                    res.is_valid,
                    f"Clean draft '{label}' unexpectedly failed with violations: {res.violations}",
                )
                self.assertEqual(len(res.violations), 0)
                self.assertLessEqual(res.word_count, 90)

    def test_slop_drafts_fail_validation(self):
        """Verify that all 10 slop drafts fail validation with the expected violation."""
        for label, draft_text, expected_keyword in self.SLOP_DRAFTS:
            with self.subTest(draft=label):
                res = validate_draft(draft_text, max_words=90)
                self.assertFalse(
                    res.is_valid,
                    f"Slop draft '{label}' was expected to fail validation, but passed.",
                )
                self.assertGreater(len(res.violations), 0)
                violations_str = " ".join(res.violations).lower()
                self.assertIn(
                    expected_keyword.lower(),
                    violations_str,
                    f"Expected '{expected_keyword}' in violations, got: {res.violations}",
                )


if __name__ == "__main__":
    unittest.main()
