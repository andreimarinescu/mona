import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { expect, test } from '@playwright/test';

// The real stack, no MSW: E2E_BASE_URL=<web> MONA_SYNTHETIC_DIR=<demo-data/synthetic> MONA_OWNER_PASSWORD=<the seeded password>.
const dir = process.env.MONA_SYNTHETIC_DIR;
test.skip(!dir || !process.env.E2E_BASE_URL, 'live intake not requested (E2E_BASE_URL and MONA_SYNTHETIC_DIR)');
test.describe.configure({ timeout: 240_000 });

const FILES = ['sie-avis-mise-en-recouvrement.pdf', 'devis-orthodontie.pdf', 'oxyleo-elements-preparatoires.pdf'];

test('drop 3 synthetic PDFs on /intake: progress, then the summary of the real batch', async ({ page }) => {
  const problems: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') problems.push(msg.text());
  });
  page.on('pageerror', (err) => problems.push(err.message));
  const unlock = await page.request.post('/api/auth/unlock', { data: { password: process.env.MONA_OWNER_PASSWORD } });
  expect(unlock.ok()).toBe(true);

  const run = `% e2e ${Date.now()}\n`;
  await page.goto('/intake');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Intake');
  await page.getByTestId('file-input').setInputFiles(
    FILES.map((name) => ({ name, mimeType: 'application/pdf', buffer: Buffer.concat([readFileSync(join(dir!, name)), Buffer.from(run)]) })),
  );

  await expect(page.getByTestId('batch-progress')).toBeVisible();
  await expect(page.getByRole('progressbar')).toBeVisible();
  const rows = page.getByRole('row').filter({ hasText: /\.pdf/ });
  await expect(rows).toHaveCount(3);
  await expect(rows.filter({ hasText: 'Working on it' }).first()).toBeVisible();
  const summary = page.getByTestId('batch-summary');
  await expect(summary).toHaveText(/^\d+ filed, \d+ need you, \d+ unreadable, 0 already had$/, { timeout: 180_000 });
  const text = (await summary.textContent()) ?? '';
  console.log(`live intake summary: ${text}`);
  const counts = text.match(/\d+/g)!.map(Number);
  expect(counts[0]! + counts[1]! + counts[2]!).toBe(3);
  await expect(rows.filter({ hasText: 'Working' })).toHaveCount(0);

  const latest = await page.request.get('/api/batches?limit=1');
  const batch = (await latest.json()).items[0];
  expect(batch.status).toBe('done');
  expect(batch.counts).toMatchObject({ items: 3, accepted: 3, duplicate: 0, rejected: 0, processing: 0 });
  expect(problems).toEqual([]);
});
