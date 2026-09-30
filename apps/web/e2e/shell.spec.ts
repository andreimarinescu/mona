import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';

const health = { status: 'ok', db: 'ok', version: '0.1.0' };

test.beforeEach(async ({ page }) => {
  await page.route('**/api/health', (route) => route.fulfill({ json: health }));
});

function watchConsole(page: Page): string[] {
  const problems: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error' || msg.type() === 'warning') problems.push(`${msg.type()}: ${msg.text()}`);
  });
  page.on('pageerror', (err) => problems.push(`pageerror: ${err.message}`));
  return problems;
}

const nav = (page: Page) => page.getByRole('navigation');

const NAV: [string, string, string][] = [
  ['Home', '/', 'Home'],
  ['Chat', '/chat', 'Chat'],
  ['Intake', '/intake', 'Intake'],
  ['Review queue', '/review', 'Review queue'],
  ['Archive', '/archive', 'Archive'],
  ['Rules', '/rules', 'Rules'],
  ['Entities & taxonomy', '/entities', 'Entities & taxonomy'],
  ['Activity log', '/activity', 'Activity log'],
  ['Settings', '/settings', 'Settings'],
];

const PARAM_ROUTES: [string, string, string?][] = [
  ['/chat/cnv_01j9zq3k8e6y4v2m7c5r1t0b9a', 'Chat', 'cnv_01j9zq3k8e6y4v2m7c5r1t0b9a'],
  ['/review/doc_01j9zq3k8e6y4v2m7c5r1t0b9a', 'Review queue', 'doc_01j9zq3k8e6y4v2m7c5r1t0b9a'],
  ['/archive/folders/Cabinet%20Marchand/2026', 'Archive'],
  ['/documents/doc_01j9zq3k8e6y4v2m7c5r1t0b9a', 'Document', 'doc_01j9zq3k8e6y4v2m7c5r1t0b9a'],
  ['/rules/rul_01j9zq3k8e6y4v2m7c5r1t0b9a', 'Rules', 'rul_01j9zq3k8e6y4v2m7c5r1t0b9a'],
  ['/entities/categories/tax', 'Entities & taxonomy', 'tax'],
];

test.describe('routes', () => {
  test('every nav item leads to its screen, with the current one marked', async ({ page }) => {
    await page.goto('/');
    for (const [label, path, title] of NAV) {
      await nav(page).getByRole('link', { name: label }).click();
      await expect(page).toHaveURL(new RegExp(`${path === '/' ? '/$' : `${path}$`}`));
      await expect(page.getByRole('heading', { level: 1 })).toHaveText(title);
      await expect(nav(page).getByRole('link', { name: label })).toHaveAttribute('aria-current', 'page');
      await expect(nav(page).locator('a[aria-current="page"]')).toHaveCount(1);
    }
  });

  test('routes with params render in the shell', async ({ page }) => {
    for (const [path, title, reference] of PARAM_ROUTES) {
      await page.goto(path);
      await expect(page.getByRole('heading', { level: 1 })).toHaveText(title);
      await expect(nav(page)).toBeVisible();
      if (reference) await expect(page.getByTestId('reference')).toContainText(reference);
    }
  });

  test('/unlock renders outside the shell', async ({ page }) => {
    await page.goto('/unlock');
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Unlock Mona');
    await expect(page.getByRole('navigation')).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Ask Mona' })).toHaveCount(0);
  });

  test('/reports is cut: it 404s and is not in the nav', async ({ page }) => {
    await page.goto('/reports');
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Page not found');
    await expect(page.getByRole('link', { name: /reports/i })).toHaveCount(0);
  });

  test('the entity scope switcher feeds app state', async ({ page }) => {
    await page.goto('/archive');
    await expect(page.getByTestId('scope-line')).toHaveText('Showing: All entities');
    await page.getByLabel('Showing').selectOption({ label: 'SCI Les Tilleuls' });
    await expect(page.getByTestId('scope-line')).toHaveText('Showing: SCI Les Tilleuls');
    await nav(page).getByRole('link', { name: 'Rules' }).click();
    await expect(page.getByTestId('scope-line')).toHaveText('Showing: SCI Les Tilleuls');
  });
});

