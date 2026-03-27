"""Feishu interactive card message builder."""

import json
from typing import List, Optional


class FeishuCard:
    """Fluent builder for Feishu interactive message cards."""

    COLORS = {
        "blue": "blue",
        "green": "green",
        "red": "red",
        "orange": "orange",
        "grey": "grey",
    }

    def __init__(self) -> None:
        self._header: Optional[dict] = None
        self._elements: List[dict] = []
        self._notes: List[dict] = []

    def header(self, title: str, color: str = "blue") -> "FeishuCard":
        self._header = {
            "template": self.COLORS.get(color, "blue"),
            "title": {"tag": "plain_text", "content": title},
        }
        return self

    def markdown(self, text: str) -> "FeishuCard":
        self._elements.append({
            "tag": "markdown",
            "content": text,
        })
        return self

    def text(self, text: str) -> "FeishuCard":
        self._elements.append({
            "tag": "div",
            "text": {"tag": "plain_text", "content": text},
        })
        return self

    def divider(self) -> "FeishuCard":
        self._elements.append({"tag": "hr"})
        return self

    def note(self, text: str) -> "FeishuCard":
        self._notes.append({
            "tag": "plain_text",
            "content": text,
        })
        return self

    def to_dict(self) -> dict:
        card: dict = {
            "config": {"wide_screen_mode": True},
            "elements": list(self._elements),
        }
        if self._header:
            card["header"] = self._header
        if self._notes:
            card["elements"].append({
                "tag": "note",
                "elements": self._notes,
            })
        return card

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


def progress_card() -> str:
    """Build a simple 'processing' card."""
    return (
        FeishuCard()
        .header("\u23f3 \u5904\u7406\u4e2d...", color="blue")
        .markdown("Claude is working on your request...")
        .to_json()
    )


def result_card(
    content: str,
    duration_s: float = 0,
    tools_count: int = 0,
    working_dir: str = "",
) -> str:
    """Build a result card from Claude response."""
    card = FeishuCard().header("\u2705 \u5b8c\u6210", color="green")

    # Truncate very long content for card (feishu card markdown has limits)
    if len(content) > 20000:
        content = content[:20000] + "\n\n... (truncated)"
    card.markdown(content)

    meta_parts = []
    if working_dir:
        meta_parts.append(f"\U0001f4c2 {working_dir}")
    if tools_count:
        meta_parts.append(f"\U0001f527 {tools_count} tools")
    if duration_s > 0:
        meta_parts.append(f"\u23f1 {duration_s:.1f}s")

    if meta_parts:
        card.divider()
        card.note(" | ".join(meta_parts))

    return card.to_json()


def error_card(error_message: str) -> str:
    """Build an error card."""
    return (
        FeishuCard()
        .header("\u274c \u6267\u884c\u5931\u8d25", color="red")
        .markdown(f"```\n{error_message[:2000]}\n```")
        .to_json()
    )
