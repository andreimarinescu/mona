import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';

const PASSWORD = 'correct horse';

function msw(page: Page, flags: Record<string, string> = {}) {
  return page.addInitScript((f) => {
    localStorage.setItem('mona.msw', '1');
    for (const [k, v] of Object.entries(f)) localStorage.setItem(`mona.msw.${k}`, v);
  }, flags);
}

function watchConsole(page: Page): string[] {
  const problems: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error' || msg.type() === 'warning') problems.push(`${msg.type()}: ${msg.text()}`);
  });
  page.on('pageerror', (err) => problems.push(`pageerror: ${err.message}`));
  return problems;
}

async function serious(page: Page) {
  const { violations } = await new AxeBuilder({ page }).analyze();
  return violations.filter((v) => v.impact === 'serious' || v.impact === 'critical').map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(' | ')}`);
}

const nav = (page: Page) => page.getByRole('navigation').first();
const entry = (page: Page) => page.getByTestId('chat-entry').getByRole('textbox');
const toast = (page: Page) => page.getByTestId('toast-region');

async function unlock(page: Page) {
  await page.getByLabel('Password').fill(PASSWORD);
  await page.getByRole('button', { name: 'Unlock' }).click();
}

test.describe('unlock and Home', () => {
  test('a locked app sends you to /unlock; the right password lands on Home, and "/" focuses the chat entry', async ({ page }) => {
    await msw(page, { locked: '1' });
    const problems = watchConsole(page);
    await page.goto('/');
    await expect(page).toHaveURL(/\/unlock$/);
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Welcome back');
    await expect(page.getByText(/mona profile set-password/)).toBeVisible();
    await expect(page.getByText(/recovery key/i)).toHaveCount(0);

    await page.getByLabel('Password').fill('nope');
    await page.getByRole('button', { name: 'Unlock' }).click();
    await expect(page.getByText("That password isn't right.")).toBeVisible();
    await expect(page.getByLabel('Password')).toHaveValue('');

    await unlock(page);
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByTestId('mona-brief')).toContainText('I filed 23 documents');
    await expect(page.getByRole('link', { name: 'Home' })).toHaveAttribute('aria-current', 'page');

    await page.locator('body').click({ position: { x: 700, y: 20 } });
    await page.keyboard.press('/');
    await expect(entry(page)).toBeFocused();
    await expect(page.locator('[role="complementary"][aria-label="Mona"]')).toHaveCount(0);
    await entry(page).fill('What is due this week?');
    await page.getByTestId('chat-entry').getByRole('button', { name: 'Send' }).click();
    const panel = page.locator('[role="complementary"][aria-label="Mona"]');
    await expect(panel).toBeVisible();
    await expect(panel.getByText('What is due this week?')).toBeVisible();
    expect(problems.filter((p) => !/status of (423|401) /.test(p))).toEqual([]);
  });

  test('the Home cards and the brief link through to their sources', async ({ page }) => {
    await msw(page);
    await page.goto('/');
    const brief = page.getByTestId('mona-brief');
    await expect(brief).toContainText('6 need your eye.');

    await brief.getByRole('link', { name: '6 need your eye.' }).click();
    await expect(page).toHaveURL(/\/review$/);
    await page.goBack();
    await page.getByRole('button', { name: 'Review 6 documents' }).click();
    await expect(page).toHaveURL(/\/review$/);
    await page.goBack();

    await page.getByTestId('home-review').getByRole('link', { name: 'Open queue' }).click();
    await expect(page).toHaveURL(/\/review$/);
    await page.goBack();
    await page.getByTestId('home-review').getByRole('link', { name: 'Nordtel invoice, September 2026' }).click();
    await expect(page).toHaveURL(/\/review\/doc_/);
    await page.goBack();

    await page.getByTestId('home-due').getByRole('link', { name: 'Call for contributions, Q3 2026' }).click();
    await expect(page).toHaveURL(/\/documents\/doc_/);
    await page.goBack();
    await page.getByRole('button', { name: /^Open URSSAF/ }).click();
    await expect(page).toHaveURL(/\/documents\/doc_/);
    await page.goBack();

    await page.getByTestId('home-activity').getByRole('link', { name: 'Full journal' }).click();
    await expect(page).toHaveURL(/\/activity$/);
    await page.goBack();
    await page.getByTestId('home-ingestion').getByRole('link', { name: 'Activity log' }).click();
    await expect(page).toHaveURL(/\/activity$/);
    await page.goBack();

    await page.getByRole('searchbox', { name: 'Search the archive' }).fill('URSSAF');
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(/\/archive\?q=URSSAF/);
  });

  test('Undo on the activity card undoes and refreshes it', async ({ page }) => {
    await msw(page);
    await page.goto('/');
    const card = page.getByTestId('home-activity');
    await expect(card.getByText('You moved Energie Verte bill, September')).toBeVisible();
    await card.getByRole('button', { name: 'Undo' }).first().click();
    await expect(toast(page).getByText('Undid 1 change')).toBeVisible();
    await expect(card.getByText('You undid a change to Energie Verte bill, September')).toBeVisible();
  });

  test('first run and the offline brain', async ({ page }) => {
    await msw(page, { seed: '0', brain: 'offline' });
    await page.goto('/');
    await expect(page.getByTestId('first-run')).toBeVisible();
    await expect(page.getByTestId('first-run').getByRole('listitem')).toHaveCount(5);
    await expect(page.getByTestId('first-run').getByRole('link', { name: 'Add documents' })).toHaveAttribute('href', '/intake');
    await expect(page.getByText('Mona’s brain is offline')).toBeVisible();
    await expect(entry(page)).toBeDisabled();
    await expect(page.getByRole('link', { name: 'Mona is offline' })).toBeVisible();
    expect(await serious(page)).toEqual([]);
  });

  test('Home at 390: one column, the entry above the tab bar, nothing wider than the screen', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await msw(page);
    const problems = watchConsole(page);
    await page.goto('/');
    await expect(page.getByTestId('mona-brief')).toBeVisible();
    await expect(page.getByTestId('home-ingestion')).toBeAttached();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
    const boxes = await Promise.all(['home-review', 'home-due', 'home-activity', 'home-ingestion'].map((id) => page.getByTestId(id).boundingBox()));
    expect(new Set(boxes.map((b) => Math.round(b!.x))).size).toBe(1);
    const entryBox = (await page.getByTestId('chat-entry').boundingBox())!;
    const tabBox = (await nav(page).boundingBox())!;
    expect(entryBox.y + entryBox.height).toBeLessThanOrEqual(tabBox.y + 1);
    await expect(nav(page).getByRole('link', { name: 'Home' })).toHaveAttribute('aria-current', 'page');
    expect(await serious(page)).toEqual([]);
    expect(problems).toEqual([]);
  });
});

test.describe('auto-lock', () => {
  test('a locked session sends the next request to /unlock?next=, and unlocking returns there', async ({ page }) => {
    await msw(page);
    await page.goto('/rules');
    await expect(page.getByTestId('rules-table')).toBeVisible();
    await page.evaluate(() => (window as unknown as { __mock: { account: { idleOut(): void } } }).__mock.account.idleOut());
    await nav(page).getByRole('link', { name: 'Review queue' }).click();
    await expect(page).toHaveURL(/\/unlock\?next=%2Freview$/);
    await expect(page.getByRole('navigation')).toHaveCount(0);
    await unlock(page);
    await expect(page).toHaveURL(/\/review$/);
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Review queue');
  });

  test('idle past the auto-lock minutes locks at the next poll; activity and a heartbeat would have kept it', async ({ page }) => {
    await page.clock.install({ time: new Date('2026-10-01T09:00:00') });
    await msw(page, { autoLock: '1' });
    await page.goto('/rules');
    await expect(page.getByTestId('rules-table')).toBeVisible();
    await page.clock.fastForward('02:00');
    await expect(page).toHaveURL(/\/unlock\?next=%2Frules$/);
    await unlock(page);
    await expect(page).toHaveURL(/\/rules$/);
  });

  test('the Lock item in the account menu locks and returns after unlocking', async ({ page }) => {
    await msw(page);
    await page.goto('/settings');
    await page.getByRole('button', { name: /Léa Marchand/ }).click();
    await page.getByRole('menuitem', { name: 'Lock' }).click();
    await expect(page).toHaveURL(/\/unlock\?next=%2Fsettings$/);
    await unlock(page);
    await expect(page).toHaveURL(/\/settings$/);
  });
});

test.describe('rules', () => {
  test('lists the rules, toggles one off and a draft on, and shows what Mona learned today', async ({ page }) => {
    await msw(page);
    await page.goto('/rules');
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Rules');
    await expect(page.getByText(/^11 rules, 9 on\./)).toBeVisible();
    const row = (name: string) => page.getByTestId('rule-row').filter({ hasText: name });
    await expect(row('Martin Supplies invoices')).toContainText('Built in');
    await expect(row('Banque Lumière statements, personal')).toContainText('3 · check');
    await expect(row('Banque Lumière: Atelier statements')).toContainText('Draft');

    await row('Martin Supplies invoices').getByRole('switch').click();
    await expect(row('Martin Supplies invoices').getByRole('switch')).toHaveAttribute('aria-checked', 'false');
    await expect(page.getByText(/^11 rules, 8 on\./)).toBeVisible();
    await row('Banque Lumière: Atelier statements').getByRole('switch').click();
    await expect(row('Banque Lumière: Atelier statements').getByRole('switch')).toHaveAttribute('aria-checked', 'true');
    await expect(row('Banque Lumière: Atelier statements')).not.toContainText('Draft');
    await expect(page.getByText(/^11 rules, 9 on\./)).toBeVisible();

    const learned = page.getByTestId('learned-panel');
    await expect(learned).toContainText('What Mona learned today');
    await expect(learned.getByRole('link')).toHaveCount(2);

    await page.getByRole('searchbox', { name: 'Find a rule' }).fill('laval');
    await expect(page.getByTestId('rule-row')).toHaveCount(1);
    await row('SIE Laval tax notices').getByRole('link').click();
    await expect(page).toHaveURL(/\/rules\/rul_/);
    await expect(page.getByTestId('rule-detail')).toContainText('When the counterparty is SIE Laval.');
    await page.getByLabel('Name', { exact: true }).fill('SIE Laval notices');
    await page.getByRole('button', { name: 'Save name' }).click();
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('SIE Laval notices');
  });
});

test.describe('entities and categories', () => {
  test('entity cards: masked accounts, fiscal year, sub-units, and Visitors shown as such', async ({ page }) => {
    await msw(page);
    await page.goto('/entities');
    await expect(page.getByTestId('entity-card')).toHaveCount(5);
    const cabinet = page.getByTestId('entity-card').filter({ hasText: 'Cabinet Marchand' });
    await expect(cabinet).toContainText('•••• 4471');
    await expect(cabinet).toContainText('31 December');
    await expect(cabinet).toContainText('Laval (main)');
    await expect(page.getByTestId('entity-card').filter({ hasText: 'Atelier Numérique' })).toContainText('30 June');
    const visitors = page.locator('[data-kind="visitors"]');
    await expect(visitors).toHaveCount(1);
    await expect(visitors).toContainText('deleted after 24 hours');
    await expect(page.getByTestId('entity-card').last()).toHaveAttribute('data-kind', 'visitors');
    await expect(page.locator('[data-kind="personal"]')).toContainText('Personal documents stay out of Telegram');
  });

  test('a category template edit: tokens, live preview, save, and the 422 path', async ({ page }) => {
    await msw(page);
    await page.goto('/entities');
    await page.getByRole('tab', { name: /Categories/ }).click();
    await expect(page).toHaveURL(/\/entities\/categories\/invoices$/);
    await page.getByRole('treeitem', { name: /Tax, 11 documents/ }).click();
    await expect(page).toHaveURL(/\/entities\/categories\/tax$/);
    const editor = page.getByTestId('category-editor');
    const path = editor.getByRole('textbox', { name: 'Path template' });
    const preview = page.getByTestId('template-preview');
    await expect(preview).toContainText('Cabinet Marchand / Appels de paiement / 2026');

    await path.fill('{entity}/{fy} {entity}/{category}');
    await expect(preview).toContainText('Cabinet Marchand / 2025 Cabinet Marchand / Appels de paiement');
    await editor.getByRole('group', { name: 'Tokens' }).first().getByRole('button', { name: 'Insert {counterparty}' }).click();
    await expect(path).toHaveValue('{entity}/{fy} {entity}/{category}{counterparty}');
    await path.fill('{entity}/{fy} {entity}/{category}');
    await editor.getByRole('button', { name: 'Save changes' }).click();
    await expect(toast(page).getByText('Category saved')).toBeVisible();
    await expect(editor.getByRole('button', { name: 'Save changes' })).toBeDisabled();

    const bad = page.waitForResponse((r) => r.url().includes('/api/categories/tax') && r.request().method() === 'PATCH' && r.status() === 422);
    await path.fill('{entity}/{nope}');
    await editor.getByRole('button', { name: 'Save changes' }).click();
    await bad;
    const error = editor.getByTestId('template-error').first();
    await expect(error).toContainText('The template has a mistake at character 10.');
    await expect(error).toContainText('Unknown token.');
    await expect(path).toHaveAttribute('aria-invalid', 'true');
    await expect(preview).toContainText('No preview while the template has a mistake.');
    await path.fill('{entity}/{category}');
    await expect(editor.getByTestId('template-error')).toHaveCount(0);
  });
});

test.describe('settings', () => {
  test('thresholds save, bad values are refused in words, and the language switches at once', async ({ page }) => {
    await msw(page);
    await page.goto('/settings#thresholds');
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Settings');
    const section = page.getByTestId('settings-thresholds');
    await expect(section).toBeInViewport();
    const high = section.getByLabel('Files on her own from (%)');
    const low = section.getByLabel('Asks you below (%)');
    const save = section.getByRole('button', { name: 'Save' });
    await expect(save).toBeDisabled();
    await low.fill('90');
    await expect(section.getByText('The low threshold must be under the high one.')).toBeVisible();
    await expect(save).toBeDisabled();
    await low.fill('70');
    await high.fill('95');
    await save.click();
    await expect(toast(page).getByText('Settings saved')).toBeVisible();
    await expect(save).toBeDisabled();
    await nav(page).getByRole('link', { name: 'Home' }).click();
    await nav(page).getByRole('link', { name: 'Settings' }).click();
    await expect(page.getByTestId('settings-thresholds').getByLabel('Files on her own from (%)')).toHaveValue('95');
    await expect(page.getByTestId('settings-thresholds').getByLabel('Asks you below (%)')).toHaveValue('70');

    await page.getByRole('radio', { name: 'Français' }).click();
    await expect(page.locator('html')).toHaveAttribute('lang', 'fr');
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Paramètres');
    await page.getByRole('radio', { name: 'Română' }).click();
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Setări');
  });

  test('profile and lock: save the auto-lock minutes, change the password; status tiles and privacy; no recovery key or theme', async ({ page }) => {
    await msw(page);
    await page.goto('/settings');
    const profile = page.getByTestId('settings-profile');
    await profile.getByLabel('Lock after (minutes)').fill('30');
    await profile.getByRole('button', { name: 'Save' }).click();
    await expect(toast(page).getByText('Settings saved')).toBeVisible();

    await profile.getByRole('button', { name: 'Change password' }).click();
    const dialog = page.getByRole('dialog');
    await dialog.getByLabel('Current password').fill(PASSWORD);
    await dialog.getByLabel('New password', { exact: true }).fill('a new password');
    await dialog.getByLabel('New password again').fill('a new password');
    await dialog.getByRole('button', { name: 'Change password' }).click();
    await expect(toast(page).getByText('Password changed')).toBeVisible();
    await expect(dialog).toHaveCount(0);

    await expect(page.getByTestId('status-tile')).toHaveCount(5);
    await expect(page.getByTestId('settings-status')).toContainText('Q4_K_XL');
    await expect(page.getByTestId('flow-stays')).toContainText('Your documents and their folders');
    await expect(page.getByTestId('flow-telegram')).toContainText('Passes through Telegram');
    await expect(page.getByTestId('flow-export')).toContainText('Mona never sends anything by herself');
    await expect(page.getByTestId('about-web-version')).toContainText(/Mona \d+\.\d+\.\d+/);
    await expect(page.getByText(/recovery key|theme|dark/i)).toHaveCount(0);
  });
});

test.describe('no console errors and no serious axe violations', () => {
  const ROUTES = ['/', '/rules', '/entities', '/entities/categories/invoices', '/settings'];
  for (const lng of ['en', 'fr', 'ro'] as const) {
    test(`Home, rules, entities, categories and settings in ${lng}`, async ({ page }) => {
      await msw(page, { locale: lng });
      const problems = watchConsole(page);
      for (const path of ROUTES) {
        await page.goto(path);
        await expect(page.locator('html')).toHaveAttribute('lang', lng);
        await page.waitForSelector('h1');
        await page.waitForTimeout(700);
        expect(await serious(page), path).toEqual([]);
      }
      expect(problems).toEqual([]);
    });
  }

  test('rule detail, the unlock page, and the password dialog', async ({ page }) => {
    await msw(page, { locked: '1' });
    const problems = watchConsole(page);
    await page.goto('/unlock');
    await expect(page.getByLabel('Password')).toBeVisible();
    expect(await serious(page)).toEqual([]);
    await unlock(page);
    await nav(page).getByRole('link', { name: 'Rules' }).click();
    await page.getByTestId('rule-row').first().getByRole('link').click();
    await expect(page.getByTestId('rule-detail')).toBeVisible();
    expect(await serious(page)).toEqual([]);
    await page.getByRole('link', { name: 'Settings' }).click();
    await page.getByRole('button', { name: 'Change password' }).click();
    await expect(page.getByRole('dialog')).toBeVisible();
    await page.waitForTimeout(600);
    expect(await serious(page)).toEqual([]);
    expect(problems).toEqual([]);
  });
});
