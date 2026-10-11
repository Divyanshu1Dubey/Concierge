"""Overnight QA: scheduler jobs, failure isolation, alert retries, backups/restore drills and diagnostics."""
import os
import sqlite3
import tempfile
from datetime import timedelta
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core import mail
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.appointments.models import Appointment
from apps.core import backups
from apps.growth import followups, jobs
from apps.growth.models import FollowUpTask, GrowthSettings, JobRun, VisibilityReport
from apps.practices.models import Practice
from apps.users.models import User


def client_for(user):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(user).access_token}')
    return c


def overdue(practice, hours=8, **kw):
    a = Appointment.objects.create(practice=practice, patient_name=kw.pop('name', 'Pat Overdue'),
                                   patient_email=kw.pop('email', 'pat@x.test'), **kw)
    Appointment.objects.filter(id=a.id).update(created_at=timezone.now() - timedelta(hours=hours))
    return a


@override_settings(EMAIL_CONFIGURED=True, IMAP_HOST='')
class JobTests(TestCase):
    def setUp(self):
        cache.clear()
        self.p1 = Practice.objects.create(name='One', slug='one', email='one@x.test', website='https://one.test')
        self.p2 = Practice.objects.create(name='Two', slug='two', email='two@x.test', website='https://two.test')
        self.off = Practice.objects.create(name='Suspended', slug='off', email='off@x.test', active=False)

    def test_replies_job_reports_unconfigured_mailbox(self):
        r = jobs.run_job('replies')
        self.assertEqual((r['status'], r['result']), ('ok', {'configured': False}))

    def test_followups_job_covers_each_active_practice_and_skips_suspended(self):
        overdue(self.p1); overdue(self.p2, email='b@x.test'); overdue(self.off, email='c@x.test')
        r = jobs.run_job('followups')
        self.assertEqual(r['result']['practices'], 2)
        self.assertEqual(FollowUpTask.objects.filter(practice=self.off).count(), 0)
        self.assertEqual(FollowUpTask.objects.count(), 2)

    def test_one_practice_failing_does_not_stop_the_others(self):
        overdue(self.p2)
        real = followups.scan_practice

        def flaky(practice, now=None):
            if practice.id == self.p1.id:
                raise RuntimeError('boom')
            return real(practice, now)
        with mock.patch('apps.growth.followups.scan_practice', side_effect=flaky):
            r = jobs.run_job('followups')
        self.assertEqual((r['status'], r['result']['errors'], r['result']['practices']), ('ok', 1, 1))
        self.assertEqual(FollowUpTask.objects.filter(practice=self.p2).count(), 1)

    def test_job_crash_is_recorded_and_next_window_retries(self):
        now = timezone.now()
        with mock.patch.dict(jobs.JOBS, {'cleanup': (mock.Mock(side_effect=ValueError('disk')), 1440)}):
            r = jobs.run_job('cleanup', now=now)
        self.assertEqual(r['status'], 'failed')
        self.assertIn('ValueError', JobRun.objects.get(job='cleanup').error)
        self.assertEqual(jobs.run_job('cleanup', now=now + timedelta(days=1))['status'], 'ok')

    def test_same_window_runs_once_even_if_called_repeatedly(self):
        now = timezone.now().replace(minute=7)
        results = [jobs.run_job('followups', now=now + timedelta(minutes=i))['status'] for i in range(5)]
        self.assertEqual(results.count('ok'), 1)  # 07..11 fall in the same 15-minute window
        self.assertEqual(JobRun.objects.filter(job='followups').count(), 1)

    def test_forced_run_bypasses_window_but_is_recorded(self):
        jobs.run_job('cleanup')
        self.assertEqual(jobs.run_job('cleanup', force=True)['status'], 'ok')
        self.assertEqual(JobRun.objects.filter(job='cleanup').count(), 2)

    def test_visibility_job_checks_stale_sites_only_and_caps_per_run(self):
        VisibilityReport.objects.create(practice=self.p1, url='https://one.test', score=70)
        with mock.patch('apps.growth.visibility.run_check') as rc:
            r = jobs.run_job('visibility')
        self.assertEqual(r['result'], {'checked': 1})
        rc.assert_called_once()
        self.assertEqual(rc.call_args.args[0], self.p2)

    def test_cleanup_removes_only_old_job_rows(self):
        old = JobRun.objects.create(job='x', run_key='old', started_at=timezone.now() - timedelta(days=40))
        JobRun.objects.create(job='x', run_key='new')
        jobs.run_job('cleanup')
        self.assertFalse(JobRun.objects.filter(id=old.id).exists())
        self.assertTrue(JobRun.objects.filter(run_key='new').exists())

    def test_backup_job_fails_cleanly_without_a_database_file(self):
        r = jobs.run_job('backup')  # tests use an in-memory database
        self.assertEqual(r['status'], 'failed')

    def test_management_command_prints_each_job(self):
        out = StringIO()
        call_command('run_scheduled_jobs', job=['cleanup'], stdout=out)
        self.assertIn('cleanup: ok', out.getvalue())
        out = StringIO()
        call_command('run_scheduled_jobs', job=['cleanup'], stdout=out)
        self.assertIn('cleanup: skipped', out.getvalue())

    def test_scheduler_status(self):
        self.assertFalse(jobs.scheduler_status()['healthy'])
        jobs.run_job('cleanup')
        st = jobs.scheduler_status()
        self.assertTrue(st['healthy'])
        self.assertEqual(st['jobs']['cleanup']['status'], 'ok')


