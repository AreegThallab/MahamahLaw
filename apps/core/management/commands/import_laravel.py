import sqlite3
from pathlib import Path
from datetime import timezone as dt_timezone
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction, connection
from django.core.management.color import no_style
from django.utils.dateparse import parse_datetime
from apps.core.models import ContactRequest, Review

def timestamp(value):
    if not value:
        return None
    parsed = parse_datetime(value)
    if parsed is None:
        raise CommandError('Unrecognized source timestamp; import cancelled.')
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt_timezone.utc)

class Command(BaseCommand):
    help = 'Import business records from a read-only Laravel SQLite source into empty Django tables.'
    def add_arguments(self, parser):
        parser.add_argument('source', type=Path)
        parser.add_argument('--dry-run', action='store_true')
    def handle(self, source, **options):
        if source.resolve() == Path(connection.settings_dict['NAME']).resolve():
            raise CommandError('Source and destination must differ.')
        user_model = get_user_model()
        mapping = [('reviews', Review), ('contact_requests', ContactRequest), ('users', user_model)]
        src = None
        try:
            src = sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True)
            src.row_factory = sqlite3.Row
            with src, transaction.atomic():
                for table, model in mapping:
                    if model.objects.exists():
                        raise CommandError('Destination business/user tables must be empty. Use a fresh database.')
                src.execute('BEGIN')
                for table, model in mapping:
                    rows = src.execute(f'SELECT * FROM {table} ORDER BY id').fetchall()
                    expected = []
                    source_fields = {column[1] for column in src.execute(f'PRAGMA table_info({table})')}
                    fields = ['id','name','email','email_verified_at','created_at','updated_at'] if table == 'users' else [f.name for f in model._meta.fields if f.name in source_fields]
                    for row in rows:
                        data = {field: timestamp(row[field]) if field.endswith('_at') else row[field] for field in fields}
                        instance = model(**data)
                        if table == 'users':
                            instance.username = f'laravel-{row["id"]}'
                            instance.set_unusable_password()
                        instance.save(force_insert=True)
                        expected.append(data)
                    actual = list(model.objects.order_by('id').values(*fields))
                    if actual != expected:
                        raise CommandError('Record verification failed; transaction rolled back.')
                    self.stdout.write(f'{table}: source={len(rows)}, destination={len(actual)}, all field values verified')
                if src.execute('PRAGMA foreign_key_check').fetchall():
                    raise CommandError('Source foreign key violations; transaction rolled back.')
                for sql in connection.ops.sequence_reset_sql(no_style(), [m for _,m in mapping]):
                    connection.cursor().execute(sql)
                if options['dry_run']:
                    transaction.set_rollback(True)
            src.close()
        except sqlite3.Error as exc:
            raise CommandError('Source SQLite could not be read; no records imported.') from exc
        finally:
            if src is not None:
                src.close()
        self.stdout.write('Dry run rolled back.' if options['dry_run'] else 'Import complete. Original database unchanged.')
