"""Convert Feishu event payloads to platform-agnostic IncomingMessage."""

import json
from typing import Any, Dict, Optional

import structlog

from ..types import AttachedFile, AttachedImage, IncomingMessage

logger = structlog.get_logger()


def parse_feishu_event(event_data: Dict[str, Any]) -> Optional[IncomingMessage]:
    """Convert a Feishu im.message.receive_v1 event into IncomingMessage.

    Args:
        event_data: The 'event' field from Feishu's event callback body.

    Returns:
        IncomingMessage or None if the event can't be parsed.
    """
    message = event_data.get("message", {})
    sender_info = event_data.get("sender", {})

    msg_type = message.get("message_type", "")
    message_id = message.get("message_id", "")
    chat_id = message.get("chat_id", "")
    chat_type = message.get("chat_type", "")

    # Sender info
    sender_id_obj = sender_info.get("sender_id", {})
    user_id = sender_id_obj.get("open_id", "")
    # Feishu doesn't always provide display name in event; fallback to user_id
    display_name = sender_info.get("sender_type", user_id)

    # Parse content JSON
    content_str = message.get("content", "{}")
    try:
        content = json.loads(content_str)
    except (json.JSONDecodeError, TypeError):
        content = {}

    text = ""
    command = None
    command_args: list[str] = []
    files: list[AttachedFile] = []
    images: list[AttachedImage] = []

    if msg_type == "text":
        text = content.get("text", "")
        # Strip @mentions: Feishu wraps mentions as @_user_1 etc.
        # The actual mention info is in message.mentions[]
        mentions = message.get("mentions", [])
        for mention in mentions:
            key = mention.get("key", "")
            if key:
                text = text.replace(key, "").strip()

    elif msg_type == "image":
        image_key = content.get("image_key", "")
        if image_key:
            images.append(AttachedImage(file_id=image_key))

    elif msg_type == "file":
        file_key = content.get("file_key", "")
        file_name = content.get("file_name", "unknown")
        images_or_files = True  # noqa: F841
        files.append(
            AttachedFile(
                file_id=file_key,
                filename=file_name,
                size=0,
            )
        )

    elif msg_type == "post":
        # Rich text: extract plain text from nested structure
        text = _extract_post_text(content)

    else:
        logger.debug("Unsupported feishu message type", msg_type=msg_type)
        text = f"[Unsupported message type: {msg_type}]"

    # Parse commands (messages starting with /)
    if text.startswith("/"):
        parts = text.split(None, 1)
        command = parts[0].lstrip("/")
        if len(parts) > 1:
            command_args = parts[1].split()
        text = parts[1] if len(parts) > 1 else ""

    # Thread ID for topic groups
    thread_id = message.get("thread_id")

    return IncomingMessage(
        platform="feishu",
        chat_id=chat_id,
        message_id=message_id,
        user_id=user_id,
        display_name=display_name,
        text=text,
        command=command,
        command_args=command_args,
        thread_id=thread_id,
        files=files,
        images=images,
        raw=event_data,
    )


def _extract_post_text(content: Dict[str, Any]) -> str:
    """Extract plain text from Feishu post (rich text) message content."""
    parts: list[str] = []
    # Post content structure: {"title": "...", "content": [[{tag, text}, ...]]}
    title = content.get("title", "")
    if title:
        parts.append(title)

    for line in content.get("content", []):
        line_parts: list[str] = []
        for element in line:
            tag = element.get("tag", "")
            if tag == "text":
                line_parts.append(element.get("text", ""))
            elif tag == "a":
                line_parts.append(element.get("text", element.get("href", "")))
            elif tag == "at":
                # Skip @mentions in post
                pass
        if line_parts:
            parts.append("".join(line_parts))

    return "\n".join(parts)
