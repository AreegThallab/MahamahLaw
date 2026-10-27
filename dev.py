"""Local-only launcher. Creates a new ignored secret once without printing it."""
import os
import secrets
import sys
from pathlib import Path

if __name__ == '__main__':
    root = Path(__file__).resolve().parent
    os.chdir(root)
    secret_file = root / '.local-secret'
    if not secret_file.exists():
        secret_file.write_text(secrets.token_urlsafe(64), encoding='ascii')
    os.environ.setdefault('DJANGO_SECRET_KEY', secret_file.read_text(encoding='ascii').strip())
    os.environ.setdefault('DJANGO_DEBUG', 'True')
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    from django.core.management import execute_from_command_line
    execute_from_command_line(['manage.py', *(sys.argv[1:] or ['runserver'])])