test.describe('language and theme', () => {
  test('html is light, English, with no theme control', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('html')).toHaveAttribute('lang', 'en');
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
    await expect(page.getByText(/theme|dark/i)).toHaveCount(0);
    await expect(page.getByRole('radiogroup')).toHaveCount(0);
  });

  for (const [lng, home, settings] of [
    ['fr', 'Accueil', 'Paramètres'],
    ['ro', 'Acasă', 'Setări'],
  ]) {
    test(`the settings language (${lng}) sets <html lang> and the nav`, async ({ page }) => {
      await page.addInitScript((l) => localStorage.setItem('mona.stub.language', l), lng);
      await page.goto('/');
      await expect(page.locator('html')).toHaveAttribute('lang', lng!);
      await expect(nav(page).getByRole('link', { name: home })).toBeVisible();
      await expect(nav(page).getByRole('link', { name: settings })).toBeVisible();
      await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
    });
  }
});

test.describe('system status line', () => {
  test('shows the computer and queue when health is ok', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('link', { name: /On this computer · queue 0/ })).toHaveAttribute('href', '/settings#status');
  });

  test('shows "Mona is offline" when health fails', async ({ page }) => {
    await page.route('**/api/health', (route) => route.fulfill({ status: 503, json: { ...health, status: 'degraded', db: 'error' } }));
    await page.goto('/');
    await expect(page.getByRole('link', { name: 'Mona is offline' })).toBeVisible();
  });
});

test.describe('chat panel', () => {
  test('opens from Ask Mona, is non-modal, and Esc returns focus to the button', async ({ page }) => {
    await page.goto('/review');
    const ask = page.getByRole('button', { name: 'Ask Mona' });
    await ask.click();
    const panel = page.locator('[role="complementary"][aria-label="Mona"]');
    await expect(panel).toBeVisible();
    expect((await panel.boundingBox())!.width).toBe(460);
    await expect(panel.getByTestId('page-context')).toHaveText('Mona can see: Review queue');
    await expect(panel.getByRole('textbox', { name: 'Ask Mona…' })).toBeFocused();
    await nav(page).getByRole('link', { name: 'Archive' }).click();
    await expect(page).toHaveURL(/\/archive$/);
    await expect(panel.getByTestId('page-context')).toHaveText('Mona can see: Archive');
    await page.getByRole('button', { name: 'Ask Mona' }).focus();
    await page.keyboard.press('Escape');
    await expect(panel).toBeHidden();
    await expect(ask).toBeFocused();
  });

  test('"/" opens it off Home, Esc closes it and restores focus', async ({ page }) => {
    await page.goto('/rules');
    const link = nav(page).getByRole('link', { name: 'Activity log' });
    await link.focus();
    await page.keyboard.press('/');
    const panel = page.locator('[role="complementary"][aria-label="Mona"]');
    await expect(panel).toBeVisible();
    await expect(panel.getByRole('textbox', { name: 'Ask Mona…' })).toBeFocused();
    await page.keyboard.press('Escape');
    await expect(panel).toBeHidden();
    await expect(link).toBeFocused();
  });

  test('"/" does nothing inside a text field', async ({ page }) => {
    await page.goto('/rules');
    await page.getByRole('button', { name: 'Ask Mona' }).click();
    const composer = page.getByRole('textbox', { name: 'Ask Mona…' });
    await composer.fill('a');
    await page.keyboard.press('/');
    await expect(composer).toHaveValue('a/');
    await expect(page.locator('[role="complementary"][aria-label="Mona"]')).toBeVisible();
  });

  test('"/" opens the panel on Home when no Home entry exists', async ({ page }) => {
    await page.goto('/');
    await page.locator('body').click({ position: { x: 700, y: 400 } });
    await page.keyboard.press('/');
    await expect(page.locator('[role="complementary"][aria-label="Mona"]')).toBeVisible();
  });

  test('stays open, with its thread and conversation id, across navigation', async ({ page }) => {
    const bodies: Record<string, unknown>[] = [];
    await page.route('**/api/chat', async (route) => {
      bodies.push(route.request().postDataJSON());
      const chunks = [
        { type: 'start', messageId: `msg_${bodies.length}`, messageMetadata: { conversationId: 'cnv_shell' } },
        { type: 'start-step' },
        { type: 'text-start', id: 't1' },
        { type: 'text-delta', id: 't1', delta: 'Hello from Mona' },
        { type: 'text-end', id: 't1' },
        { type: 'finish-step' },
        { type: 'finish', finishReason: 'stop' },
      ];
      await route.fulfill({
        status: 200,
        headers: { 'content-type': 'text/event-stream', 'x-vercel-ai-ui-message-stream': 'v1' },
        body: chunks.map((c) => `data: ${JSON.stringify(c)}\n\n`).join('') + 'data: [DONE]\n\n',
      });
    });
    await page.goto('/intake');
    await page.getByRole('button', { name: 'Ask Mona' }).click();
    const panel = page.locator('[role="complementary"][aria-label="Mona"]');
    await panel.getByRole('textbox', { name: 'Ask Mona…' }).fill('first');
    await panel.getByRole('button', { name: 'Send' }).click();
    await expect(panel.getByText('Hello from Mona')).toBeVisible();

    await nav(page).getByRole('link', { name: 'Rules' }).click();
    await nav(page).getByRole('link', { name: 'Settings' }).click();
    await expect(panel).toBeVisible();
    await expect(panel.getByText('Hello from Mona')).toBeVisible();

    await panel.getByRole('textbox', { name: 'Ask Mona…' }).fill('second');
    await panel.getByRole('button', { name: 'Send' }).click();
    await expect.poll(() => bodies.length).toBe(2);
    expect(bodies[0]).toMatchObject({ message: 'first', pageContext: { route: '/intake', summary: 'Intake' }, locale: 'en' });
    expect(bodies[1]).toMatchObject({
      conversationId: 'cnv_shell',
      message: 'second',
      pageContext: { route: '/settings', summary: 'Settings' },
    });
  });
});

