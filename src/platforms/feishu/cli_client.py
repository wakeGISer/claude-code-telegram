"""Async subprocess wrapper around feishu-cli Go binary.

All Feishu API operations (send message, delete, reply, etc.) go through
the feishu-cli binary which handles token management and API calls.
"""

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

import structlog

logger = structlog.get_logger()

FEISHU_CLI_PATH = Path.home() / "go" / "bin" / "feishu-cli"


class FeishuCLIError(Exception):
    """Error from feishu-cli subprocess."""

    def __init__(self, message: str, stderr: str = "", returncode: int = -1) -> None:
        super().__init__(message)
        self.stderr = stderr
        self.returncode = returncode


class FeishuCLIClient:
    """Async wrapper for feishu-cli subprocess calls."""

    def __init__(
        self,
        cli_path: Optional[str] = None,
        app_id: Optional[str] = None,
        app_secret: Optional[str] = None,
    ) -> None:
        self.cli_path = cli_path or str(FEISHU_CLI_PATH)
        self.app_id = app_id
        self.app_secret = app_secret

    async def send_text(
        self,
        receive_id: str,
        text: str,
        id_type: str = "chat_id",
    ) -> Dict[str, Any]:
        """Send a text message."""
        return await self._run(
            "msg", "send",
            "--receive-id-type", id_type,
            "--receive-id", receive_id,
            "--text", text,
            "--output", "json",
        )

    async def send_card(
        self,
        receive_id: str,
        card_json: str,
        id_type: str = "chat_id",
    ) -> Dict[str, Any]:
        """Send an interactive card message."""
        return await self._run(
            "msg", "send",
            "--receive-id-type", id_type,
            "--receive-id", receive_id,
            "--msg-type", "interactive",
            "--content", card_json,
            "--output", "json",
        )

    async def send_image(
        self,
        receive_id: str,
        image_path: str,
        id_type: str = "chat_id",
    ) -> Dict[str, Any]:
        """Send a local image (auto-uploaded by feishu-cli)."""
        return await self._run(
            "msg", "send",
            "--receive-id-type", id_type,
            "--receive-id", receive_id,
            "--image", image_path,
            "--output", "json",
        )

    async def send_file(
        self,
        receive_id: str,
        file_path: str,
        id_type: str = "chat_id",
    ) -> Dict[str, Any]:
        """Send a local file (auto-uploaded by feishu-cli)."""
        return await self._run(
            "msg", "send",
            "--receive-id-type", id_type,
            "--receive-id", receive_id,
            "--file", file_path,
            "--output", "json",
        )

    async def reply(
        self,
        message_id: str,
        text: str,
    ) -> Dict[str, Any]:
        """Reply to a message."""
        return await self._run(
            "msg", "reply",
            message_id,
            "--text", text,
            "--output", "json",
        )

    async def delete(self, message_id: str) -> Dict[str, Any]:
        """Delete a message."""
        return await self._run("msg", "delete", message_id)

    async def get_message(self, message_id: str) -> Dict[str, Any]:
        """Get message details."""
        return await self._run("msg", "get", message_id, "--output", "json")

    async def _run(self, *args: str) -> Dict[str, Any]:
        """Execute feishu-cli with given arguments."""
        cmd = [self.cli_path, *args]

        env = dict(os.environ)
        if self.app_id:
            env["FEISHU_APP_ID"] = self.app_id
        if self.app_secret:
            env["FEISHU_APP_SECRET"] = self.app_secret

        logger.debug("feishu-cli exec", cmd=" ".join(cmd[:6]))

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        except asyncio.TimeoutError:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
            raise FeishuCLIError("feishu-cli timed out after 30s")
        except FileNotFoundError:
            raise FeishuCLIError(
                f"feishu-cli not found at {self.cli_path}. "
                "Install: go install github.com/riba2534/feishu-cli@latest"
            )

        stdout_str = stdout.decode("utf-8", errors="replace").strip()
        stderr_str = stderr.decode("utf-8", errors="replace").strip()

        if proc.returncode != 0:
            logger.warning(
                "feishu-cli failed",
                returncode=proc.returncode,
                stderr=stderr_str[:500],
            )
            raise FeishuCLIError(
                f"feishu-cli exited {proc.returncode}: {stderr_str[:300]}",
                stderr=stderr_str,
                returncode=proc.returncode or -1,
            )

        if not stdout_str:
            return {}

        try:
            return json.loads(stdout_str)  # type: ignore[no-any-return]
        except json.JSONDecodeError:
            # Some commands output non-JSON (e.g. delete confirmation)
            return {"raw_output": stdout_str}
