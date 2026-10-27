import hashlib
import sqlite3
import tempfile
from pathlib import Path
from io import StringIO
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, Client, override_settings
from django.utils import timezone
from apps.core.models import Review, ContactRequest, SubmissionWindow

@override_settings(SECURE_SSL_REDIRECT=False, SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False)
class ApplicationTests(TestCase):
    review = {'name':'عميل تجريبي', 'rating':5, 'review':'تجربة قانونية واضحة ومهنية للغاية.'}
    contact = {'name':'طالب استشارة', 'phone':'+966500000000', 'email':'CLIENT@example.com', 'service':'الاستشارات القانونية', 'message':'أرغب في حجز استشارة ومناقشة الموضوع.'}
    def test_home_branding_sections_and_routes(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'محاماة')
        self.assertNotContains(response, 'الهذيلي')
        self.assertNotContains(response, 'ALHUDHAYLI')
        self.assertNotContains(response, '@if')
        self.assertEqual(self.client.get('/up').status_code, 200)
        for url in ['/reviews','/contact-requests']:
            self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.get('/missing').status_code, 404)
    def test_review_pending_and_success(self):
        self.assertRedirects(self.client.post('/reviews', self.review), '/#testimonials')
        self.assertEqual(Review.objects.get().status, 'pending')
        self.assertNotContains(self.client.get('/'), self.review['review'])
    def test_contact_new_and_sanitized(self):
        data = {**self.contact, 'name':' <b>طالب استشارة</b> '}
        self.assertRedirects(self.client.post('/contact-requests', data), '/#contact')
        item = ContactRequest.objects.get()
        self.assertEqual(item.status, 'new')
        self.assertEqual(item.name, 'طالب استشارة')
        self.assertEqual(item.email, 'client@example.com')
    def test_approved_latest_eight_only(self):
        for i in range(10):
            Review.objects.create(name=f'APPROVED-{i}', rating=5, review='approved text', status='approved', created_at=timezone.now())
        Review.objects.create(name='PRIVATE-PENDING', rating=5, review='secret')
        response = self.client.get('/')
        self.assertContains(response, 'APPROVED-9')
        self.assertNotContains(response, 'APPROVED-0')
        self.assertNotContains(response, 'PRIVATE-PENDING')
    def test_validation_and_form_isolation(self):
        data = {**self.review, 'rating':6, 'name':'<script>x</script>'}
        response = self.client.post('/reviews', data)
        self.assertFalse(Review.objects.exists())
        self.assertTrue(response.context['review_form'].errors)
        self.assertFalse(response.context['contact_form'].is_bound)
        self.assertNotContains(response, '<script>x</script>')
        for field, value in [('phone','abc'), ('email','invalid'), ('message','short'), ('name','x'), ('company_website','spam')]:
            SubmissionWindow.objects.all().delete()
            response = self.client.post('/contact-requests', {**self.contact, field:value})
            self.assertTrue(response.context['contact_form'].errors)
        self.assertFalse(ContactRequest.objects.exists())
    def test_honeypot(self):
        self.client.post('/reviews', {**self.review,'company_website':'bot.example'})
        self.assertFalse(Review.objects.exists())
    def test_csrf(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post('/reviews', self.review).status_code, 403)
        client.get('/')
        self.assertEqual(client.post('/reviews', self.review, HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value).status_code, 302)
    def test_rate_limits_and_expiration(self):
        for url, data, limit in [('/reviews',self.review,3),('/contact-requests',self.contact,4)]:
            for _ in range(limit):
                self.assertEqual(self.client.post(url,data).status_code,302)
            response = self.client.post(url,data)
            self.assertEqual(response.status_code,429)
            self.assertTrue(response.has_header('Retry-After'))
            self.assertEqual(self.client.post(url,data,REMOTE_ADDR='127.0.0.2').status_code,302)
        SubmissionWindow.objects.update(started_at=timezone.now()-timezone.timedelta(seconds=61))
        self.assertEqual(self.client.post('/reviews',self.review).status_code,302)
    def test_admin_permissions(self):
        self.assertEqual(self.client.get('/admin/core/contactrequest/').status_code,302)
        user = get_user_model().objects.create_user(username='ordinary',email='ordinary@example.com',password='test-password')
        self.client.force_login(user)
        self.assertEqual(self.client.get('/admin/core/contactrequest/').status_code,302)
        user.is_staff = True
        user.save()
        self.assertEqual(self.client.get('/admin/core/contactrequest/').status_code,403)
        user.is_superuser = True
        user.save()
        self.assertEqual(self.client.get('/admin/core/contactrequest/').status_code,200)
    def test_import_readonly_verified_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)/'source.sqlite'
            db = sqlite3.connect(source)
            db.executescript('''CREATE TABLE reviews(id INTEGER PRIMARY KEY,name TEXT,rating INTEGER,review TEXT,status TEXT,created_at TEXT,updated_at TEXT);
            CREATE TABLE contact_requests(id INTEGER PRIMARY KEY,name TEXT,phone TEXT,email TEXT,service TEXT,message TEXT,status TEXT,created_at TEXT,updated_at TEXT);
            CREATE TABLE users(id INTEGER PRIMARY KEY,name TEXT,email TEXT,email_verified_at TEXT,created_at TEXT,updated_at TEXT,password TEXT);
            INSERT INTO reviews VALUES(7,'historic',5,'original review','approved','2026-01-01 00:00:00',NULL);
            INSERT INTO users VALUES(4,'historic user','history@example.com',NULL,NULL,NULL,'laravel-hash');''')
            db.close()
            original = hashlib.sha256(source.read_bytes()).digest()
            call_command('import_laravel',source,dry_run=True,stdout=StringIO())
            self.assertFalse(Review.objects.exists())
            call_command('import_laravel',source,stdout=StringIO())
            self.assertEqual(Review.objects.get().pk,7)
            user = get_user_model().objects.get()
            self.assertFalse(user.has_usable_password())
            self.assertFalse(user.is_staff)
            self.assertEqual(original,hashlib.sha256(source.read_bytes()).digest())
            with self.assertRaises(CommandError):
                call_command('import_laravel',source,stdout=StringIO())