test.describe('skip link', () => {
  test('is the first tab stop and moves focus to the page', async ({ page }) => {
    await page.goto('/review');
    await page.keyboard.press('Tab');
    const skip = page.getByRole('link', { name: 'Skip to content' });
    await expect(skip).toBeFocused();
    await expect(skip).toBeInViewport();
    await page.keyboard.press('Enter');
    await expect(page.locator('main')).toBeFocused();
    await expect(page).toHaveURL(/\/review$/);
  });

  test('is the first tab stop on /unlock too', async ({ page }) => {
    await page.goto('/unlock');
    await page.keyboard.press('Tab');
    await expect(page.getByRole('link', { name: 'Skip to content' })).toBeFocused();
  });
});

test.describe('mobile (390 wide)', () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test('tab bar replaces the sidebar, and More holds the four desk screens', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('complementary', { name: 'Sidebar' })).toBeHidden();
    const tabs = nav(page);
    await expect(tabs).toBeVisible();
    await expect(tabs.getByRole('link')).toHaveCount(4);
    for (const name of ['Home', /^Review/, 'Chat', 'Archive']) await expect(tabs.getByRole('link', { name })).toBeVisible();
    await expect(tabs.getByRole('link', { name: /^Review/ })).toContainText('6');
    await tabs.getByRole('button', { name: 'More' }).click();
    const items = page.getByRole('menu', { name: 'More screens' }).getByRole('menuitem');
    await expect(items).toHaveText(['Rules', 'Entities & taxonomy', 'Activity log', 'Settings']);
    await items.filter({ hasText: 'Activity log' }).click();
    await expect(page).toHaveURL(/\/activity$/);
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Activity log');
  });
});

