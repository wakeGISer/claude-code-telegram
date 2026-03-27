"""Tests for Feishu CLI client subprocess wrapper."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from src.platforms.feishu.cli_client import FeishuCLIClient, FeishuCLIError


@pytest.fixture
def cli() -> FeishuCLIClient:
    return FeishuCLIClient(
        cli_path="/usr/bin/echo",  # use echo as a dummy binary
        app_id="test_app",
        app_secret="test_secret",
    )


class TestFeishuCLIClient:
    async def test_run_success(self) -> None:
        """Successful subprocess returns parsed JSON."""
        client = FeishuCLIClient(cli_path="/bin/echo")

        # Mock subprocess to return JSON
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(
            return_value=(
                json.dumps({"message_id": "om_123"}).encode(),
                b"",
            )
        )
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await client._run("msg", "send", "--text", "hello")
            assert result["message_id"] == "om_123"

    async def test_run_failure(self) -> None:
        """Non-zero exit code raises FeishuCLIError."""
        client = FeishuCLIClient(cli_path="/bin/false")

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b"error msg"))
        mock_proc.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with pytest.raises(FeishuCLIError) as exc_info:
                await client._run("msg", "send")
            assert exc_info.value.returncode == 1

    async def test_run_non_json_output(self) -> None:
        """Non-JSON output returns raw_output dict."""
        client = FeishuCLIClient()

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(
            return_value=(b"Message deleted successfully", b"")
        )
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await client._run("msg", "delete", "om_123")
            assert result["raw_output"] == "Message deleted successfully"

    async def test_run_empty_output(self) -> None:
        """Empty stdout returns empty dict."""
        client = FeishuCLIClient()

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await client._run("msg", "delete", "om_123")
            assert result == {}

    async def test_send_text(self) -> None:
        """send_text calls _run with correct args."""
        client = FeishuCLIClient(app_id="app", app_secret="secret")

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(
            return_value=(json.dumps({"message_id": "om_1"}).encode(), b"")
        )
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            result = await client.send_text("oc_chat", "hello")
            assert result["message_id"] == "om_1"
            # Verify the command includes msg send
            call_args = mock_exec.call_args[0]
            assert "msg" in call_args
            assert "send" in call_args

    async def test_env_vars_passed(self) -> None:
        """App ID and secret are passed as env vars."""
        client = FeishuCLIClient(app_id="my_app", app_secret="my_secret")

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"{}", b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            await client._run("msg", "send")
            call_kwargs = mock_exec.call_args[1]
            env = call_kwargs["env"]
            assert env["FEISHU_APP_ID"] == "my_app"
            assert env["FEISHU_APP_SECRET"] == "my_secret"
