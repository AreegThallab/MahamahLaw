from datetime import timedelta
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from apps.core.content import CONTENT
from apps.core.models import ContactRequest, Review

NAMES = ['أحمد السبيعي','سارة القحطاني','عبدالله العتيبي','نورة الدوسري','فهد السالم','ريم الحربي','خالد الزهراني','هند الغامدي']
COMMENTS = ['نموذج تجريبي: شرح واضح للخيارات القانونية وخطوات المتابعة.',
            'نموذج تجريبي: مراجعة دقيقة للعقد وتوضيح بنوده والتزاماته.',
            'نموذج تجريبي: تواصل منظم وإجابة مفصلة عن الاستفسارات.']

class Command(BaseCommand):
    help = 'Create idempotent, clearly marked fictional development records (24 consultations, 12 contacts, 18 reviews).'
    def handle(self, **options):
        if not settings.DEBUG:
            raise CommandError('Demo seeding is only allowed when DJANGO_DEBUG=True. Nothing was changed.')
        added = 0
        now = timezone.now()
        with transaction.atomic():
            for kind, count in [('consultation',24),('contact',12)]:
                for i in range(count):
                    key = f'mahamah-demo-v1-{kind}-{i:02d}'
                    existing = ContactRequest.objects.filter(demo_key=key).first()
                    if existing:
                        if not existing.is_demo:
                            raise CommandError('A non-demo record owns a demo key; nothing was changed.')
                        continue
                    record = ContactRequest(demo_key=key,is_demo=True,request_type=kind,
                        name=NAMES[i%len(NAMES)],phone=f'+96600000{i+1000:04d}',email=f'demo.{kind}{i+1}@example.com',
                        service=CONTENT['services'][i%len(CONTENT['services'])]['title'],
                        message='طلب تجريبي خيالي لتجربة لوحة الإدارة ومتابعة الإجراءات. لا يمثل عميلًا أو قضية حقيقية.',
                        status=ContactRequest.Status.values[i%4],internal_notes='سجل تجريبي للتطوير فقط.',
                        created_at=now-timedelta(days=i%21,hours=i%12),updated_at=now)
                    record.full_clean()
                    record.save()
                    added += 1
            for i in range(18):
                key = f'mahamah-demo-v1-review-{i:02d}'
                existing = Review.objects.filter(demo_key=key).first()
                if existing:
                    if not existing.is_demo:
                        raise CommandError('A non-demo record owns a demo key; nothing was changed.')
                    continue
                record = Review(demo_key=key,is_demo=True,name=NAMES[i%len(NAMES)],rating=3+i%3,
                                review=COMMENTS[i%len(COMMENTS)],status=['approved','pending','rejected'][i%3],
                                created_at=now-timedelta(days=i,hours=i%8),updated_at=now)
                record.full_clean()
                record.save()
                added += 1
        self.stdout.write(f'Created {added} demo records. Existing and genuine records were not modified.')
