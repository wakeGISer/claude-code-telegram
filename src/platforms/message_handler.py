"""Shared message handler for platform-agnostic Claude interactions.

This is the core logic extracted from the Telegram orchestrator,
usable by any platform adapter. Handles:
- Text messages → Claude → response
- Progress indication (send + delete pattern)
- Response formatting and delivery
"""

import time
from pathlib import Path
from typing import Any, Dict, Optional

import structlog

from ..claude.facade import ClaudeIntegration
from ..storage.facade import Storage
from .types import IncomingMessage, PlatformSender

logger = structlog.get_logger()


class SharedMessageHandler:
    """Platform-agnostic handler: IncomingMessage → Claude → reply via sender."""

    def __init__(
        self,
        claude_integration: ClaudeIntegration,
        storage: Optional[Storage] = None,
        approved_directory: Optional[Path] = None,
    ) -> None:
        self.claude = claude_integration
        self.storage = storage
        self.approved_directory = approved_directory or Path(".")
        # Per-user session tracking (platform:user_id -> session_id)
        self._sessions: Dict[str, Optional[str]] = {}

    def _session_key(self, msg: IncomingMessage) -> str:
        return f"{msg.platform}:{msg.user_id}"

    async def handle_text(
        self,
        msg: IncomingMessage,
        sender: PlatformSender,
    ) -> None:
        """Handle a text message by routing it through Claude."""
        if not msg.text.strip():
            return

        session_key = self._session_key(msg)
        session_id = self._sessions.get(session_key)

        # Send progress indicator
        progress_id = ""
        try:
            progress_id = await sender.send_text(
                msg.chat_id, "\u23f3 \u5904\u7406\u4e2d..."
            )
        except Exception:
            logger.debug("Failed to send progress message")

        start_time = time.time()
        success = True

        try:
            response = await self.claude.run_command(
                prompt=msg.text,
                working_directory=self.approved_directory,
                user_id=int(msg.user_id) if msg.user_id.isdigit() else 0,
                session_id=session_id,
            )

            self._sessions[session_key] = response.session_id
            content = response.content or "(empty response)"

        except Exception as e:
            success = False
            logger.error(
                "Claude failed",
                error=str(e),
                platform=msg.platform,
                user_id=msg.user_id,
            )
            content = f"\u274c Error: {str(e)[:500]}"

        finally:
            # Delete progress message
            if progress_id:
                try:
                    await sender.delete_message(msg.chat_id, progress_id)
                except Exception:
                    pass

        # Split and send response
        max_len = sender.max_message_length()
        chunks = _split_message(content, max_len)

        for chunk in chunks:
            try:
                await sender.send_text(
                    msg.chat_id, chunk, reply_to=msg.message_id
                )
            except Exception as send_err:
                logger.warning("Failed to send chunk", error=str(send_err))
                # Retry without reply_to and without parse_mode
                try:
                    await sender.send_text(msg.chat_id, chunk)
                except Exception:
                    logger.error("Failed to send response completely")

        # Store interaction
        if self.storage and success:
            try:
                await self.storage.save_claude_interaction(
                    user_id=int(msg.user_id) if msg.user_id.isdigit() else 0,
                    session_id=response.session_id,  # type: ignore[possibly-undefined]
                    prompt=msg.text,
                    response=response,  # type: ignore[possibly-undefined]
                    ip_address=None,
                )
            except Exception as e:
                logger.warning("Failed to log interaction", error=str(e))

    async def handle_command(
        self,
        msg: IncomingMessage,
        sender: PlatformSender,
    ) -> None:
        """Handle slash commands."""
        cmd = msg.command or ""

        if cmd == "new":
            session_key = self._session_key(msg)
            self._sessions.pop(session_key, None)
            await sender.send_text(
                msg.chat_id, "\U0001f195 New session started.", reply_to=msg.message_id
            )

        elif cmd == "status":
            session_key = self._session_key(msg)
            sid = self._sessions.get(session_key, "none")
            await sender.send_text(
                msg.chat_id,
                f"\U0001f4ca Status\n"
                f"Platform: {msg.platform}\n"
                f"User: {msg.user_id}\n"
                f"Session: {sid or 'none'}\n"
                f"Directory: {self.approved_directory}",
                reply_to=msg.message_id,
            )

        elif cmd == "start":
            await sender.send_text(
                msg.chat_id,
                "\U0001f44b Hi! I'm Livis, your Claude Code assistant. "
                "Send me any message and I'll route it to Claude.",
                reply_to=msg.message_id,
            )

        else:
            # Unknown commands: treat as text if there are args
            if msg.text.strip():
                await self.handle_text(msg, sender)
            else:
                await sender.send_text(
                    msg.chat_id,
                    f"Unknown command: /{cmd}",
                    reply_to=msg.message_id,
                )


def _split_message(text: str, max_length: int = 4096) -> list[str]:
    """Split long messages at paragraph boundaries."""
    if len(text) <= max_length:
        return [text]

    chunks: list[str] = []
    while text:
        if len(text) <= max_length:
            chunks.append(text)
            break

        split_pos = text.rfind("\n\n", 0, max_length)
        if split_pos == -1:
            split_pos = text.rfind("\n", 0, max_length)
        if split_pos == -1:
            split_pos = text.rfind(" ", 0, max_length)
        if split_pos == -1:
            split_pos = max_length

        chunks.append(text[:split_pos])
        text = text[split_pos:].lstrip()

    return chunks
