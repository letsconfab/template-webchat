"""Unit tests for answer-quality generation helpers (history + prompt contract)."""

from __future__ import annotations

import unittest

from backend.services.chat_generation import (
    RECENT_MESSAGE_LIMIT,
    build_agent_messages,
    build_system_prompt,
    extract_followups,
)


class BuildSystemPromptTests(unittest.TestCase):
    def test_prompt_includes_concise_first_response_contract(self) -> None:
        prompt = build_system_prompt(has_kb=True)
        self.assertIn("120–180 words", prompt)
        self.assertIn("three actionable steps", prompt)
        self.assertIn("clarifying question", prompt)
        self.assertIn("Mermaid", prompt)

    def test_prompt_requires_alo_evidence_and_forbids_silent_fallback(self) -> None:
        prompt = build_system_prompt(has_kb=True)
        self.assertIn("ALO evidence required", prompt)
        self.assertIn("general guidance", prompt.lower())
        self.assertNotIn("answer from your own knowledge", prompt.lower())
        self.assertIn("say so", prompt.lower())

    def test_prompt_without_kb_still_has_concise_contract(self) -> None:
        prompt = build_system_prompt(has_kb=False)
        self.assertIn("120–180 words", prompt)
        self.assertNotIn("retrieve_knowledge", prompt)


class BuildAgentMessagesTests(unittest.TestCase):
    def test_includes_bounded_prior_turns_before_latest_user_message(self) -> None:
        history = [
            {"role": "user", "content": "What is ALO?"},
            {"role": "assistant", "content": "ALO is …"},
            {"role": "user", "content": "Give me the next step."},
        ]
        messages = build_agent_messages(history, latest_user_message="Give me the next step.")
        roles = [m.type for m in messages]
        self.assertEqual(roles[-1], "human")
        self.assertEqual(messages[-1].content, "Give me the next step.")
        self.assertGreaterEqual(len(messages), 3)
        self.assertEqual(messages[0].content, "What is ALO?")

    def test_does_not_duplicate_latest_user_message_already_in_history(self) -> None:
        history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
            {"role": "user", "content": "Latest"},
        ]
        messages = build_agent_messages(history, latest_user_message="Latest")
        user_contents = [m.content for m in messages if m.type == "human"]
        self.assertEqual(user_contents.count("Latest"), 1)

    def test_keeps_only_recent_messages_when_history_is_long(self) -> None:
        history = []
        for i in range(RECENT_MESSAGE_LIMIT + 10):
            role = "user" if i % 2 == 0 else "assistant"
            history.append({"role": role, "content": f"msg-{i}"})
        latest = history[-1]["content"] if history[-1]["role"] == "user" else "new"
        messages = build_agent_messages(history, latest_user_message=latest)
        # One optional summary human/system note + recent window + ensure bound
        self.assertLessEqual(len(messages), RECENT_MESSAGE_LIMIT + 2)
        self.assertTrue(
            any("earlier messages" in (m.content or "").lower() for m in messages)
        )


    def test_includes_active_journey_context_when_provided(self) -> None:
        messages = build_agent_messages(
            [],
            latest_user_message="Start",
            active_journey={
                "title": "Licensing basics",
                "purpose": "Understand licensing",
                "knowledge_source_labels": ["ALO Licensing Policy"],
            },
        )
        self.assertTrue(
            any("Active starter journey: Licensing basics" in m.content for m in messages)
        )
        self.assertTrue(
            any("ALO Licensing Policy" in m.content for m in messages)
        )


class ExtractFollowupsTests(unittest.TestCase):
    def test_strips_followups_block_and_returns_up_to_three(self) -> None:
        raw = (
            "Here is the answer.\n\n"
            ":::followups\n"
            "- How does licensing work?\n"
            "- What is the next facilitation step?\n"
            "- Unrelated general coding tip\n"
            "- Fourth should be dropped\n"
            ":::\n"
        )
        cleaned, followups = extract_followups(raw)
        self.assertEqual(cleaned.strip(), "Here is the answer.")
        self.assertEqual(len(followups), 3)
        self.assertEqual(followups[0], "How does licensing work?")

    def test_returns_original_when_no_followups_block(self) -> None:
        raw = "Just an answer."
        cleaned, followups = extract_followups(raw)
        self.assertEqual(cleaned, raw)
        self.assertEqual(followups, [])


if __name__ == "__main__":
    unittest.main()
