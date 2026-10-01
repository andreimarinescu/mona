import { test, type Page } from '@playwright/test';

const dir = process.env.SHOTS_DIR;
const PDF = (text: string) => Buffer.from(`%PDF-1.4\n${text}\n%%EOF`);

test.describe('screenshots at 1440', () => {
  test.skip(!dir, 'set SHOTS_DIR to write the screenshots');
  test.use({ viewport: { width: 1440, height: 1024 } });

  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('mona.msw', '1');
      localStorage.setItem('mona.msw.step', '700');
    });
  });

  const shot = (page: Page, name: string) => page.screenshot({ path: `${dir}/${name}.png` });

  test('intake, mid-batch and finished', async ({ page }) => {
    await page.goto('/intake');
    await page.getByTestId('file-input').setInputFiles(
      ['invoice_a.pdf', 'invoice_b.pdf', 'scan_c.pdf', 'blurry_d.pdf', 'invoice_e.pdf', 'invoice_f.pdf'].map((name) => ({ name, mimeType: 'application/pdf', buffer: PDF(name) })),
    );
    await page.getByTestId('batch-progress').waitFor();
    await page.waitForTimeout(2600);
    await shot(page, 'intake-running');
    await page.getByTestId('batch-summary').waitFor({ timeout: 20_000 });
    await page.getByText('Mona has 2 questions about this batch').waitFor({ timeout: 10_000 });
    await page.waitForTimeout(400);
    await shot(page, 'intake-done');
  });

  test('review and the correction prompt', async ({ page }) => {
    await page.goto('/review');
    await page.getByTestId('review-detail').waitFor();
    await shot(page, 'review');
    const detail = page.getByTestId('review-detail');
    await detail.getByLabel('Entity').selectOption({ label: 'Cabinet Marchand' });
    await detail.getByRole('button', { name: 'Correct and file' }).click();
    await page.getByTestId('scope-prompt').getByRole('radio', { name: /Every document like this/ }).check();
    await page.getByTestId('rule-preview').waitFor();
    await page.waitForTimeout(400);
    await page.screenshot({ path: `${dir}/review-correction.png`, fullPage: true });
  });

  test('activity', async ({ page }) => {
    await page.goto('/review');
    await page.getByTestId('review-detail').waitFor();
    await page.keyboard.press('Enter');
    await page.getByTestId('toast-region').getByText('Filed 1 document').waitFor();
    await page.getByRole('navigation').getByRole('link', { name: 'Activity log' }).click();
    await page.locator('li[data-group-id]').first().getByRole('button', { name: 'Show the changes in this group' }).click();
    await page.waitForTimeout(400);
    await shot(page, 'activity');
  });

  test('mobile review at 390', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/review');
    await page.getByTestId('review-item').first().waitFor();
    await shot(page, 'review-mobile-list');
    await page.getByRole('link', { name: 'Nordtel invoice, September 2026' }).click();
    await page.getByTestId('review-detail').waitFor();
    await shot(page, 'review-mobile-detail');
  });

  async function showcase(page: Page) {
    await page.waitForFunction(() => '__mock' in window);
    return page.evaluate(() => {
      const world = (window as unknown as { __mock: { docs: Map<string, { summary: { id: string; title: string } }> } }).__mock;
      return [...world.docs.values()].find((d) => d.summary.title === 'Call for contributions, Q3 2026')!.summary.id;
    });
  }

  test('archive search, folders, viewer with a highlight, and the export dialog', async ({ page }) => {
    await page.goto('/archive?q=URSSAF');
    await page.getByTestId('results-table').waitFor();
    await page.getByRole('radio', { name: /Cabinet Marchand/ }).check();
    await page.getByLabel('Category').selectOption({ label: 'Tax · 9' });
    await page.getByLabel('Minimum amount').fill('1000');
    await page.getByLabel('Minimum amount').blur();
    await page.getByTestId('active-filters').waitFor();
    await page.waitForTimeout(500);
    await shot(page, 'archive-search');

    await page.goto('/archive/folders/Cabinet%20Marchand/2026%20Cabinet%20Marchand/Imp%C3%B4ts/Appels%20de%20paiement');
    await page.getByTestId('folder-contents').getByRole('row').nth(1).waitFor();
    await page.waitForTimeout(500);
    await shot(page, 'archive-folders');

    const id = await showcase(page);
    await page.goto(`/documents/${id}`);
    const frame = page.frameLocator('iframe[data-testid="pdf-frame"]');
    await frame.locator('.textLayer').first().waitFor();
    await page.getByTestId('side-panel').locator('[data-field="amount"]').getByRole('button', { name: /Show on page/ }).click();
    await frame.locator('.textLayer .highlight').first().waitFor();
    await page.waitForTimeout(600);
    await shot(page, 'viewer-highlight');

    await page.goto('/archive');
    await page.getByTestId('results-table').waitFor();
    await page.getByRole('button', { name: 'Export for accountant…' }).click();
    await page.getByTestId('export-included').waitFor();
    await page.waitForTimeout(500);
    await shot(page, 'export-dialog');
  });
});

