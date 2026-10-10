#!/usr/bin/env python
"""Fallback manage.py forwarder in case backend/manage.py is invoked from inside backend/."""
import os
import sys

def main():
    parent_backend = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if parent_backend not in sys.path:
        sys.path.insert(0, parent_backend)
    os.chdir(parent_backend)
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable?"
        ) from exc
    execute_from_command_line(sys.argv)

if __name__ == '__main__':
    main()
