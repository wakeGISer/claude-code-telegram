"""Knowledge base store — capture notes and search Obsidian vault."""

import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import structlog

logger = structlog.get_logger()


class SearchResult:
    """A single search hit."""

    def __init__(self, path: Path, matches: List[str]) -> None:
        self.path = path
        self.title = path.stem
        self.matches = matches

    def summary(self, max_lines: int = 3) -> str:
        """Format as a compact summary."""
        lines = self.matches[:max_lines]
        preview = "\n".join(f"  {line.strip()}" for line in lines)
        return f"📄 {self.title}\n{preview}"


class KnowledgeStore:
    """Read/write Obsidian vault markdown files."""

    def __init__(self, vault_path: Path) -> None:
        self.vault_path = vault_path
        self.inbox_path = vault_path / "inbox"

    def capture(
        self,
        content: str,
        title: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> Path:
        """Write a note to the inbox directory.

        Returns the path of the created file.
        """
        self.inbox_path.mkdir(parents=True, exist_ok=True)

        if not title:
            first_line = content.split("\n", 1)[0].strip()
            title = first_line[:60] if first_line else "untitled"

        slug = _slugify(title)
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        filename = f"{date_str}-{slug}.md"
        file_path = self.inbox_path / filename

        tag_list = tags or ["telegram", "inbox"]
        now_iso = datetime.now(timezone.utc).isoformat()

        frontmatter = (
            f"---\n"
            f"title: {title}\n"
            f"tags: {tag_list}\n"
            f"created: {now_iso}\n"
            f"source: livis\n"
            f"---\n\n"
        )

        file_path.write_text(frontmatter + content, encoding="utf-8")
        logger.info("Note captured", path=str(file_path), title=title)
        return file_path

    def search(self, query: str, max_results: int = 10) -> List[SearchResult]:
        """Search vault for files containing the query string."""
        if not self.vault_path.exists():
            return []

        results: List[SearchResult] = []
        query_lower = query.lower()

        for md_file in self.vault_path.rglob("*.md"):
            # Skip hidden dirs and node_modules
            parts = md_file.parts
            if any(p.startswith(".") or p == "node_modules" for p in parts):
                continue

            try:
                text = md_file.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            if query_lower not in text.lower():
                continue

            # Collect matching lines
            matching_lines = [
                line
                for line in text.splitlines()
                if query_lower in line.lower() and not line.startswith("---")
            ]

            results.append(SearchResult(md_file, matching_lines))
            if len(results) >= max_results:
                break

        return results


def _slugify(text: str, max_length: int = 40) -> str:
    """Convert text to a filesystem-safe slug."""
    text = unicodedata.normalize("NFKD", text)
    text = re.sub(r"[^\w\s-]", "", text.lower())
    text = re.sub(r"[\s_]+", "-", text).strip("-")
    return text[:max_length]
