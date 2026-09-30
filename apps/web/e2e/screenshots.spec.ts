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
});
