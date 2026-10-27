"""Run against Django :8020 and the original Laravel :8001. Requires Playwright."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parents[1] / 'test-results'
OUT.mkdir(exist_ok=True)
with sync_playwright() as p:
    browser = p.chromium.launch()
    report = {}
    for width, height in [(1440,1000),(768,1024),(390,844)]:
        measurements = {}
        for label, port in [('laravel',8001),('django',8020)]:
            page = browser.new_page(viewport={'width':width,'height':height}, reduced_motion='reduce')
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            response = page.goto(f'http://127.0.0.1:{port}/')
            assert response.status == 200, (label,response.status)
            page.evaluate('document.fonts.ready')
            page.locator('img').evaluate_all('(images)=>images.forEach(i=>i.loading="eager")')
            page.wait_for_function('Array.from(document.images).every(i=>i.complete)')
            page.wait_for_timeout(250)
            page.screenshot(path=str(OUT/f'{label}-{width}.png'), full_page=True, clip={'x':0,'y':0,'width':width,'height':page.evaluate('document.documentElement.scrollHeight')})
            measurements[label] = page.evaluate('''() => ({sections:[...document.querySelectorAll('main section')].map(e=>({id:e.id,width:e.getBoundingClientRect().width,height:e.getBoundingClientRect().height})), overflow:document.documentElement.scrollWidth>innerWidth, font:getComputedStyle(document.body).fontFamily})''')
            if label == 'django':
                assert 'MAHAMAH' in page.title()
                assert not errors, errors
                assert not measurements[label]['overflow']
                assert page.locator('img').evaluate_all('(images)=>images.every(i=>i.complete && i.naturalWidth>0)')
                for link in page.locator('a[href^="#"]').all():
                    href = link.get_attribute('href')
                    assert href == '#' or page.locator(href).count() == 1, href
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
                page.locator('[data-slider-next]').evaluate('(button)=>button.click()')
                page.wait_for_timeout(100)
                assert page.locator('[data-testimonial-track]').evaluate('(e)=>e.scrollLeft') < 0
                page.locator('[data-back-top]').evaluate('(button)=>button.click()')
                page.wait_for_timeout(100)
                assert page.evaluate('scrollY') == 0
                measurements[label]['js_errors'] = errors
            page.close()
        assert len(measurements['django']['sections']) == len(measurements['laravel']['sections'])
        report[str(width)] = measurements
    browser.close()
(OUT/'browser-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('Desktop, tablet and mobile screenshots and interaction checks passed.')
