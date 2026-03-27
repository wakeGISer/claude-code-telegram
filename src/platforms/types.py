"""Platform-agnostic message types and sender protocol.

These types decouple the core orchestrator from any specific
messaging platform (Telegram, Feishu, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional, Protocol, runtime_checkable


@dataclass
class AttachedFile:
    """A file attached to an incoming message."""

    file_id: str
    filename: str
    size: int
    mime_type: Optional[str] = None


@dataclass
class AttachedImage:
    """An image attached to an incoming message."""

    file_id: str
    width: Optional[int] = None
    height: Optional[int] = None


@dataclass
class IncomingMessage:
    """Platform-agnostic incoming message.

    Adapters convert platform-native events (Telegram Update,
    Feishu im.message.receive_v1) into this canonical form before
    handing off to the shared orchestrator.
    """

    platform: str  # "telegram" | "feishu"
    chat_id: str
    message_id: str
    user_id: str  # platform-specific, always str
    display_name: str
    text: str = ""
    command: Optional[str] = None  # "new", "status" (no slash)
    command_args: List[str] = field(default_factory=list)
    thread_id: Optional[str] = None
    files: List[AttachedFile] = field(default_factory=list)
    images: List[AttachedImage] = field(default_factory=list)
    raw: Any = None  # original platform object


@runtime_checkable
class PlatformSender(Protocol):
    """Interface for sending messages back to a platform.

    Each platform adapter implements this protocol so the
    orchestrator can reply without knowing platform details.
    """

    platform_name: str

    async def send_text(
        self,
        chat_id: str,
        text: str,
        reply_to: Optional[str] = None,
        parse_mode: Optional[str] = None,
        thread_id: Optional[str] = None,
    ) -> str:
        """Send a text message. Returns the sent message ID."""
        ...

    async def edit_text(
        self,
        chat_id: str,
        message_id: str,
        text: str,
        parse_mode: Optional[str] = None,
    ) -> None:
        """Edit an existing text message."""
        ...

    async def delete_message(
        self,
        chat_id: str,
        message_id: str,
    ) -> None:
        """Delete a message."""
        ...

    async def send_typing(self, chat_id: str) -> None:
        """Show typing indicator (no-op if platform doesn't support it)."""
        ...

    async def send_image(
        self,
        chat_id: str,
        image_path: Path,
        caption: Optional[str] = None,
        thread_id: Optional[str] = None,
    ) -> str:
        """Send an image. Returns the sent message ID."""
        ...

    async def download_file(self, file_id: str, dest: Path) -> Path:
        """Download a file by platform file_id to dest path."""
        ...

    def max_message_length(self) -> int:
        """Maximum text message length for this platform."""
        ...
