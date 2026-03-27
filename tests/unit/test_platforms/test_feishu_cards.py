"""Tests for Feishu card builder."""

import json

from src.platforms.feishu.cards import (
    FeishuCard,
    error_card,
    progress_card,
    result_card,
)


class TestFeishuCard:
    def test_simple_card(self) -> None:
        card = FeishuCard().header("Test", color="blue").markdown("hello").to_dict()
        assert card["header"]["template"] == "blue"
        assert card["header"]["title"]["content"] == "Test"
        assert len(card["elements"]) == 1
        assert card["elements"][0]["tag"] == "markdown"

    def test_card_with_note(self) -> None:
        card = FeishuCard().header("H").note("footer text").to_dict()
        # Note element is appended at the end
        note_elem = card["elements"][-1]
        assert note_elem["tag"] == "note"
        assert note_elem["elements"][0]["content"] == "footer text"

    def test_divider(self) -> None:
        card = FeishuCard().markdown("a").divider().markdown("b").to_dict()
        assert card["elements"][1]["tag"] == "hr"

    def test_to_json(self) -> None:
        card_json = FeishuCard().header("T").markdown("m").to_json()
        parsed = json.loads(card_json)
        assert "header" in parsed
        assert "elements" in parsed

    def test_wide_screen_mode(self) -> None:
        card = FeishuCard().to_dict()
        assert card["config"]["wide_screen_mode"] is True


class TestCardHelpers:
    def test_progress_card(self) -> None:
        card_json = progress_card()
        card = json.loads(card_json)
        assert "header" in card

    def test_result_card(self) -> None:
        card_json = result_card("done!", duration_s=2.5, tools_count=3)
        card = json.loads(card_json)
        assert card["header"]["template"] == "green"

    def test_result_card_truncation(self) -> None:
        long_content = "x" * 25000
        card_json = result_card(long_content)
        card = json.loads(card_json)
        md_content = card["elements"][0]["content"]
        assert len(md_content) < 25000
        assert "truncated" in md_content

    def test_error_card(self) -> None:
        card_json = error_card("something went wrong")
        card = json.loads(card_json)
        assert card["header"]["template"] == "red"