test.describe('toasts', () => {
  type Hook = { toasts: { push: (t: Record<string, unknown>) => void } };
  const push = (page: Page, toast: Record<string, unknown>) =>
    page.evaluate((t) => (window as unknown as { __mona: Hook }).__mona.toasts.push(t), toast);

  test('group, cap at three, and sit left of the open chat panel', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/');
    await page.evaluate(() => {
      const { toasts } = (window as unknown as { __mona: Hook }).__mona;
      for (let i = 0; i < 12; i++) toasts.push({ key: 'filed', message: 'toast.filed', from: 'mona', undo: () => {} });
      for (const key of ['b', 'c', 'd']) toasts.push({ key, message: 'toast.failed', tone: 'neutral' });
    });
    const region = page.getByTestId('toast-region');
    await expect(region.getByText('Filed 12 documents')).toBeVisible();
    await expect(region.getByRole('status')).toHaveCount(3);
    const closed = (await region.boundingBox())!;
    expect(closed.x + closed.width).toBeGreaterThan(1440 - 40);

    await page.getByRole('button', { name: 'Ask Mona' }).click();
    const panel = await page.locator('[role="complementary"][aria-label="Mona"]').boundingBox();
    await expect.poll(async () => { const b = (await region.boundingBox())!; return b.x + b.width <= panel!.x; }).toBe(true);
  });

  test('a danger toast is an alert that stays until dismissed', async ({ page }) => {
    await page.goto('/');
    await push(page, { key: 'err', message: 'toast.failed', tone: 'danger' });
    const alert = page.getByRole('alert');
    await expect(alert).toHaveText(/Something went wrong/);
    await page.waitForTimeout(7_000);
    await expect(alert).toBeVisible();
    await alert.getByRole('button', { name: 'Close' }).click();
    await expect(alert).toHaveCount(0);
  });
});

test.describe('console and accessibility', () => {
  const ROUTES = ['/', ...NAV.map(([, p]) => p), ...PARAM_ROUTES.map(([p]) => p), '/unlock', '/reports'];

  test('no console errors or warnings on any route', async ({ page }) => {
    const problems = watchConsole(page);
    for (const path of [...new Set(ROUTES)]) {
      await page.goto(path);
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    }
    await page.goto('/');
    await page.getByRole('button', { name: 'Ask Mona' }).click();
    await expect(page.locator('[role="complementary"][aria-label="Mona"]')).toBeVisible();
    await page.getByRole('button', { name: /Léa Marchand/ }).click();
    await expect(page.getByRole('menuitem', { name: 'Lock' })).toBeVisible();
    expect(problems).toEqual([]);
  });

  test('no console errors or warnings at 390 wide', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const problems = watchConsole(page);
    for (const path of ['/', '/review', '/unlock']) {
      await page.goto(path);
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    }
    await page.goto('/');
    await nav(page).getByRole('button', { name: 'More' }).click();
    await expect(page.getByRole('menu')).toBeVisible();
    expect(problems).toEqual([]);
  });

  async function serious(page: Page) {
    const { violations } = await new AxeBuilder({ page }).analyze();
    return violations.filter((v) => v.impact === 'serious' || v.impact === 'critical').map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(' | ')}`);
  }

  for (const path of [...new Set(ROUTES)]) {
    test(`axe: no serious or critical violations on ${path}`, async ({ page }) => {
      await page.goto(path);
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
      expect(await serious(page)).toEqual([]);
    });
  }

  test('axe: panel open, user menu open, French, and mobile with More open', async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem('mona.stub.language', 'fr'));
    await page.goto('/');
    await page.getByRole('button', { name: 'Demander à Mona' }).click();
    await expect(page.locator('[role="complementary"][aria-label="Mona"]')).toBeVisible();
    expect(await serious(page)).toEqual([]);
    await page.getByRole('button', { name: /Léa Marchand/ }).click();
    await expect(page.getByRole('menu')).toBeVisible();
    expect(await serious(page)).toEqual([]);
    await page.keyboard.press('Escape');
    await page.keyboard.press('Escape');
    await page.setViewportSize({ width: 390, height: 844 });
    await nav(page).getByRole('button', { name: 'Plus' }).click();
    await expect(page.getByRole('menu')).toBeVisible();
    expect(await serious(page)).toEqual([]);
  });
});
