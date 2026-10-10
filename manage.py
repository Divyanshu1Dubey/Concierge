#!/usr/bin/env python
"""Root manage.py wrapper that delegates to backend/manage.py seamlessly."""
import os
import sys

def main():
    repo_root = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.join(repo_root, 'backend')
    if os.path.isdir(backend_dir):
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)
        os.chdir(backend_dir)
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
