"""Run due scheduled jobs once (for a cron container that shares the database volume, or local use)."""
from django.core.management.base import BaseCommand

from apps.growth.jobs import JOBS, run_due_jobs


class Command(BaseCommand):
    help = 'Run due scheduled jobs (reply collection, follow-ups, outreach drafts, briefings, checks, backups).'

    def add_arguments(self, parser):
        parser.add_argument('--job', action='append', choices=sorted(JOBS), help='Only run these jobs')
        parser.add_argument('--force', action='store_true', help='Run even if the job already ran in this window')

    def handle(self, *args, **opts):
        for r in run_due_jobs(only=opts.get('job'), force=opts.get('force', False)):
            line = f"{r['job']}: {r['status']}"
            if r.get('reason'):
                line += f" ({r['reason']})"
            if r.get('error'):
                line += f" - {r['error']}"
            self.stdout.write(line)
