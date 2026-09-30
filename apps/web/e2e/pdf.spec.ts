import { expect, test, type Page } from '@playwright/test';

async function openViewer(page: Page) {
  await page.goto('/dev/pdf');
  const viewer = page.frameLocator('iframe[title="pdf.js"]');
  await expect(viewer.locator('.textLayer').first()).toContainText('Montant à payer');
  return viewer;
}

test('finds the phrase through the URL hash', async ({ page }) => {
  const viewer = await openViewer(page);
  await page.getByRole('button', { name: 'Find via URL hash' }).click();
  await expect(viewer.locator('.textLayer .highlight')).toContainText('284,00');
});

test('finds the phrase through the pdf.js event bus', async ({ page }) => {
  const viewer = await openViewer(page);
  await page.getByRole('button', { name: 'Find via event bus' }).click();
  await expect(viewer.locator('.textLayer .highlight')).toContainText('284,00');
});
