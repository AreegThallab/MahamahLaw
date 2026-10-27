from datetime import timedelta
import re
from io import StringIO
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.admin.models import LogEntry
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from apps.core.models import ContactRequest, Review, SubmissionWindow, SubmissionReceipt

@override_settings(SECURE_SSL_REDIRECT=False, SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False)
class DashboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager = get_user_model().objects.create_superuser(username='test-manager', email='test-manager@example.com', password=None)
        cls.reader = get_user_model().objects.create_user(username='test-reader',email='test-reader@example.com',is_staff=True)
        cls.reader.user_permissions.add(*Permission.objects.filter(codename__in=['view_review','view_contactrequest'],content_type__app_label='core'))
        cls.ordinary = get_user_model().objects.create_user(username='test-customer',email='test-customer@example.com')
    def setUp(self):
        self.client.force_login(self.manager)
    def request_record(self, **data):
        defaults = {'name':'طلب خاص','phone':'+966000000001','email':'client@example.com','service':'مراجعة العقود',
                    'message':'تفاصيل طلب خاص لا تظهر للعامة.', 'created_at':timezone.now(), 'updated_at':timezone.now()}
        return ContactRequest.objects.create(**{**defaults,**data})
    def review_record(self,**data):
        return Review.objects.create(**{'name':'صاحب تقييم', 'rating':5, 'review':'نص تقييم لا ينشر قبل الاعتماد.', 'created_at':timezone.now(),**data})
    def test_dashboard_authentication_all_routes_and_api(self):
        urls=['/dashboard/','/dashboard/consultations/','/dashboard/contacts/','/dashboard/reviews/',
              '/dashboard/reports/','/dashboard/users/','/dashboard/settings/','/dashboard/live/']
        self.client.logout()
        for url in urls:
            with self.subTest(url=url):
                response=self.client.get(url)
                self.assertEqual(response.status_code,302)
                self.assertIn('/dashboard/login/',response.url)
        self.client.force_login(self.ordinary)
        for url in urls:
            self.assertEqual(self.client.get(url).status_code,403)
    def test_per_model_permission_checks_and_read_only_staff(self):
        self.client.force_login(self.reader)
        for url in ['/dashboard/','/dashboard/consultations/','/dashboard/contacts/','/dashboard/reviews/','/dashboard/reports/','/dashboard/live/']:
            self.assertEqual(self.client.get(url).status_code,200)
        self.assertEqual(self.client.get('/dashboard/users/').status_code,403)
        item=self.request_record()
        review=self.review_record()
        self.assertEqual(self.client.post(reverse('dashboard:request-detail',args=[item.pk]),{'status':'closed'}).status_code,403)
        self.assertEqual(self.client.post(reverse('dashboard:review-approve',args=[review.pk])).status_code,403)
        self.assertEqual(self.client.post(reverse('dashboard:review-reject',args=[review.pk]),{'confirm':'on'}).status_code,403)
        self.assertNotContains(self.client.get('/dashboard/reviews/'),'button-danger')
        for action in ['approve','reject']:
            self.client.post('/admin/core/review/',{'action':action,'_selected_action':[review.pk]})
            review.refresh_from_db()
            self.assertEqual(review.status,'pending')
    def test_staff_without_permissions_cannot_read_private_lists_or_live(self):
        staff=get_user_model().objects.create_user(username='no-permissions',email='none@example.com',is_staff=True)
        self.client.force_login(staff)
        for url in ['/dashboard/','/dashboard/live/','/dashboard/live/?mode=contact','/dashboard/live/?mode=reviews','/dashboard/reviews/','/dashboard/consultations/','/dashboard/reports/']:
            self.assertEqual(self.client.get(url).status_code,403)
        self.assertEqual(self.client.get('/dashboard/settings/').status_code,200)
    def test_every_sidebar_page_is_functional(self):
        for url in ['/dashboard/','/dashboard/consultations/','/dashboard/contacts/','/dashboard/reviews/','/dashboard/reports/','/dashboard/users/','/dashboard/settings/']:
            response=self.client.get(url)
            self.assertEqual(response.status_code,200)
            self.assertContains(response,'محاماة')
            self.assertIn('no-store',response.headers['Cache-Control'])
        self.assertEqual(self.client.get('/admin/').status_code,200)
    def test_public_request_is_saved_once_and_appears_immediately(self):
        public=Client()
        payload={'name':'عميل جديد','phone':'+966000000002','email':'new@example.com','service':'استشارة','message':'تفاصيل استشارة جديدة من الموقع العام.'}
        for _ in range(2):
            self.assertEqual(public.post('/contact-requests',payload).status_code,302)
        self.assertEqual(ContactRequest.objects.count(),1)
        item=ContactRequest.objects.get()
        self.assertEqual(item.status,'new')
        self.assertEqual(item.request_type,'consultation')
        self.assertFalse(item.is_demo)
        self.assertContains(self.client.get('/dashboard/'),payload['name'])
        live=self.client.get('/dashboard/live/').json()
        self.assertIn(payload['name'],live['html'])
        self.assertIn('تفاصيل استشارة',self.client.get(reverse('dashboard:request-detail',args=[item.pk])).content.decode())
    def test_duplicate_review_protection_expiry_and_distinct_payload(self):
        public=Client()
        data={'name':'نص تجريبي','rating':4,'review':'نص تعليق واضح لأجل اختبار التكرار.'}
        public.post('/reviews',data)
        public.post('/reviews',data)
        self.assertEqual(Review.objects.count(),1)
        SubmissionWindow.objects.all().delete()
        SubmissionReceipt.objects.update(expires_at=timezone.now()-timedelta(seconds=1))
        public.post('/reviews',data)
        public.post('/reviews',{**data,'review':'نص تعليق آخر مختلف عن التعليق السابق.'})
        self.assertEqual(Review.objects.count(),3)
    def test_each_selected_rating_is_saved_and_displayed_exactly(self):
        public=Client()
        self.assertContains(public.get('/'),'<select name="rating" required>')
        for rating in range(1,6):
            with self.subTest(rating=rating):
                data={'name':f'اختبار القيمة {rating}', 'rating':str(rating), 'review':f'اختبار حفظ وعرض القيمة المختارة رقم {rating}.'}
                response=public.post('/reviews',data,REMOTE_ADDR=f'127.0.1.{rating}')
                self.assertEqual(response.status_code,302)
                item=Review.objects.get(name=data['name'])
                self.assertEqual(item.rating,rating)
                detail=self.client.get(reverse('dashboard:review-detail',args=[item.pk]))
                self.assertEqual(detail.content.decode().count('class="filled"'),rating)
                self.client.post(reverse('dashboard:review-approve',args=[item.pk]))
                html=public.get('/').content.decode()
                block=re.search(r'aria-label="تقييم '+str(rating)+r' من 5">(.*?)</div>',html,re.S)
                self.assertIsNotNone(block)
                self.assertEqual(block[1].count('class="filled"'),rating)
        # Keep the user's chosen value when another field needs correction.
        response=public.post('/reviews',{'name':'x','rating':'4','review':'نص صالح مع اسم يحتاج إلى تصحيح.'},REMOTE_ADDR='127.0.1.20')
        self.assertContains(response,'value="4" selected')
    def test_rating_requires_an_explicit_valid_choice(self):
        from apps.core.forms import ReviewForm
        self.assertIsNone(ReviewForm()['rating'].value())
        public=Client()
        for index,value in enumerate(['','0','6','1.5','invalid']):
            response=public.post('/reviews',{'name':'اختبار اختيار','rating':value,'review':'رسالة اختبار تتطلب اختيار تقييم صحيح.'},REMOTE_ADDR=f'127.0.2.{index}')
            self.assertEqual(response.status_code,200)
            self.assertIn('rating',response.context['review_form'].errors)
        self.assertFalse(Review.objects.exists())
    def test_live_update_interval_label_is_not_visible(self):
        response=self.client.get('/dashboard/')
        self.assertNotContains(response,'تحديث تلقائي كل 15 ثانية')
        self.assertContains(response,'تحديث الآن')
        self.assertNotContains(self.client.get('/dashboard/settings/'),'15 ثانية')
    def test_newest_requests_first(self):
        old=self.request_record(name='قديم',created_at=timezone.now()-timedelta(days=3))
        recent=self.request_record(name='حديث')
        rows=list(self.client.get('/dashboard/consultations/').context['request_rows'])
        self.assertEqual([r.pk for r in rows],[recent.pk,old.pk])
    def test_status_update_and_correct_chart_counts(self):
        item=self.request_record()
        for status in ['in_progress','contacted','closed']:
            self.request_record(status=status)
        self.request_record(request_type='contact')
        chart=self.client.get('/dashboard/').context['chart']
        self.assertEqual(chart['total'],4)
        self.assertEqual([s['count'] for s in chart['legend']],[1,1,1,1])
        response=self.client.post(reverse('dashboard:request-detail',args=[item.pk]),{'status':'contacted','request_type':'consultation','internal_notes':'تم التواصل مع العميل.'})
        self.assertEqual(response.status_code,302)
        item.refresh_from_db()
        self.assertEqual(item.status,'contacted')
        self.assertEqual(item.internal_notes,'تم التواصل مع العميل.')
        chart=self.client.get('/dashboard/').context['chart']
        self.assertEqual([s['count'] for s in chart['legend']],[0,1,2,1])
        self.assertTrue(LogEntry.objects.filter(object_id=str(item.pk)).exists())
    def test_invalid_status_rejected_and_type_change_does_not_duplicate(self):
        item=self.request_record()
        url=reverse('dashboard:request-detail',args=[item.pk])
        self.assertEqual(self.client.post(url,{'status':'invented','request_type':'contact'}).status_code,200)
        item.refresh_from_db()
        self.assertEqual(item.status,'new')
        self.client.post(url,{'status':'in_progress','request_type':'contact','internal_notes':'متابعة عامة'})
        self.assertEqual(ContactRequest.objects.count(),1)
        self.assertNotContains(self.client.get('/dashboard/consultations/'),item.name)
        self.assertContains(self.client.get('/dashboard/contacts/'),item.name)
    def test_approve_publishes_once_and_pending_rejected_hidden(self):
        approved=self.review_record(name='قابل للنشر')
        self.review_record(name='قيد المراجعة الخاص',status='pending')
        self.review_record(name='مرفوض خاص',status='rejected')
        url=reverse('dashboard:review-approve',args=[approved.pk])
        self.assertEqual(self.client.get(url).status_code,405)
        for _ in range(2):
            self.assertEqual(self.client.post(url).status_code,302)
        approved.refresh_from_db()
        self.assertEqual(approved.status,'approved')
        public=Client().get('/')
        self.assertContains(public,'قابل للنشر',count=1)
        self.assertNotContains(public,'قيد المراجعة الخاص')
        self.assertNotContains(public,'مرفوض خاص')
        self.assertEqual(LogEntry.objects.filter(object_id=str(approved.pk)).count(),1)
    def test_rejection_requires_confirmation_and_removes_publication(self):
        item=self.review_record(status='approved')
        url=reverse('dashboard:review-reject',args=[item.pk])
        self.assertEqual(self.client.get(url).status_code,200)
        self.client.post(url,{})
        item.refresh_from_db()
        self.assertEqual(item.status,'approved')
        self.client.post(url,{'confirm':'on'})
        item.refresh_from_db()
        self.assertEqual(item.status,'rejected')
        self.assertNotContains(Client().get('/'),item.review)
        # The preserved Django Admin bulk action must also require confirmation.
        item.status='approved'
        item.save()
        data={'action':'reject','_selected_action':[item.pk]}
        self.assertEqual(self.client.post('/admin/core/review/',data).status_code,200)
        item.refresh_from_db()
        self.assertEqual(item.status,'approved')
        self.client.post('/admin/core/review/',{**data,'confirm_reject':'yes'})
        item.refresh_from_db()
        self.assertEqual(item.status,'rejected')
    def test_review_table_has_no_status_column_or_visibility_toggle(self):
        self.review_record()
        response=self.client.get('/dashboard/reviews/')
        self.assertNotContains(response,'<th scope="col">الحالة</th>')
        self.assertNotContains(response,'إظهار في الموقع')
        self.assertContains(response,'عرض التقييم')
        self.assertContains(response,'رفض')
    def test_csrf_and_post_only_mutation_routes(self):
        review=self.review_record()
        item=self.request_record()
        csrf=Client(enforce_csrf_checks=True)
        csrf.force_login(self.manager)
        for url,payload in [(reverse('dashboard:review-approve',args=[review.pk]),{}),
                            (reverse('dashboard:review-reject',args=[review.pk]),{'confirm':'on'}),
                            (reverse('dashboard:request-detail',args=[item.pk]),{'status':'closed'}),
                            ('/dashboard/settings/',{'page_size':20}),('/dashboard/logout/',{})]:
            self.assertEqual(csrf.post(url,payload).status_code,403)
        self.assertEqual(csrf.get('/dashboard/logout/').status_code,405)
        csrf.get(reverse('dashboard:review-detail',args=[review.pk]))
        token=csrf.cookies['csrftoken'].value
        self.assertEqual(csrf.post(reverse('dashboard:review-approve',args=[review.pk]),HTTP_X_CSRFTOKEN=token).status_code,302)
    def test_search_filters_pagination_keep_query(self):
        for i in range(23):
            self.request_record(name=f'عميل بحث {i}',status='contacted' if i%2==0 else 'new')
        response=self.client.get('/dashboard/consultations/',{'q':'بحث','status':'contacted','page':2})
        self.assertEqual(response.context['request_rows'].paginator.count,12)
        self.assertEqual(len(response.context['request_rows']),2)
        self.assertContains(response,'q=')
        self.assertContains(response,'status=contacted')
        self.assertEqual(self.client.get('/dashboard/consultations/?status=invalid').context['request_rows'].paginator.count,0)
        self.review_record(review='عبارة محددة للبحث في التقييمات.')
        self.assertEqual(self.client.get('/dashboard/reviews/?q=محددة').context['review_rows'].paginator.count,1)
    @override_settings(DEBUG=True)
    def test_demo_seed_idempotent_cleanup_preserves_real_data(self):
        real=self.request_record()
        genuine_review=self.review_record(status='approved')
        call_command('seed_demo',stdout=StringIO())
        call_command('seed_demo',stdout=StringIO())
        self.assertEqual(ContactRequest.objects.filter(is_demo=True,request_type='consultation').count(),24)
        self.assertEqual(ContactRequest.objects.filter(is_demo=True,request_type='contact').count(),12)
        self.assertEqual(Review.objects.filter(is_demo=True).count(),18)
        self.assertContains(Client().get('/'),'نموذج تجريبي')
        call_command('remove_demo',stdout=StringIO())
        self.assertTrue(ContactRequest.objects.filter(pk=real.pk).exists())
        self.assertTrue(Review.objects.filter(pk=genuine_review.pk).exists())
        self.assertEqual(ContactRequest.objects.count(),1)
        self.assertEqual(Review.objects.count(),1)
    @override_settings(DEBUG=False)
    def test_production_cannot_seed_or_publish_demo_testimonials(self):
        with self.assertRaises(CommandError):
            call_command('seed_demo',stdout=StringIO())
        self.review_record(name='DEMO-PRIVATE',is_demo=True,status='approved')
        self.assertNotContains(Client().get('/'),'DEMO-PRIVATE')
    def test_report_range_and_review_totals(self):
        self.request_record(created_at=timezone.now()-timedelta(days=20))
        self.request_record()
        self.review_record(status='pending')
        today=timezone.localdate()
        response=self.client.get('/dashboard/reports/',{'start':today.isoformat(),'end':today.isoformat()})
        self.assertEqual(response.context['chart']['total'],1)
        self.assertEqual(response.context['review_totals'][0][1],1)
        response=self.client.get('/dashboard/reports/',{'start':'2026-10-30','end':'2026-10-01'})
        self.assertTrue(response.context['form'].errors)
        self.assertEqual(response.context['chart']['total'],0)
    def test_preferences_and_users_are_safe(self):
        self.assertEqual(self.client.post('/dashboard/settings/',{'page_size':20}).status_code,302)
        self.assertEqual(self.client.session['dashboard_preferences'],{'page_size':20,'live_updates':False})
        self.assertEqual(self.client.post('/dashboard/settings/',{'page_size':100000}).status_code,200)
        self.assertEqual(self.client.session['dashboard_preferences']['page_size'],20)
        response=self.client.get('/dashboard/users/')
        self.assertContains(response,self.reader.username)
        self.assertNotContains(response,self.ordinary.username)
        self.assertEqual(self.client.post('/dashboard/users/',{'is_superuser':True}).status_code,405)
    def test_login_staff_validation_and_rate_limit(self):
        self.client.logout()
        self.reader.set_password('Only-used-in-tests-2026')
        self.reader.save()
        self.ordinary.set_password('Only-used-in-tests-2026')
        self.ordinary.save()
        response=self.client.post('/dashboard/login/',{'username':self.ordinary.username,'password':'Only-used-in-tests-2026'})
        self.assertEqual(response.status_code,200)
        self.assertNotIn('_auth_user_id',self.client.session)
        response=self.client.post('/dashboard/login/',{'username':self.reader.username,'password':'Only-used-in-tests-2026'})
        self.assertEqual(response.status_code,302)
        self.client.logout()
        for _ in range(3):
            self.client.post('/dashboard/login/',{'username':'missing','password':'invalid'})
        self.assertEqual(self.client.post('/dashboard/login/',{'username':'missing','password':'invalid'}).status_code,429)
    def test_live_endpoint_preserves_filters_and_does_not_leak_other_models(self):
        self.request_record(name='حدث جديد')
        self.request_record(name='تم الاتصال',status='contacted')
        response=self.client.get('/dashboard/live/',{'mode':'consultation','q':'جديد','status':'new'})
        self.assertEqual(response.status_code,200)
        self.assertIn('حدث جديد',response.json()['html'])
        self.assertNotIn('تم الاتصال',response.json()['html'])
        self.assertEqual(self.client.get('/dashboard/live/?mode=unknown').status_code,400)
    def test_private_fields_escaped_and_never_public(self):
        item=self.request_record(name='<script>alert(1)</script>',internal_notes='CONFIDENTIAL-INTERNAL')
        self.review_record(review='<script>alert(2)</script>')
        response=self.client.get(reverse('dashboard:request-detail',args=[item.pk]))
        self.assertNotContains(response,'<script>alert(1)</script>')
        self.assertContains(response,'&lt;script&gt;')
        public=Client().get('/')
        self.assertNotContains(public,item.message)
        self.assertNotContains(public,'CONFIDENTIAL-INTERNAL')
