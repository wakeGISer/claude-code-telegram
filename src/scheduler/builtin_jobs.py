"""Built-in scheduled job templates for livis personal assistant."""

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from ..config.settings import Settings
    from .scheduler import JobScheduler

logger = structlog.get_logger()

DAILY_BRIEF_PROMPT = (
    "Give me a brief daily summary. Include:\n"
    "1. Today's date and day of week\n"
    "2. List any open tasks from the tasks table (SELECT * FROM tasks WHERE status='open')\n"
    "3. A short motivational note\n"
    "Keep it concise — this is a morning brief."
)

WEEKLY_REVIEW_PROMPT = (
    "Generate a weekly review. Include:\n"
    "1. Tasks completed this week\n"
    "2. Tasks still open\n"
    "3. Key accomplishments and learnings\n"
    "4. Suggestions for next week\n"
    "Use /weekly skill if available."
)


async def register_builtin_jobs(
    scheduler: "JobScheduler",
    settings: "Settings",
) -> None:
    """Register built-in scheduled jobs based on config."""

    if settings.enable_daily_brief and settings.daily_brief_chat_id:
        try:
            await scheduler.add_job(
                job_name="Daily Brief",
                cron_expression=settings.daily_brief_cron,
                prompt=DAILY_BRIEF_PROMPT,
                target_chat_ids=[settings.daily_brief_chat_id],
                working_directory=settings.approved_directory,
            )
            logger.info(
                "Registered daily brief job",
                cron=settings.daily_brief_cron,
                chat_id=settings.daily_brief_chat_id,
            )
        except Exception as e:
            logger.warning("Failed to register daily brief", error=str(e))

    if settings.enable_weekly_review and settings.weekly_review_chat_id:
        try:
            await scheduler.add_job(
                job_name="Weekly Review",
                cron_expression=settings.weekly_review_cron,
                prompt=WEEKLY_REVIEW_PROMPT,
                target_chat_ids=[settings.weekly_review_chat_id],
                working_directory=settings.approved_directory,
            )
            logger.info(
                "Registered weekly review job",
                cron=settings.weekly_review_cron,
                chat_id=settings.weekly_review_chat_id,
            )
        except Exception as e:
            logger.warning("Failed to register weekly review", error=str(e))
