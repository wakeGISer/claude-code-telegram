"""Telegram implementation of PlatformSender."""

from pathlib import Path
from typing import Optional

import structlog
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

logger = structlog.get_logger()

# Telegram rate limit: ~30 msgs/sec globally, ~1 msg/sec per chat
MAX_MESSAGE_LENGTH = 4096


class TelegramSender:
    """Send messages via Telegram Bot API."""

    platform_name = "telegram"

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def send_text(
        self,
        chat_id: str,
        text: str,
        reply_to: Optional[str] = None,
        parse_mode: Optional[str] = None,
        thread_id: Optional[str] = None,
    ) -> str:
        pm = ParseMode.HTML if parse_mode == "HTML" else None
        msg = await self.bot.send_message(
            chat_id=int(chat_id),
            text=text,
            parse_mode=pm,
            reply_to_message_id=int(reply_to) if reply_to else None,
            message_thread_id=int(thread_id) if thread_id else None,
        )
        return str(msg.message_id)

    async def edit_text(
        self,
        chat_id: str,
        message_id: str,
        text: str,
        parse_mode: Optional[str] = None,
    ) -> None:
        pm = ParseMode.HTML if parse_mode == "HTML" else None
        await self.bot.edit_message_text(
            chat_id=int(chat_id),
            message_id=int(message_id),
            text=text,
            parse_mode=pm,
        )

    async def delete_message(self, chat_id: str, message_id: str) -> None:
        try:
            await self.bot.delete_message(
                chat_id=int(chat_id),
                message_id=int(message_id),
            )
        except TelegramError:
            logger.debug(
                "Failed to delete message",
                chat_id=chat_id,
                message_id=message_id,
            )

    async def send_typing(self, chat_id: str) -> None:
        try:
            await self.bot.send_chat_action(int(chat_id), "typing")
        except TelegramError:
            pass

    async def send_image(
        self,
        chat_id: str,
        image_path: Path,
        caption: Optional[str] = None,
        thread_id: Optional[str] = None,
    ) -> str:
        with open(image_path, "rb") as f:
            msg = await self.bot.send_photo(
                chat_id=int(chat_id),
                photo=f,
                caption=caption,
                message_thread_id=int(thread_id) if thread_id else None,
            )
        return str(msg.message_id)

    async def download_file(self, file_id: str, dest: Path) -> Path:
        file = await self.bot.get_file(file_id)
        await file.download_to_drive(str(dest))
        return dest

    def max_message_length(self) -> int:
        return MAX_MESSAGE_LENGTH
