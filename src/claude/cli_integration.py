"""Claude Code CLI subprocess integration.

Spawns `claude -p --output-format stream-json --verbose` as a child process,
giving full access to skills, MCP servers, and plugins — the same environment
as the interactive CLI.
"""

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import structlog

from ..config.settings import Settings
from ..security.validators import SecurityValidator
from .exceptions import (
    ClaudeMCPError,
    ClaudeParsingError,
    ClaudeProcessError,
    ClaudeTimeoutError,
)
from .sdk_integration import ClaudeResponse, StreamUpdate

logger = structlog.get_logger()


class ClaudeCLIManager:
    """Manage Claude Code via CLI subprocess.

    Provides the same ``execute_command`` interface as ``ClaudeSDKManager``
    so that ``ClaudeIntegration`` (the facade) can use either backend
    transparently.
    """

    def __init__(
        self,
        config: Settings,
        security_validator: Optional[SecurityValidator] = None,
    ) -> None:
        self.config = config
        self.security_validator = security_validator
        self._cli_path = config.claude_cli_path or "claude"

    # ------------------------------------------------------------------
    # Public API (matches ClaudeSDKManager.execute_command signature)
    # ------------------------------------------------------------------

    async def execute_command(
        self,
        prompt: str,
        working_directory: Path,
        session_id: Optional[str] = None,
        continue_session: bool = False,
        stream_callback: Optional[Callable[[StreamUpdate], None]] = None,
    ) -> ClaudeResponse:
        """Execute a Claude Code command via the CLI."""
        start_time = time.monotonic()

        logger.info(
            "Starting Claude CLI command",
            working_directory=str(working_directory),
            session_id=session_id,
            continue_session=continue_session,
        )

        args = self._build_args(
            prompt=prompt,
            working_directory=working_directory,
            session_id=session_id,
            continue_session=continue_session,
            has_stream_callback=stream_callback is not None,
        )

        env = self._build_env()

        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(working_directory),
                env=env,
                limit=1024 * 1024,  # 1MB line buffer (default 64KB too small for skill output)
            )

            events, stderr_data = await self._run_with_timeout(process, stream_callback)

            duration_ms = int((time.monotonic() - start_time) * 1000)
            return self._build_response(events, stderr_data, duration_ms, session_id)

        except asyncio.TimeoutError:
            logger.error(
                "Claude CLI timed out",
                timeout_seconds=self.config.claude_timeout_seconds,
            )
            # Kill the process on timeout
            try:
                process.kill()  # type: ignore[possibly-undefined]
                await process.wait()
            except Exception:
                pass
            raise ClaudeTimeoutError(
                f"Claude CLI timed out after {self.config.claude_timeout_seconds}s"
            )

        except FileNotFoundError:
            logger.error("Claude CLI not found", cli_path=self._cli_path)
            raise ClaudeProcessError(
                f"Claude CLI not found at '{self._cli_path}'. "
                "Install with: npm install -g @anthropic-ai/claude-code"
            )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _build_args(
        self,
        prompt: str,
        working_directory: Path,
        session_id: Optional[str],
        continue_session: bool,
        has_stream_callback: bool,
    ) -> List[str]:
        args = [
            self._cli_path,
            "-p",
            prompt,
            "--output-format",
            "stream-json",
            "--verbose",
        ]

        if has_stream_callback:
            args.append("--include-partial-messages")

        # Session resume
        if session_id and continue_session:
            args.extend(["--resume", session_id])

        # Model
        if self.config.claude_model:
            args.extend(["--model", self.config.claude_model])

        # Max turns
        args.extend(["--max-turns", str(self.config.claude_max_turns)])

        # Budget cap
        if self.config.claude_max_cost_per_request:
            args.extend(
                ["--max-budget-usd", str(self.config.claude_max_cost_per_request)]
            )

        # Permission bypass (bot has its own security layer)
        args.append("--dangerously-skip-permissions")

        # Append bot-specific instructions (don't override full system prompt;
        # --setting-sources already loads CLAUDE.md from user/project levels)
        bot_instructions = (
            f"All file operations must stay within {working_directory}. "
            "Use relative paths.\n"
            "回复风格：用中文，简洁直接，像一个靠谱的技术搭档在聊天。"
            "不要用 emoji 开头，不要说'好的'、'当然可以'之类的废话。"
            "称呼用户为'哥'。\n"
            "重要：你运行在 Telegram bot 内部。\n"
            "- 绝对不要读取 .env 文件，不要尝试调用 Telegram API。\n"
            "- 当生成了图片/文件时，在回复末尾用独立一行写绝对路径"
            "（如 /path/to/image.png），bot 会自动提取并发送。\n"
            "- 回复正文中不要展示文件路径给用户，保持干净。"
        )
        args.extend(["--append-system-prompt", bot_instructions])

        # Tool restrictions (only when tool validation is active)
        if not self.config.disable_tool_validation:
            if self.config.claude_allowed_tools:
                args.extend(["--allowed-tools", *self.config.claude_allowed_tools])
            if self.config.claude_disallowed_tools:
                args.extend(
                    ["--disallowed-tools", *self.config.claude_disallowed_tools]
                )

        # MCP config
        if self.config.enable_mcp and self.config.mcp_config_path:
            args.extend(["--mcp-config", str(self.config.mcp_config_path)])

        # Setting sources
        args.extend(["--setting-sources", "user,project"])

        return args

    def _build_env(self) -> Dict[str, str]:
        env = dict(os.environ)
        # Prevent nested-session detection
        env.pop("CLAUDECODE", None)
        if self.config.anthropic_api_key_str:
            env["ANTHROPIC_API_KEY"] = self.config.anthropic_api_key_str
        return env

    async def _run_with_timeout(
        self,
        process: asyncio.subprocess.Process,
        stream_callback: Optional[Callable[[StreamUpdate], None]],
    ) -> tuple:
        """Read stdout/stderr concurrently with a timeout wrapper."""

        events: List[Dict[str, Any]] = []
        stderr_lines: List[str] = []

        async def _read_stderr() -> None:
            assert process.stderr is not None
            async for raw in process.stderr:
                line = raw.decode("utf-8", errors="replace").rstrip()
                if line:
                    stderr_lines.append(line)
                    logger.debug("Claude CLI stderr", line=line)

        async def _read_stdout() -> None:
            assert process.stdout is not None
            async for raw in process.stdout:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    logger.debug("Skipping non-JSON line", line=line[:200])
                    continue

                events.append(event)

                if stream_callback:
                    update = self._event_to_stream_update(event)
                    if update:
                        try:
                            await stream_callback(update)
                        except Exception as e:
                            logger.warning("Stream callback error", error=str(e))

        async def _run() -> None:
            await asyncio.gather(_read_stdout(), _read_stderr())
            await process.wait()

        await asyncio.wait_for(
            _run(),
            timeout=self.config.claude_timeout_seconds,
        )

        stderr_data = "\n".join(stderr_lines[-30:])
        return events, stderr_data

    def _event_to_stream_update(self, event: Dict[str, Any]) -> Optional[StreamUpdate]:
        """Map a CLI JSONL event to a StreamUpdate."""
        etype = event.get("type")

        if etype == "assistant":
            msg = event.get("message", {})
            content_blocks = msg.get("content", [])
            text_parts: List[str] = []
            tool_calls: List[Dict[str, Any]] = []

            for block in content_blocks:
                btype = block.get("type")
                if btype == "text":
                    text_parts.append(block.get("text", ""))
                elif btype == "tool_use":
                    tool_calls.append(
                        {
                            "name": block.get("name", "unknown"),
                            "input": block.get("input", {}),
                            "id": block.get("id"),
                        }
                    )
                # Skip thinking, image, etc.

            if text_parts or tool_calls:
                return StreamUpdate(
                    type="assistant",
                    content="\n".join(text_parts) if text_parts else None,
                    tool_calls=tool_calls if tool_calls else None,
                )

        elif etype == "user":
            msg = event.get("message", {})
            content_blocks = msg.get("content", [])
            parts: List[str] = []
            for block in content_blocks:
                if block.get("type") == "tool_result":
                    text = block.get("content", "")
                    if isinstance(text, str) and text:
                        parts.append(text)
            if parts:
                return StreamUpdate(type="user", content="\n".join(parts))

        # Partial streaming tokens
        elif etype == "content_block_delta":
            delta = event.get("delta", {})
            if delta.get("type") == "text_delta":
                text = delta.get("text", "")
                if text:
                    return StreamUpdate(type="stream_delta", content=text)

        return None

    def _build_response(
        self,
        events: List[Dict[str, Any]],
        stderr_data: str,
        duration_ms: int,
        fallback_session_id: Optional[str],
    ) -> ClaudeResponse:
        """Build a ClaudeResponse from collected JSONL events."""
        result_event = next((e for e in events if e.get("type") == "result"), None)

        if result_event:
            is_error = result_event.get("is_error", False)
            sid = result_event.get("session_id", "")

            # Check for MCP errors
            if is_error and "mcp" in result_event.get("result", "").lower():
                raise ClaudeMCPError(f"MCP error: {result_event.get('result', '')}")

            return ClaudeResponse(
                content=result_event.get("result", ""),
                session_id=sid or fallback_session_id or "",
                cost=result_event.get("total_cost_usd", 0.0),
                duration_ms=result_event.get("duration_ms", duration_ms),
                num_turns=result_event.get("num_turns", 0),
                is_error=is_error,
                error_type="cli_error" if is_error else None,
                tools_used=self._extract_tools(events),
            )

        # Fallback: try session_id from init event
        init_event = next((e for e in events if e.get("type") == "system"), None)
        init_session_id = init_event.get("session_id", "") if init_event else ""

        # Fallback: extract text from assistant messages
        content_parts: List[str] = []
        for ev in events:
            if ev.get("type") == "assistant":
                for block in ev.get("message", {}).get("content", []):
                    if block.get("type") == "text":
                        content_parts.append(block.get("text", ""))

        content = "\n".join(content_parts)

        if not content and stderr_data:
            error_snippet = stderr_data[-500:]
            if "mcp" in error_snippet.lower():
                raise ClaudeMCPError(f"MCP error (stderr): {error_snippet}")
            raise ClaudeProcessError(
                f"Claude CLI produced no output. Stderr: {error_snippet}"
            )

        if not content and not events:
            raise ClaudeParsingError("Claude CLI returned no events")

        return ClaudeResponse(
            content=content,
            session_id=init_session_id or fallback_session_id or "",
            cost=0.0,
            duration_ms=duration_ms,
            num_turns=len(
                [e for e in events if e.get("type") in ("assistant", "user")]
            ),
            is_error=False,
            tools_used=self._extract_tools(events),
        )

    @staticmethod
    def _extract_tools(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        tools: List[Dict[str, Any]] = []
        now = time.time()
        for ev in events:
            if ev.get("type") != "assistant":
                continue
            for block in ev.get("message", {}).get("content", []):
                if block.get("type") == "tool_use":
                    tools.append(
                        {
                            "name": block.get("name", "unknown"),
                            "timestamp": now,
                            "input": block.get("input", {}),
                        }
                    )
        return tools
