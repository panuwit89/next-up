from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from finance.brief import run_weekly_company_brief
from finance.config import get_settings


def create_scheduler() -> BackgroundScheduler:
    settings = get_settings()
    scheduler = BackgroundScheduler(timezone=settings.TIMEZONE)
    scheduler.add_job(
        run_weekly_company_brief,
        CronTrigger(
            day_of_week=settings.SCHEDULE_DAY_OF_WEEK,
            hour=settings.SCHEDULE_HOUR,
            minute=settings.SCHEDULE_MINUTE,
            timezone=settings.TIMEZONE,
        ),
        id="weekly_company_brief",
        max_instances=1,
        replace_existing=True,
    )
    return scheduler