test.describe('chat screenshots at 1440 (p3, p4, p5) and 390', () => {
  test.skip(!dir, 'set SHOTS_DIR to write the screenshots');
  test.use({ viewport: { width: 1440, height: 1024 } });

  const chatShot = (page: Page, name: string) => page.screenshot({ path: `${dir}/${name}.png` });
  const composer = (scope: Page | ReturnType<Page['locator']>) => scope.getByRole('textbox', { name: 'Write to Mona…' });
  async function ask(scope: Page | ReturnType<Page['locator']>, page: Page, text: string) {
    const replies = (scope === page ? page.locator('main') : scope).locator('[data-role="assistant"]');
    const before = await replies.count();
    await composer(scope).fill(text);
    await composer(scope).press('Enter');
    await replies.nth(before).waitFor();
    await (scope === page ? page.locator('main') : scope).locator('[data-chat-status="ready"]').waitFor();
  }

  test('p3 and p4: the debrief in the chat page, then rule previews, a draft and the language switch', async ({ page, context }) => {
    await context.grantPermissions(['clipboard-read', 'clipboard-write']);
    await page.addInitScript(() => {
      localStorage.setItem('mona.msw', '1');
      localStorage.setItem('mona.msw.step', '150');
      localStorage.setItem('mona.msw.chatDelay', '10');
    });
    await page.goto('/intake');
    await page.getByTestId('file-input').setInputFiles(['scan_per_1.pdf', 'scan_vie_1.pdf', 'scan_per_2.pdf', 'invoice_x.pdf'].map((name) => ({ name, mimeType: 'application/pdf', buffer: PDF(name) })));
    await page.getByRole('button', { name: 'Answer now' }).click({ timeout: 20_000 });
    const panel = page.locator('[role="complementary"][aria-label="Mona"]');
    await panel.locator('[data-card="interview"]').waitFor();
    await page.locator('[data-chat-status="ready"]').waitFor();
    await ask(panel, page, 'How much did we pay last year?');
    await panel.getByRole('button', { name: 'Open in Chat' }).click();
    await page.locator('main [data-card="interview"]').waitFor();
    await page.locator('main [data-card="interview"]').scrollIntoViewIfNeeded();
    await page.waitForTimeout(400);
    await chatShot(page, 'chat-p3-interview');

    await page.locator('main [data-card="interview"]').getByRole('button', { name: 'Personal: split retirement and life insurance' }).click();
    await page.locator('main [data-card="rulePreview"]').nth(1).waitFor();
    await page.locator('main [data-card="rulePreview"]').first().scrollIntoViewIfNeeded();
    await page.waitForTimeout(400);
    await chatShot(page, 'chat-p4-previews');
    await ask(page, page, 'Pouvez-vous rédiger une réponse pour demander un échéancier ?');
    await page.locator('main [data-card="draft"] [data-testid="draft-body"]').waitFor({ timeout: 10_000 });
    await page.waitForTimeout(400);
    await chatShot(page, 'chat-p4-draft-language');
  });

  test('p5: the panel over the archive, with a deadline and a live answer', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('mona.msw', '1');
      localStorage.setItem('mona.msw.chatDelay', '70');
    });
    await page.goto('/archive?q=URSSAF');
    await page.getByTestId('results-table').waitFor();
    await page.getByRole('button', { name: 'Ask Mona', exact: true }).click();
    const panel = page.locator('[role="complementary"][aria-label="Mona"]');
    await ask(panel, page, 'When is the next payment due, and how much?');
    await composer(panel).fill('And the same quarter last year? How much did we pay?');
    await composer(panel).press('Enter');
    await panel.locator('[data-testid="thinking"][data-live="true"]').waitFor();
    await page.waitForTimeout(250);
    await chatShot(page, 'chat-p5-panel');
  });

  test('Chat at 390', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.addInitScript(() => {
      localStorage.setItem('mona.msw', '1');
      localStorage.setItem('mona.msw.chatDelay', '10');
    });
    await page.goto('/chat');
    await ask(page, page, "What's due this month?");
    await page.waitForTimeout(300);
    await chatShot(page, 'chat-390');
  });
});
