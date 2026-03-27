"""Feishu implementation of PlatformSender using feishu-cli."""

from pathlib import Path
from typing import Optional

import structlog

from .cli_client import FeishuCLIClient, FeishuCLIError

logger = structlog.get_logger()

MAX_MESSAGE_LENGTH = 30000


class FeishuSender:
    """Send messages via feishu-cli subprocess."""

    platform_name = "feishu"

    def __init__(self, cli_client: FeishuCLIClient) -> None:
        self.cli = cli_client

    async def send_text(
        self,
        chat_id: str,
        text: str,
        reply_to: Optional[str] = None,
        parse_mode: Optional[str] = None,
        thread_id: Optional[str] = None,
    ) -> str:
        """Send a text message. Returns message_id."""
        try:
            if reply_to:
                result = await self.cli.reply(reply_to, text)
            else:
                result = await self.cli.send_text(chat_id, text)
            return result.get("message_id", "")
        except FeishuCLIError as e:
            logger.error("Feishu send_text failed", error=str(e), chat_id=chat_id)
            raise

    async def edit_text(
        self,
        chat_id: str,
        message_id: str,
        text: str,
        parse_mode: Optional[str] = None,
    ) -> None:
        """Edit not supported by feishu-cli — no-op with warning."""
        logger.debug(
            "Feishu edit_text is no-op (feishu-cli has no update-message)",
            message_id=message_id,
        )

    async def delete_message(self, chat_id: str, message_id: str) -> None:
        """Delete a message."""
        try:
            await self.cli.delete(message_id)
        except FeishuCLIError:
            logger.debug("Failed to delete feishu message", message_id=message_id)

    async def send_typing(self, chat_id: str) -> None:
        """No typing indicator in Feishu — no-op."""
        pass

    async def send_image(
        self,
        chat_id: str,
        image_path: Path,
        caption: Optional[str] = None,
        thread_id: Optional[str] = None,
    ) -> str:
        """Send an image via feishu-cli."""
        try:
            result = await self.cli.send_image(chat_id, str(image_path))
            msg_id = result.get("message_id", "")
            if caption:
                await self.cli.reply(msg_id, caption)
            return msg_id
        except FeishuCLIError as e:
            logger.error("Feishu send_image failed", error=str(e))
            raise

    async def download_file(self, file_id: str, dest: Path) -> Path:
        """Download not yet implemented for Feishu."""
        raise NotImplementedError("Feishu file download not yet implemented")

    def max_message_length(self) -> int:
        return MAX_MESSAGE_LENGTH