@override_settings(EMAIL_CONFIGURED=True)
class AlertTests(TestCase):
    def setUp(self):
        cache.clear()
        self.p = Practice.objects.create(name='Alpha', slug='alpha', email='desk@alpha.test')

    def test_alert_retried_after_mail_failure_then_sent_once(self):
        overdue(self.p)
        with mock.patch('apps.growth.followups.send_mail', side_effect=OSError('smtp down')):
            followups.scan_practice(self.p)
        self.assertIsNone(FollowUpTask.objects.get().alert_sent_at)
        followups.scan_practice(self.p)
        followups.scan_practice(self.p)
        self.assertEqual(len([m for m in mail.outbox if 'follow-up' in m.subject]), 1)
        self.assertIsNotNone(FollowUpTask.objects.get().alert_sent_at)

    def test_threshold_boundary(self):
        GrowthSettings.for_practice(self.p)
        GrowthSettings.objects.filter(practice=self.p).update(waiting_alert_hours=4)
        overdue(self.p, hours=3.9, email='early@x.test')
        overdue(self.p, hours=4.1, email='late@x.test')
        followups.scan_practice(self.p)
        self.assertEqual(list(FollowUpTask.objects.values_list('patient_email', flat=True)), ['late@x.test'])

    def test_alerts_disabled_means_no_tasks_and_no_email(self):
        GrowthSettings.for_practice(self.p)
        GrowthSettings.objects.filter(practice=self.p).update(waiting_alerts_enabled=False)
        overdue(self.p)
        followups.scan_practice(self.p)
        self.assertEqual(FollowUpTask.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_deleted_request_removes_its_task(self):
        a = overdue(self.p)
        followups.scan_practice(self.p)
        a.delete()
        self.assertEqual(FollowUpTask.objects.count(), 0)

    def test_spam_and_closed_requests_are_never_chased(self):
        overdue(self.p, status='spam', email='s@x.test')
        overdue(self.p, status='cancelled', email='c@x.test')
        followups.scan_practice(self.p)
        self.assertEqual(FollowUpTask.objects.count(), 0)

    def test_no_recipient_means_no_alert_and_no_crash(self):
        self.p.email = ''
        self.p.save()
        overdue(self.p)
        self.assertEqual(followups.scan_practice(self.p)['alerted'], 0)


class BackupTests(TestCase):
    def _db(self, path, tables=backups.CORE_TABLES):
        c = sqlite3.connect(path)
        for t in tables:
            c.execute(f'CREATE TABLE "{t}" (id INTEGER PRIMARY KEY)')
        c.execute('INSERT INTO django_migrations VALUES (1)') if 'django_migrations' in tables else None
        c.commit(); c.close()

    def test_verify_good_missing_tables_corrupt_and_absent(self):
        d = tempfile.mkdtemp()
        good, partial, corrupt = (os.path.join(d, n) for n in ('good.sqlite3', 'partial.sqlite3', 'corrupt.sqlite3'))
        self._db(good)
        self._db(partial, tables=('users_user',))
        Path(corrupt).write_bytes(b'this is not a database' * 100)
        g = backups.verify_backup(good)
        self.assertTrue(g['ok'])
        self.assertEqual(g['migrations'], 1)
        self.assertFalse(backups.verify_backup(partial)['ok'])
        self.assertIn('Missing core tables', backups.verify_backup(partial)['error'])
        self.assertFalse(backups.verify_backup(corrupt)['ok'])
        self.assertFalse(backups.verify_backup(os.path.join(d, 'nope.sqlite3'))['ok'])

    def test_restore_drill_uses_a_temporary_copy_and_never_the_live_file(self):
        d = tempfile.mkdtemp()
        src = os.path.join(d, 'heyjarvis-1.sqlite3')
        self._db(src)
        before = Path(src).read_bytes()
        with override_settings(BACKUP_DIR=d):
            r = backups.restore_drill(migrate=False)
        self.assertTrue(r['ok'], r)
        self.assertEqual([s['step'] for s in r['steps']], ['verify', 'restore_to_temp', 'verify_restored'])
        self.assertEqual(Path(src).read_bytes(), before)  # source untouched

    def test_restore_drill_reports_bad_backup(self):
        d = tempfile.mkdtemp()
        Path(d, 'heyjarvis-1.sqlite3').write_bytes(b'garbage')
        with override_settings(BACKUP_DIR=d):
            r = backups.restore_drill(migrate=False)
        self.assertFalse(r['ok'])
        with override_settings(BACKUP_DIR=tempfile.mkdtemp()):
            self.assertEqual(backups.restore_drill()['error'], 'No backups found.')

    def test_backup_command_on_a_file_database(self):
        d = tempfile.mkdtemp()
        live = os.path.join(d, 'live.sqlite3')
        self._db(live)
        out_dir = os.path.join(d, 'backups')
        db = {'ENGINE': 'django.db.backends.sqlite3', 'NAME': live}
        with mock.patch.dict('django.conf.settings.DATABASES', {'default': db}):
            for _ in range(3):
                call_command('backup_db', dir=out_dir, keep=2, stdout=StringIO())
        files = sorted(Path(out_dir).glob('live-*.sqlite3'))
        self.assertEqual(len(files), 2)  # retention
        self.assertTrue(all(backups.verify_backup(f)['ok'] for f in files))


class DiagnosticsTests(TestCase):
    def setUp(self):
        self.agency = User.objects.create_user(username='ag@x.test', email='ag@x.test', password='Str0ng-Test-Passphrase-91',
                                               role='AGENCY_ADMIN')
        self.p = Practice.objects.create(name='Alpha', slug='alpha', email='a@x.test')
        self.admin = User.objects.create_user(username='ad@x.test', email='ad@x.test', password='Str0ng-Test-Passphrase-91',
                                              role='PRACTICE_ADMIN', practice=self.p)

    def test_only_agency_admins(self):
        self.assertEqual(client_for(self.admin).get('/api/v1/growth/system-status/').status_code, 403)
        self.assertEqual(APIClient().get('/api/v1/growth/system-status/').status_code, 401)
        self.assertEqual(client_for(self.admin).post('/api/v1/growth/system-status/', {'action': 'restore_drill'}, format='json').status_code, 403)

    @override_settings(CRON_SECRET='very-secret-cron-value-123', SECRET_KEY='k' * 60, DEBUG=False)
    def test_report_flags_blockers_without_leaking_values(self):
        r = client_for(self.agency).get('/api/v1/growth/system-status/')
        self.assertEqual(r.status_code, 200)
        body = r.content.decode()
        self.assertNotIn('very-secret-cron-value-123', body)
        self.assertNotIn('k' * 60, body)
        checks = {c['key']: c for s in r.json()['sections'] for c in s['checks']}
        self.assertEqual(checks['cron_secret']['status'], 'ok')
        self.assertEqual(checks['secret_key']['status'], 'ok')
        self.assertEqual(checks['scheduler']['status'], 'fail')  # never ran
        self.assertIn(self.p.name, [x['name'] for x in r.json()['practices']])

    @override_settings(SECRET_KEY='django-insecure-short', DEBUG=True, CRON_SECRET='')
    def test_weak_configuration_is_reported(self):
        checks = {c['key']: c for s in client_for(self.agency).get('/api/v1/growth/system-status/').json()['sections'] for c in s['checks']}
        for key in ('secret_key', 'debug', 'cron_secret'):
            self.assertEqual(checks[key]['status'], 'fail', key)
            self.assertTrue(checks[key]['fix'])

    def test_exposed_demo_account_flagged(self):
        User.objects.create_user(username='doctor@heyjarvis-demo.com', email='doctor@heyjarvis-demo.com',
                                 password='Str0ng-Test-Passphrase-91', role='PRACTICE_ADMIN', practice=self.p)
        checks = {c['key']: c for s in client_for(self.agency).get('/api/v1/growth/system-status/').json()['sections'] for c in s['checks']}
        self.assertEqual(checks['exposed_accounts']['status'], 'fail')

    @override_settings(GROWTH_SYNC_BACKGROUND=True)
    def test_restore_drill_action_runs_and_reports(self):
        cache.clear()
        d = tempfile.mkdtemp()
        with override_settings(BACKUP_DIR=d):
            r = client_for(self.agency).post('/api/v1/growth/system-status/', {'action': 'restore_drill'}, format='json')
            self.assertEqual(r.status_code, 202)
            res = client_for(self.agency).get('/api/v1/growth/system-status/').json()['restore_drill']
        self.assertEqual(res['status'], 'failed')
        self.assertIn('No backups', res.get('error', ''))
