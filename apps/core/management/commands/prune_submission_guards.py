from datetime import timedelta
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from apps.core.models import SubmissionReceipt, SubmissionWindow

class Command(BaseCommand):
    help = 'Remove expired anti-duplicate receipts and old throttle windows without touching business records.'
    def handle(self, **options):
        now = timezone.now()
        with transaction.atomic():
            receipts = SubmissionReceipt.objects.filter(expires_at__lt=now).delete()[0]
            windows = SubmissionWindow.objects.filter(started_at__lt=now-timedelta(days=1)).delete()[0]
        self.stdout.write(f'Removed {receipts} expired receipts and {windows} old throttle windows.')
