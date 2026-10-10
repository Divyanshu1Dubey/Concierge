from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.core'
    verbose_name = 'Core'

    def ready(self):
        from django.db.backends.signals import connection_created
        connection_created.connect(configure_sqlite, dispatch_uid='core.configure_sqlite')


def configure_sqlite(sender, connection, **kwargs):
    """WAL lets readers proceed during writes; busy_timeout makes writers wait rather than fail."""
    if connection.vendor != 'sqlite':
        return
    with connection.cursor() as cursor:
        cursor.execute('PRAGMA busy_timeout=20000;')  # first, so the statements below wait for locks
        cursor.execute('PRAGMA journal_mode;')
        mode = (cursor.fetchone() or [''])[0]
        if str(mode).lower() not in ('wal', 'memory'):
            try:
                # Persistent per database file; only needs to succeed once.
                cursor.execute('PRAGMA journal_mode=WAL;')
            except Exception:
                pass  # another process holds a lock; a later connection will switch it
        cursor.execute('PRAGMA synchronous=NORMAL;')
