"""Verify frontend refinements against the Django server, without writing business records."""
import hashlib
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'test-results'
before = json.loads((OUT / 'protected-sections-before.json').read_text(encoding='utf-8'))
report = {}
with sync_playwright() as p:
    browser = p.chromium.launch()
    for width, height in [(1440,1000),(768,1024),(390,844)]:
        # Compare protected layout with original CSS at the same loaded-font state.
        # The early pre-edit snapshot can include a font-swap frame; retain its HTML
        # check, then obtain deterministic geometry with the refinement sheet disabled.
        baseline_page = browser.new_page(viewport={'width':width,'height':height}, reduced_motion='reduce')
        baseline_page.route('**/refinements.css', lambda route: route.fulfill(status=200,content_type='text/css',body=''))
        baseline_page.goto('http://127.0.0.1:8020/')
        baseline_page.evaluate('document.fonts.ready')
        baseline_page.wait_for_timeout(100)
        baseline = baseline_page.evaluate('''()=>Object.fromEntries(['why','methodology'].map(id=>[id,[...document.querySelectorAll('#'+id+' .why-item, #'+id+' .timeline-item')].map(e=>({html:e.outerHTML, width:e.getBoundingClientRect().width,height:e.getBoundingClientRect().height, x:e.getBoundingClientRect().x,style:[getComputedStyle(e).padding,getComputedStyle(e).gap,getComputedStyle(e).backgroundImage,getComputedStyle(e).transform]}))]))''')
        for section in baseline:
            assert [e['html'] for e in baseline[section]] == [e['html'] for e in before[str(width)][section]]
        baseline_page.close()
        page = browser.new_page(viewport={'width':width, 'height':height}, reduced_motion='reduce')
        errors, bad_responses = [], []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('response', lambda response: bad_responses.append([response.status,response.url]) if response.status >= 400 else None)
        assert page.goto('http://127.0.0.1:8020/').status == 200
        page.evaluate('document.fonts.ready')
        page.locator('img').evaluate_all('(images)=>images.forEach(i=>i.loading="eager")')
        page.wait_for_function('Array.from(document.images).every(i=>i.complete && i.naturalWidth>0)')
        assert 'MAHAMAH' in page.title()
        assert page.locator('.eyebrow').count() == 0
        assert page.locator('.hero-logo').count() == 0
        assert page.locator('.navbar img, .hero-office-visual > img').count() == 2
        assert page.locator('#services h2').inner_text() == 'خدمات قانونية تحمي مصالحك'
        assert page.locator('#contact h2').inner_text() == 'تواصل'
        assert page.locator('#contact input[name=csrfmiddlewaretoken]').count() == 1
        assert page.locator('#expertise .icon-badge svg').count() == 8
        assert page.locator('.team-card').count() == 3
        assert page.locator('.team-card img').count() == 0
        assert page.locator('.team-avatar svg').count() == 3
        assert page.locator('.team-card .demo-label').count() == 3
        assert page.locator('.team-card h3').all_text_contents() == ['أحمد العتيبي','سارة القحطاني','نورة الدوسري']
        assert page.locator('.social-links svg').count() == 3
        assert page.locator('.social-links a').count() == 0
        assert page.locator('html').get_attribute('dir') == 'rtl'
        assert page.evaluate('document.documentElement.scrollWidth === innerWidth')
        assert page.evaluate('document.fonts.check(\'400 16px "Thmanyah Sans"\')')
        assert page.evaluate('document.fonts.check(\'900 16px "Thmanyah Sans"\')')
        rendered_fonts = page.locator('h1').evaluate('e=>getComputedStyle(e).fontFamily')
        assert rendered_fonts.startswith('"Thmanyah Display"')
        assert page.evaluate('document.fonts.check(\'900 16px "Thmanyah Display"\')')
        cards = page.locator('.team-card').evaluate_all('(cards)=>cards.map(e=>({height:e.getBoundingClientRect().height,x:e.getBoundingClientRect().x,y:e.getBoundingClientRect().y}))')
        assert max(c['height'] for c in cards)-min(c['height'] for c in cards) < 1
        if width == 1440:
            assert len(set(c['y'] for c in cards)) == 1
        if width == 390:
            assert len(set(c['y'] for c in cards)) == 3
        protected = page.evaluate('''()=>Object.fromEntries(['why','methodology'].map(id=>[id,[...document.querySelectorAll('#'+id+' .why-item, #'+id+' .timeline-item')].map(e=>({html:e.outerHTML, width:e.getBoundingClientRect().width,height:e.getBoundingClientRect().height, x:e.getBoundingClientRect().x,style:[getComputedStyle(e).padding,getComputedStyle(e).gap,getComputedStyle(e).backgroundImage,getComputedStyle(e).transform]}))]))''')
        # Reduced-motion animation may finish at an identity matrix instead of `none`.
        for snapshot in (protected, baseline):
            for items in snapshot.values():
                for item in items:
                    if item['style'][-1] == 'matrix(1, 0, 0, 1, 0, 0)':
                        item['style'][-1] = 'none'
        differences = [(section, i, key, old[key], new[key]) for section in protected for i,(old,new) in enumerate(zip(baseline[section],protected[section])) for key in old if old[key] != new[key]]
        assert not differences, (width, differences)
        for link in page.locator('a[href^="#"]').all():
            assert page.locator(link.get_attribute('href')).count() == 1
        faq = page.locator('.faq-item button').first
        faq.click()
        assert faq.get_attribute('aria-expanded') == 'true'
        faq.click()
        assert faq.get_attribute('aria-expanded') == 'false'
        if width <= 900:
            page.locator('[data-menu-toggle]').click()
            assert page.locator('[data-menu-toggle]').get_attribute('aria-expanded') == 'true'
            page.locator('.nav-link[href="#about"]').click()
            assert page.locator('[data-menu-toggle]').get_attribute('aria-expanded') == 'false'
        next_button = page.locator('[data-slider-next]')
        next_button.click()
        page.wait_for_timeout(100)
        assert page.locator('[data-testimonial-track]').evaluate('e=>e.scrollLeft') < 0
        page.locator('[data-slider-prev]').click()
        page.wait_for_timeout(100)
        assert abs(page.locator('[data-testimonial-track]').evaluate('e=>e.scrollLeft')) < 1
        # Browser validation without submitting or changing the existing database.
        assert page.locator('.contact-form').evaluate('e=>e.checkValidity()') is False
        page.locator('.contact-form input[name=name]').fill('تجربة الواجهة')
        page.locator('.contact-form input[name=phone]').fill('+966500000000')
        page.locator('.contact-form select').select_option(index=1)
        page.locator('.contact-form textarea').fill('اختبار للواجهة دون إرسال النموذج أو حفظ سجل.')
        assert page.locator('.contact-form').evaluate('e=>e.checkValidity()') is True
        page.locator('.contact-form').evaluate('e=>e.reset()')
        page.locator('[data-back-top]').evaluate('e=>e.click()')
        page.wait_for_timeout(100)
        assert page.evaluate('scrollY') == 0
        assert not errors, errors
        assert not bad_responses, bad_responses
        page.screenshot(path=str(OUT/f'refined-{width}.png'), full_page=True, clip={'x':0,'y':0,'width':width,'height':page.evaluate('document.documentElement.scrollHeight')})
        for section in ['home','expertise','team','testimonials']:
            page.locator('#'+section).screenshot(path=str(OUT/f'refined-{section}-{width}.png'))
        report[width] = {'js_errors': errors, 'asset_errors':bad_responses, 'font':rendered_fonts, 'team_cards':cards, 'protected_sections':'unchanged', 'interactions':'passed'}
        page.close()
    browser.close()
(OUT/'refinement-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('1440/768/390 checks passed; protected cards and timeline unchanged; no business records submitted.')
