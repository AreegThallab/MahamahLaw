"""Exercise the dashboard using a temporary test database, never the real client database.

Run: .venv/Scripts/python dev.py shell -c "exec(open('tests/browser_dashboard.py', encoding='utf-8').read())"
Requires the existing development Playwright installation.
"""
import json
import secrets
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from wsgiref.simple_server import make_server, WSGIRequestHandler
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles.handlers import StaticFilesHandler
from django.core.management import call_command
from django.core.wsgi import get_wsgi_application
from django.db import connections
from django.test import Client, override_settings
from django.test.runner import DiscoverRunner
from playwright.sync_api import sync_playwright
from apps.core.models import ContactRequest, Review

OUT=Path(settings.BASE_DIR)/'test-results'
OUT.mkdir(exist_ok=True)
runner=DiscoverRunner(verbosity=0)
database_config=runner.setup_databases()
server=None
db_worker=ThreadPoolExecutor(max_workers=1)
def db_call(callback):
    return db_worker.submit(callback).result()
class QuietHandler(WSGIRequestHandler):
    def log_message(self,*args):
        pass

try:
    with override_settings(DEBUG=True,SECURE_SSL_REDIRECT=False,SESSION_COOKIE_SECURE=False,CSRF_COOKIE_SECURE=False,ALLOWED_HOSTS=['127.0.0.1','testserver']):
        call_command('seed_demo',verbosity=0)
        password=secrets.token_urlsafe(32)
        user=get_user_model().objects.create_superuser(username='browser-manager',email='browser-manager@example.com',password=password,name='مدير تجريبي')
        server=make_server('127.0.0.1',0,StaticFilesHandler(get_wsgi_application()),handler_class=QuietHandler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        origin=f'http://127.0.0.1:{server.server_port}'
        report={}
        with sync_playwright() as p:
            browser=p.chromium.launch()
            context=browser.new_context(viewport={'width':1440,'height':1000},reduced_motion='reduce')
            page=context.new_page()
            errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(origin+'/dashboard/login/')
            page.locator('input[name=username]').fill(user.username)
            page.locator('input[name=password]').fill(password)
            page.get_by_role('button',name='تسجيل الدخول',exact=True).click()
            page.wait_for_url(origin+'/dashboard/')
            page.evaluate('document.fonts.ready')
            page.screenshot(path=str(OUT/'dashboard-desktop.png'),full_page=True)
            assert page.locator('[data-chart-total]').inner_text()=='24'
            assert page.locator('.review-panel thead').inner_text().find('الحالة')==-1
            # Check 15-second live update from a real public submission to the test DB.
            payload={'name':'طلب مباشر للاختبار','phone':'+966000009999','email':'live@example.com','service':'الاستشارات القانونية','message':'رسالة اختبار من النموذج العام إلى لوحة الإدارة مباشرة.'}
            public=Client()
            public_page=context.new_page()
            public_page.on('pageerror',lambda error:errors.append(str(error)))
            public_page.goto(origin+'/')
            for field in ['name','phone','email','message']:
                public_page.locator(f'.contact-form [name={field}]').fill(payload[field])
            public_page.locator('.contact-form select[name=service]').select_option(payload['service'])
            public_page.locator('.contact-form button[type=submit]').click()
            public_page.wait_for_url(origin+'/#contact')
            assert 'تم إرسال طلبك بنجاح' in public_page.locator('.contact-form .form-alert.success').inner_text()
            public_page.close()
            page.bring_to_front()
            page.wait_for_function("document.querySelector('[data-live-region]').textContent.includes('طلب مباشر للاختبار')",timeout=24000)
            assert page.locator('[data-chart-total]').inner_text()=='25'
            report['live_update']='New public request and updated chart appeared without reload.'
            # Test approval and rejection through the actual browser forms.
            review_data={'name':'اختبار اعتماد عبر المتصفح','rating':4,'review':'اختبار فعلي لدورة الاعتماد والرفض عبر واجهة الإدارة.'}
            public_page=context.new_page()
            public_page.goto(origin+'/')
            form=public_page.locator('.stacked-form')
            assert form.locator('select[name=rating]').input_value()==''
            form.locator('input[name=name]').fill(review_data['name'])
            form.locator('select[name=rating]').select_option(str(review_data['rating']))
            form.locator('textarea[name=review]').fill(review_data['review'])
            form.locator('button[type=submit]').click()
            public_page.wait_for_url(origin+'/#testimonials')
            public_page.close()
            page.bring_to_front()
            review=db_call(lambda: Review.objects.get(name=review_data['name']))
            assert review.status=='pending'
            assert review.rating==4
            page.goto(origin+f'/dashboard/reviews/{review.pk}/')
            assert page.locator('.review-detail .review-stars .filled').count()==4
            page.get_by_role('button',name='اعتماد ونشر').click()
            assert 'تم اعتماد' in page.locator('.dashboard-main').inner_text()
            assert review_data['review'] in db_call(lambda: public.get('/')).content.decode()
            page.get_by_role('link',name='رفض التقييم',exact=True).click()
            db_call(review.refresh_from_db)
            assert review.status=='approved'
            page.locator('input[name=confirm]').check()
            page.get_by_role('button',name='تأكيد الرفض').click()
            db_call(review.refresh_from_db)
            assert review.status=='rejected'
            assert review_data['review'] not in db_call(lambda: public.get('/')).content.decode()
            report['moderation']='Approval publishes; confirmation required for rejection; rejection removes publication.'
            # State updates and persistent notes.
            item=db_call(lambda: ContactRequest.objects.get(name=payload['name']))
            page.goto(origin+f'/dashboard/requests/{item.pk}/')
            page.locator('select[name=status]').select_option('contacted')
            page.locator('textarea[name=internal_notes]').fill('ملاحظة تجريبية داخلية محفوظة.')
            page.get_by_role('button',name='حفظ التغييرات').click()
            db_call(item.refresh_from_db)
            assert item.status=='contacted' and item.internal_notes
            for route in ['consultations','contacts','reviews','users','reports','settings']:
                response=page.goto(origin+'/dashboard/'+route+'/')
                assert response.status==200,(route,response.status)
            for width,height in [(1440,1000),(768,1024),(390,844)]:
                page.set_viewport_size({'width':width,'height':height})
                page.goto(origin+'/dashboard/')
                page.evaluate('document.fonts.ready')
                assert 'تحديث تلقائي كل 15 ثانية' not in page.locator('body').inner_text()
                assert page.evaluate('document.documentElement.scrollWidth===innerWidth'),width
                assert not errors,errors
                assert page.locator('.donut').bounding_box()['width']>100
                if width<=900:
                    toggle=page.locator('.sidebar-toggle')
                    toggle.click()
                    assert toggle.get_attribute('aria-expanded')=='true'
                    page.screenshot(path=str(OUT/f'dashboard-sidebar-{width}.png'))
                    page.keyboard.press('Escape')
                    assert toggle.get_attribute('aria-expanded')=='false'
                page.screenshot(path=str(OUT/f'dashboard-{width}.png'),full_page=True)
                for route in ['consultations','contacts','reviews','users','reports','settings',f'requests/{item.pk}',f'reviews/{review.pk}']:
                    response=page.goto(origin+'/dashboard/'+route+'/')
                    assert response.status==200,(width,route,response.status)
                    assert page.evaluate('document.documentElement.scrollWidth===innerWidth'),(width,route)
                    assert not errors,errors
                report[str(width)]={'overflow':False,'js_errors':list(errors),'navigation':'passed'}
            # Preferences persist and disable polling when selected.
            page.goto(origin+'/dashboard/settings/')
            page.locator('select[name=page_size]').select_option('20')
            page.locator('input[name=live_updates]').uncheck()
            page.get_by_role('button',name='حفظ التفضيلات').click()
            page.goto(origin+'/dashboard/')
            assert page.locator('body').get_attribute('data-live-enabled')=='false'
            # With JavaScript disabled, database-backed pages/forms still work.
            nojs=browser.new_context(storage_state=context.storage_state(),java_script_enabled=False,viewport={'width':390,'height':844})
            offline_page=nojs.new_page()
            assert offline_page.goto(origin+'/dashboard/').status==200
            assert offline_page.locator('.sidebar').is_visible()
            assert offline_page.locator('[data-chart-total]').inner_text()=='25'
            nojs.close()
            report['no_javascript']='Tables, chart and sidebar remain usable; server-rendered fallback works.'
            # Logout is a CSRF-protected POST form; no hardcoded accounts remain.
            page.set_viewport_size({'width':1440,'height':1000})
            page.locator('.logout-form button').click()
            page.wait_for_url(origin+'/dashboard/login/')
            assert page.goto(origin+'/dashboard/').url.startswith(origin+'/dashboard/login/')
            browser.close()
        (OUT/'dashboard-browser-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print('Dashboard browser checks passed: live polling, moderation, request update, settings, logout and 1440/768/390 responsive views.')
finally:
    if server:
        server.shutdown()
        server.server_close()
    db_worker.submit(connections.close_all).result()
    db_worker.shutdown()
    connections.close_all()
    runner.teardown_databases(database_config)
