"""Test every product page with native Python Playwright and capture real UI.
Run: uv run --project scripts/ui-tests python scripts/test_pages.py
Requires running services and APP_MODE=demo. No provider/account key is read here.
"""
import argparse
import json
import re
from importlib.metadata import version
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, expect

PAGES = [
    ('overview', 'Overview'), ('facility', 'Facility operations'),
    ('energy', 'Energy'), ('water', 'Water & reserves'),
    ('waste', 'Waste operations'), ('environment', 'Environment'),
    ('assets', 'Assets & maintenance'), ('parking', 'Traffic & parking'),
    ('safety', 'Safety incidents'), ('simulations', 'What-if studio'),
    ('sustainability', 'Sustainability & cost'), ('actions', 'Action centre'),
    ('reports', 'Reports'), ('chat', 'Chatbot'), ('agent', 'Agent activity'),
    ('imports', 'Import quality'), ('models', 'Model evaluation'),
    ('settings', 'Policy & settings'),
]


def loaded(page, slug):
    expect(page.locator('.loading:visible')).to_have_count(0)
    expect(page.locator('.notice.error:visible')).to_have_count(0)
    if slug in {'overview', 'energy', 'water'}:
        expect(page.locator('.kpi .value')).to_have_count(4)
        for item in page.locator('.kpi .value').all():
            expect(item).to_contain_text(re.compile(r'\d'))
        expect(page.locator('.chart canvas').first).to_be_visible()
    elif slug == 'environment':
        expect(page.locator('.grid.three .metric-mini')).to_have_count(6)
    elif slug == 'waste':
        expect(page.locator('.grid.three .metric-mini')).to_have_count(4)
    elif slug in {'parking', 'safety'}:
        expect(page.locator('.grid.three .metric-mini')).to_have_count(3)
        for item in page.locator('.grid.three .metric-mini').all():
            expect(item).to_have_text(re.compile(r'\d'))
    elif slug == 'assets':
        expect(page.locator('pre.data').first).to_contain_text('"assets"')
    elif slug == 'sustainability':
        expect(page.locator('pre.data').first).to_contain_text('cost_estimate_inr')
    elif slug == 'models':
        expect(page.locator('.grid.three .panel')).to_have_count(7)
        expect(page.get_by_role('heading', name='anomaly', exact=True)).to_be_visible()
    elif slug in {'facility', 'agent', 'imports', 'settings'}:
        expect(page.locator('.record-title').first).to_be_visible()
    elif slug == 'actions':
        expect(page.locator('.action-columns')).to_be_visible()
    elif slug == 'reports':
        expect(page.get_by_role('link', name='Download CSV').first).to_be_visible()
    elif slug == 'chat':
        expect(page.get_by_label('Message', exact=True)).to_be_visible()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://localhost:3000')
    parser.add_argument('--output', default='docs/screenshots/pages')
    args = parser.parse_args()
    output = Path(args.output); output.mkdir(parents=True, exist_ok=True)
    results = []; failures = []
    expect.set_options(timeout=60000)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1440, 'height': 960}, device_scale_factor=1)
        page = context.new_page()
        page.set_default_timeout(60000)
        page.set_default_navigation_timeout(60000)
        errors = []; responses = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        def console_error(message):
            if message.type != 'error':
                return
            # The login screen deliberately probes the current anonymous session.
            anonymous_auth_probe = (urlparse(message.location.get('url', '')).path in
                                    {'/api/v1/me', '/api/v1/worlds', '/api/v1/organizations', '/api/v1/facilities'}
                                    and '401' in message.text)
            if not anonymous_auth_probe:
                errors.append('console: ' + message.text)
        page.on('console', console_error)
        page.on('response', lambda response: responses.append({'url': response.url.split('?')[0], 'status': response.status})
                if '/api/v1/' in response.url else None)
        try:
            page.goto(args.url, wait_until='networkidle')
            expect(page.get_by_role('heading', name='Choose a demo role')).to_be_visible()
            expect(page.locator('.demo-role')).to_have_count(7)
            assert not errors, 'Login JavaScript/console error: ' + '; '.join(errors)
            page.screenshot(path=str(output / 'login.png'))
            page.screenshot(path=str(output / 'login-full.png'), full_page=True)
            results.append({'page': 'login', 'title': 'Demo sign-in', 'passed': True, 'screenshot': 'login.png', 'full_screenshot': 'login-full.png'})
            page.get_by_role('button', name='Continue as Hospital admin', exact=True).click()
            expect(page.get_by_role('heading', name='Overview', exact=True)).to_be_visible()
            page.wait_for_load_state('networkidle')
            page.get_by_label('World', exact=True).select_option(label='extended_v1')
            page.wait_for_load_state('networkidle')
            for slug, title in PAGES:
                errors.clear(); responses.clear()
                try:
                    response = page.goto(args.url.rstrip('/') + '/' + slug, wait_until='networkidle')
                    assert response and response.status == 200, 'Document did not return HTTP 200'
                    expect(page.locator('main h1')).to_have_text(title)
                    expect(page.locator('.clock')).to_be_visible()
                    expect(page.locator('.loading:visible')).to_have_count(0)
                    expect(page.locator('.notice.error:visible')).to_have_count(0)
                    expect(page.get_by_label('World').locator('option:checked')).to_have_text('extended_v1')
                    assert not errors, 'JavaScript exception: ' + '; '.join(errors)
                    assert not [r for r in responses if r['status'] >= 400], 'Domain API request failed'
                    # Exercise the global refresh and await actual scoped reads.
                    refresh_path = {
                        'overview': '/overview', 'energy': '/overview', 'water': '/reserves',
                        'waste': '/waste/state', 'environment': '/environment/state',
                        'assets': '/assets/state', 'parking': '/parking/state',
                        'safety': '/safety/state', 'sustainability': '/sustainability',
                        'models': '/models', 'facility': '/records/buildings',
                        'actions': '/actions', 'reports': '/reports',
                        'chat': '/conversations', 'agent': '/records/agent_runs',
                        'imports': '/records/dataset_versions', 'settings': '/records/policy_versions',
                        'simulations': '/simulations',
                    }[slug]
                    with page.expect_response(lambda r: urlparse(r.url).path == '/api/v1' + refresh_path) as refreshed:
                        page.get_by_role('button', name='Refresh', exact=True).click()
                    assert refreshed.value.status == 200, 'Refresh API did not return HTTP 200'
                    # Reading the JSON body waits for the complete response without
                    # creating the SDK's unresolved target-close watcher.
                    assert isinstance(refreshed.value.json(), dict), 'Refresh did not return a domain JSON object'
                    page.wait_for_load_state('networkidle')
                    expect(page.locator('.loading:visible')).to_have_count(0)
                    expect(page.locator('.notice.error:visible')).to_have_count(0)
                    assert not errors, 'JavaScript exception after refresh'
                    assert not [r for r in responses if r['status'] >= 400], 'Domain API refresh failed'
                    if slug in {'overview', 'energy', 'water'}:
                        expect(page.locator('.chart canvas').first).to_be_visible()
                    if slug in {'facility','water','waste','environment','assets','parking','safety','sustainability','settings'}:
                        add = page.get_by_role('button', name=re.compile(r'^Add '))
                        if add.count():
                            add.first.click()
                            dialog = page.get_by_role('dialog')
                            expect(dialog).to_be_visible()
                            expect(dialog.get_by_role('button', name='Save record')).to_be_visible()
                            dialog.get_by_role('button', name='Cancel', exact=True).click()
                            expect(dialog).not_to_be_visible()
                            page.wait_for_load_state('networkidle')
                    if slug == 'simulations' and page.get_by_role('button', name='View result').count():
                        page.get_by_role('button', name='View result').first.click()
                        expect(page.get_by_text('Simulated • saved result', exact=True)).to_be_visible()
                    if slug == 'chat':
                        expect(page.get_by_label('Message', exact=True)).to_be_visible()
                        # Display the completed real-provider flow from the browser suite.
                        conversation = page.get_by_label('Conversation', exact=True)
                        option = conversation.locator('option').filter(has_text='Read current water reserves using your tools; show assumptions.').first
                        if option.count():
                            conversation.select_option(option.get_attribute('value'))
                        else:
                            page.get_by_label('Message', exact=True).fill('Read current water reserves using your tools; show assumptions.')
                            page.get_by_role('button', name='Send message', exact=True).click()
                            expect(page.get_by_text(re.compile(r'run completed')).first).to_be_visible(timeout=180000)
                        expect(page.locator('.message.assistant').first).to_be_visible()
                    loaded(page, slug)
                    # A final completed response and two painted frames keep captures
                    # from racing React effects after refresh/dialog closure.
                    page.wait_for_load_state('networkidle')
                    loaded(page, slug)
                    page.evaluate('new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
                    page.evaluate('document.fonts.ready')
                    page.evaluate('window.scrollTo(0, 0)')
                    loaded(page, slug)
                    assert not errors, 'JavaScript exception before capture: ' + '; '.join(errors)
                    assert not [r for r in responses if r['status'] >= 400], 'Domain API request failed before capture'
                    page.screenshot(path=str(output / f'{slug}.png'))
                    page.screenshot(path=str(output / f'{slug}-full.png'), full_page=True)
                    result = {'page': slug, 'title': title, 'passed': True, 'screenshot': f'{slug}.png', 'full_screenshot': f'{slug}-full.png',
                              'world': 'extended_v1', 'api_responses': list(responses)}
                    print('PASS', slug, flush=True)
                except Exception as error:
                    page.screenshot(path=str(output / f'{slug}-failed.png'), full_page=True)
                    result = {'page': slug, 'title': title, 'passed': False, 'error': str(error)}
                    failures.append(slug); print('FAIL', slug, str(error)[:250], flush=True)
                results.append(result)
            # Check the loaded mobile workspace and capture it separately.
            errors.clear(); responses.clear()
            page.set_viewport_size({'width': 390, 'height': 844})
            page.goto(args.url.rstrip('/') + '/overview', wait_until='networkidle')
            expect(page.get_by_role('heading', name='Overview', exact=True)).to_be_visible()
            loaded(page, 'overview')
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Mobile horizontal overflow'
            assert not errors, 'Mobile JavaScript exception'
            assert not [r for r in responses if r['status'] >= 400], 'Mobile domain API request failed'
            page.screenshot(path=str(output / 'overview-mobile.png'), full_page=True)
            results.append({'page': 'overview-mobile', 'title': 'Mobile overview', 'passed': True,
                            'screenshot': 'overview-mobile.png', 'viewport': {'width': 390, 'height': 844},
                            'world': 'extended_v1', 'api_responses': list(responses)})
        finally:
            report = {'captured_at': datetime.now(timezone.utc).isoformat(), 'base_url': args.url,
                      'viewport': {'width': 1440, 'height': 960}, 'playwright_version': version('playwright'), 'source': 'actual running synthetic demo',
                      'results': results, 'failed_pages': failures}
            (output / 'page-results.json').write_text(json.dumps(report, indent=2) + '\n')
            context.close(); browser.close()
    if failures:
        raise SystemExit('Page verification failed: ' + ', '.join(failures))
    print('PASS all 18 product pages, login and mobile overview')


if __name__ == '__main__':
    main()
