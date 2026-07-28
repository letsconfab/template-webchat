"""Regression fixtures derived from the eleven negative-feedback cases.

These tests pin the answer-quality / trust contracts from
docs/evolution/2026-07-27-negative-feedback-evolution.md. They do not call a
live LLM; they verify that generation helpers encode the behaviors required to
address each critical theme.

NF-DIAGRAM is an additive prompt-contract pin from
docs/field-debug/2026-07-28-missing-mermaid-diagrams.md (not one of the
original eleven NF cases).
"""

from __future__ import annotations

import unittest

from backend.services.chat_generation import build_system_prompt, extract_followups
from backend.services.source_provenance import format_retrieval_source, google_doc_url


# Map of NF-id → required contract keywords / behaviors in the system prompt.
CRITICAL_CASES = [
    # Progressive / brevity (NF-01, NF-09, NF-11)
    {
        "id": "NF-01",
        "theme": "progressive_actionable",
        "must_include": ["120–180 words", "three actionable steps", "go deeper"],
    },
    {
        "id": "NF-09",
        "theme": "brevity",
        "must_include": ["120–180 words", "tables unless requested"],
    },
    {
        "id": "NF-11",
        "theme": "progressive_disclosure",
        "must_include": ["go deeper", "120–180 words"],
    },
    # Relevance / freshness / trust (NF-02, NF-07)
    {
        "id": "NF-02",
        "theme": "relevance_freshness",
        "must_include": ["ALO evidence required", "Clarify or decline"],
    },
    {
        "id": "NF-07",
        "theme": "ip_evidence_boundary",
        "must_include": [
            "licensing",
            "IP claims",
            "say so",
            "Do not silently fall back",
        ],
        "must_not_include": ["answer from your own knowledge"],
    },
    # Clarification (NF-08, NF-10)
    {
        "id": "NF-08",
        "theme": "clarification_on_ambiguity",
        "must_include": ["clarifying question", "ambiguous"],
    },
    {
        "id": "NF-10",
        "theme": "cognitive_load_adaptation",
        "must_include": ["clarifying question", "120–180 words"],
    },
    # Guided continuation (NF-05) — follow-up contract
    {
        "id": "NF-05",
        "theme": "suggested_followups",
        "must_include": [":::followups", "up to three follow-up"],
    },
    # Visual structure (diagram contract; field-debug 2026-07-28)
    {
        "id": "NF-DIAGRAM",
        "theme": "mermaid_structure_diagram",
        "must_include": [
            "```mermaid",
            "Do not replace the concise textual explanation with a diagram",
            "Simple factual answers should not acquire a diagram by default",
        ],
    },
]


class NegativeFeedbackRegressionTests(unittest.TestCase):
    def test_critical_prompt_contracts_cover_regression_set(self) -> None:
        prompt = build_system_prompt(has_kb=True)
        for case in CRITICAL_CASES:
            with self.subTest(case=case["id"]):
                for needle in case["must_include"]:
                    self.assertIn(
                        needle,
                        prompt,
                        f"{case['id']} ({case['theme']}) missing: {needle!r}",
                    )
                for needle in case.get("must_not_include", []):
                    self.assertNotIn(
                        needle.lower(),
                        prompt.lower(),
                        f"{case['id']} should not allow: {needle!r}",
                    )

    def test_nf03_nf04_product_surfaces_are_out_of_prompt_but_documented(self) -> None:
        """NF-03/NF-04 are product UX (sessions + journeys), not prompt text.

        This sentinel documents that they are covered by API/UI work rather than
        the system prompt regression set above.
        """
        product_cases = {"NF-03", "NF-04"}
        prompt_cases = {c["id"] for c in CRITICAL_CASES}
        self.assertTrue(product_cases.isdisjoint(prompt_cases))

    def test_nf06_file_upload_remains_deferred(self) -> None:
        prompt = build_system_prompt(has_kb=True)
        self.assertNotIn("upload", prompt.lower())

    def test_mermaid_structure_trigger_is_stronger_than_substring(self) -> None:
        """Diagram contract must name structure triggers (beyond fence syntax).

        Live LLM rehearsal of an INTEGRATE-style question remains a non-prod
        eval step; this pins the prompt language that rehearsal should exercise.
        """
        prompt = build_system_prompt(has_kb=True)
        self.assertIn("```mermaid", prompt)
        self.assertIn("multi-part framework", prompt)
        self.assertIn("process/sequence", prompt)
        self.assertIn("system relationship", prompt)

    def test_citation_contract_produces_google_knowledge_source_link(self) -> None:
        url = google_doc_url("fileABC")
        text = format_retrieval_source(
            title="ALO Licensing Policy",
            passage="Licensing requires board approval.",
            google_url=url,
            locator="Heading: Licensing",
            modified_time="2026-07-01T00:00:00.000Z",
            chunk_index=1,
            relevance=0.9,
        )
        self.assertIn("ALO Licensing Policy", text)
        self.assertIn(url, text)
        self.assertIn("Heading: Licensing", text)

    def test_followup_block_is_stripped_for_tester_facing_content(self) -> None:
        raw = (
            "Direct answer with three steps.\n\n"
            ":::followups\n"
            "- What is the next facilitation step?\n"
            "- How does licensing interact with IP?\n"
            ":::\n"
        )
        cleaned, followups = extract_followups(raw)
        self.assertNotIn(":::followups", cleaned)
        self.assertEqual(len(followups), 2)


if __name__ == "__main__":
    unittest.main()
