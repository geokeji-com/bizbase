import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { launch, evidence, screenshot, privateRoot } from './common.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const credentials = JSON.parse(await fs.readFile(path.join(privateRoot, 'credentials.json'), 'utf8'));
const snapshot = JSON.parse(await fs.readFile(path.join(privateRoot, 'snapshot-s01.json'), 'utf8'));
const expected = snapshot.subjects.find(item => item.customer_id === credentials.delivery_id);
const user = credentials.accounts.reader;
function change(kind, value) {
  execFileSync('python3', [path.join(root, 'scripts/directory/state.py'), kind, value], { cwd: root, stdio: 'pipe' });
}
const browser = await launch();
const results = [];
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('http://127.0.0.1:8081/login');
  await page.locator('#login_email').fill(user.user);
  await page.locator('#login_password').fill(user.password);
  await page.locator('.for-login button[type="submit"]').click();
  await page.waitForURL(url => !url.pathname.includes('/login'));
  await page.goto('http://127.0.0.1:8081/desk/bb-directory');
  const test = id => page.getByTestId(id);
  const customer = () => page.locator(`[data-customer-id="${credentials.delivery_id}"]`);
  await customer().waitFor();
  assert.equal(await page.locator('[data-customer-id]').count(), 1);
  await customer().click();
  await test('subjects-table').waitFor();
  assert.equal(await test('subject-row').count(), 1);
  assert.ok((await test('subject-row').textContent()).includes(expected.subject_id));
  assert.ok((await test('subject-row').textContent()).includes(expected.name));
  assert.equal(await test('data-as-of').textContent(), '2026-11-02');
  assert.equal(await test('snapshot-mode').textContent(), '历史快照');
  assert.equal(await test('unknown-type').textContent(), '未知');
  const version = await test('directory-version').textContent();
  const consumer = JSON.parse(await fs.readFile(path.join(privateRoot, 'evidence/consumer.json'), 'utf8'));
  assert.equal(version, consumer.meta.version);
  assert.equal(expected.subject_id, consumer.items[0].subject_id);
  await screenshot(page, 'directory-normal.png');
  results.push('A1/A2 ordinary browser and independent consumer identities/version agree');
  await test('subject-search').fill('round01-browser-nonmatching');
  await test('no-matching-subjects').waitFor();
  await test('clear-subject-search').click();
  await test('subjects-table').waitFor();
  results.push('B2 unmatched subject query and recovery');
  // 延迟实际后端响应；内容仍来自真实 API，不注入合成客户。
  let delayed = false;
  await page.route('**/api/method/bizbase.api.directory.list_subjects?**', async route => {
    const response = await route.fetch();
    if (!delayed && new URL(route.request().url()).searchParams.get('query') === 'slow-query') {
      delayed = true;
      await new Promise(resolve => setTimeout(resolve, 1300));
    }
    await route.fulfill({ response }).catch(() => {});
  });
  await test('subject-search').fill('slow-query');
  await page.waitForTimeout(400);
  await test('loading-state').waitFor();
  await test('subject-search').fill('');
  await test('subjects-table').waitFor();
  await page.waitForTimeout(1500);
  assert.equal(await test('subject-row').count(), 1);
  assert.equal(await test('no-matching-subjects').count(), 0);
  await page.unroute('**/api/method/bizbase.api.directory.list_subjects?**');
  results.push('E1 delayed real response cannot overwrite newer query');
  await page.route('**/api/method/bizbase.api.directory.list_customers?**', route => route.abort('failed'));
  await test('refresh-directory').click();
  await test('source-error').waitFor();
  assert.equal(await test('subjects-table').count(), 0);
  await page.unroute('**/api/method/bizbase.api.directory.list_customers?**');
  await test('retry-source').click();
  await customer().waitFor();
  results.push('C1 browser transport failure clears stale data and retry recovers');
  try {
    change('grant', 'off');
    await test('refresh-directory').click();
    await test('forbidden').waitFor();
    assert.equal(await customer().count(), 0);
    assert.equal(await test('subjects-table').count(), 0);
    assert.equal(await test('snapshot-meta').isVisible(), false);
    await screenshot(page, 'directory-revoked.png');
  } finally { change('grant', 'on'); }
  await test('check-permission').click();
  await customer().waitFor();
  results.push('D3 same browser session loses access after committed revocation');
  try {
    change('directory', 'off');
    await test('refresh-directory').click();
    await test('disabled').waitFor();
    assert.equal(await customer().count(), 0);
  } finally { change('directory', 'on'); }
  await test('retry-source').click();
  await customer().waitFor();
  await customer().click();
  await test('subjects-table').waitFor();
  results.push('F1 actual directory kill switch and retry');
  assert.equal(await test('prototype-toolbar').count(), 0);
  const storage = await page.evaluate(() => JSON.stringify({ local: { ...localStorage }, session: { ...sessionStorage } }));
  for (const account of Object.values(credentials.accounts)) {
    assert.ok(!storage.includes(account.api_secret) && !storage.includes(account.password));
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await screenshot(page, 'directory-mobile.png');
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
  assert.deepEqual(errors, []);
  results.push('D6 production page excludes prototype and machine credentials; responsive rendering');
  await evidence('browser.json', { passed: true, tested_at: new Date().toISOString(), version, results });
  console.log(`Browser: ${results.length} check groups passed`);
} catch (error) {
  const pages = browser.contexts().flatMap(context => context.pages());
  if (pages[0]) await screenshot(pages[0], 'directory-failure.png').catch(() => {});
  throw error;
} finally {
  await browser.close();
}
