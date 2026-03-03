"""
Simple Job Scheduler - Example Usage
=====================================

Demonstrates all four scheduling strategies:
  1. Interval-based  - run every N seconds/minutes/hours
  2. Cron expression - run according to a cron schedule
  3. One-time        - run exactly once at a specific datetime
  4. Dependencies    - job B runs only after job A completes
"""

import logging
import time
from datetime import datetime, timedelta

# Configure logging so scheduler activity is visible
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

from scheduler import (
    Job,
    Scheduler,
)
from scheduler.schedules import CronSchedule, IntervalSchedule, OneTimeSchedule


# ---------------------------------------------------------------------------
# Define job functions
# ---------------------------------------------------------------------------

def health_check():
    print(f"  [health_check]  {datetime.now():%H:%M:%S} - System is healthy")


def cleanup_temp_files():
    print(f"  [cleanup]       {datetime.now():%H:%M:%S} - Cleaned temp files")


def extract_data():
    print(f"  [ETL extract]   {datetime.now():%H:%M:%S} - Extracting data...")
    time.sleep(0.1)  # simulate work


def transform_data():
    print(f"  [ETL transform] {datetime.now():%H:%M:%S} - Transforming data...")


def load_data():
    print(f"  [ETL load]      {datetime.now():%H:%M:%S} - Loading data to warehouse")


def send_notification():
    print(f"  [notify]        {datetime.now():%H:%M:%S} - ETL pipeline complete!")


def one_time_migration():
    print(f"  [migration]     {datetime.now():%H:%M:%S} - One-time DB migration done!")


# ---------------------------------------------------------------------------
# Build the scheduler
# ---------------------------------------------------------------------------

scheduler = Scheduler(max_workers=4, tick_interval=0.1)

# 1. Interval-based: health check every 2 seconds
scheduler.add_job(Job(
    "health_check",
    health_check,
    IntervalSchedule(seconds=2),
))

# 2. Cron expression: cleanup at the start of every minute
#    (using */1 for demo; normally you'd use something like "0 3 * * *")
scheduler.add_job(Job(
    "cleanup",
    cleanup_temp_files,
    CronSchedule("*/1 * * * *"),
))

# 3. One-time: DB migration runs once, 1 second from now
migration_time = datetime.now() + timedelta(seconds=1)
scheduler.add_job(Job(
    "db_migration",
    one_time_migration,
    OneTimeSchedule(migration_time),
))

# 4. Dependency chain: ETL pipeline where each step waits for the previous
#    extract -> transform -> load -> notify
scheduler.add_job(Job(
    "etl_extract",
    extract_data,
    OneTimeSchedule(datetime.now() + timedelta(seconds=0.5)),
))
scheduler.add_job(Job(
    "etl_transform",
    transform_data,
    # Will fire 2s after the extract completes (or immediately if already done)
    IntervalSchedule(seconds=2),
    dependencies=["etl_extract"],
))
scheduler.add_job(Job(
    "etl_load",
    load_data,
    IntervalSchedule(seconds=2),
    dependencies=["etl_transform"],
))
scheduler.add_job(Job(
    "etl_notify",
    send_notification,
    IntervalSchedule(seconds=2),
    dependencies=["etl_load"],
))

# ---------------------------------------------------------------------------
# Run for 6 seconds then print a status summary
# ---------------------------------------------------------------------------

print("\n=== Starting scheduler (runs for 6 seconds) ===\n")
scheduler.start()

try:
    time.sleep(6)
finally:
    scheduler.stop()

print("\n=== Job Summary ===")
for job in scheduler.list_jobs():
    print(
        f"  {job.name:<20} status={job.status.value:<10} "
        f"runs={len(job.history)}  next_run={job.next_run}"
    )
