from django.core.management.base import BaseCommand
from django.db import transaction
from apps.core.models import ContactRequest, Review

class Command(BaseCommand):
    help = 'Remove only explicitly flagged demo requests/reviews, preserving every genuine submission.'
    def handle(self, **options):
        with transaction.atomic():
            contacts = ContactRequest.objects.filter(is_demo=True,demo_key__startswith='mahamah-demo-v1-').delete()[0]
            reviews = Review.objects.filter(is_demo=True,demo_key__startswith='mahamah-demo-v1-').delete()[0]
        self.stdout.write(f'Removed {contacts} demo requests and {reviews} demo reviews. Genuine records preserved.')
