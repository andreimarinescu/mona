import { readFileSync } from 'node:fs';
import { expect, test } from '@playwright/test';

// C5 §7 against the vendored pdf.js: every verified quote's findQuery must highlight on its page.
// Input: `mona pipeline evidence --out cases.json`, run where the PDF paths resolve locally:
// MONA_FINDQUERY_CASES=cases.json npm run e2e -w apps/web -- findquery
interface Case {
  document_id: string;
  field: string;
  page: number;
  find_query: string;
  pdf: string | null;
  method: string | null;
}

const source = process.env.MONA_FINDQUERY_CASES;
const cases: Case[] = source ? (JSON.parse(readFileSync(source, 'utf8')) as Case[]).filter((c) => c.pdf) : [];

test.skip(!source, 'no findQuery cases requested (MONA_FINDQUERY_CASES)');
test.describe.configure({ timeout: 60_000 });

for (const [n, c] of cases.entries()) {
  test(`${c.document_id} ${c.field} p${c.page} (${c.method})`, async ({ page }) => {
    const url = `/dev/fixture/${n}.pdf`;
    await page.route(`**${url}`, (route) =>
      route.fulfill({ body: readFileSync(c.pdf as string), contentType: 'application/pdf' }),
    );
    await page.goto(`/dev/pdf?file=${encodeURIComponent(url)}&page=${c.page}&q=${encodeURIComponent(c.find_query)}`);
    const viewer = page.frameLocator('iframe[title="pdf.js"]');
    await expect(viewer.locator('.textLayer').first()).toBeAttached();
    await page.getByRole('button', { name: 'Find via event bus' }).click();
    const hit = viewer.locator(`.page[data-page-number="${c.page}"] .textLayer .highlight`);
    await expect(hit.first()).toBeAttached();
  });
}
