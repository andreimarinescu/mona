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
