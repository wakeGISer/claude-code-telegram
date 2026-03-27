"""Convert Telegram Update objects to platform-agnostic IncomingMessage."""

from typing import Optional

from telegram import Update

from ..types import AttachedFile, AttachedImage, IncomingMessage


def to_incoming_message(update: Update) -> Optional[IncomingMessage]:
    """Convert a Telegram Update into a canonical IncomingMessage.

    Returns None if the update doesn't contain a usable message.
    """
    message = update.effective_message
    user = update.effective_user
    if not message or not user:
        return None

    text = message.text or message.caption or ""
    command = None
    command_args: list[str] = []

    # Parse /command from text
    if text.startswith("/"):
        parts = text.split(None, 1)
        cmd_part = parts[0].lstrip("/")
        # Strip @botname suffix
        if "@" in cmd_part:
            cmd_part = cmd_part.split("@")[0]
        command = cmd_part
        if len(parts) > 1:
            command_args = parts[1].split()
        text = parts[1] if len(parts) > 1 else ""

    # Collect attached files
    files: list[AttachedFile] = []
    if message.document:
        doc = message.document
        files.append(
            AttachedFile(
                file_id=doc.file_id,
                filename=doc.file_name or "unknown",
                size=doc.file_size or 0,
                mime_type=doc.mime_type,
            )
        )

    # Collect attached images
    images: list[AttachedImage] = []
    if message.photo:
        # Telegram sends multiple sizes; take the largest
        largest = message.photo[-1]
        images.append(
            AttachedImage(
                file_id=largest.file_id,
                width=largest.width,
                height=largest.height,
            )
        )

    # Thread ID (forum topics / private topics)
    thread_id = None
    raw_thread = getattr(message, "message_thread_id", None)
    if isinstance(raw_thread, int) and raw_thread > 0:
        thread_id = str(raw_thread)

    return IncomingMessage(
        platform="telegram",
        chat_id=str(message.chat_id),
        message_id=str(message.message_id),
        user_id=str(user.id),
        display_name=user.full_name or user.username or str(user.id),
        text=text,
        command=command,
        command_args=command_args,
        thread_id=thread_id,
        files=files,
        images=images,
        raw=update,
    )
