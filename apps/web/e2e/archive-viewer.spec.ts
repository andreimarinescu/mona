import AxeBuilder from '@axe-core/playwright';
import { expect, test, type FrameLocator, type Page } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('mona.msw', '1');
    localStorage.setItem('mona.msw.step', '250');
  });
});

function watchConsole(page: Page): string[] {
  const problems: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error' || msg.type() === 'warning') problems.push(`${msg.type()}: ${msg.text()}`);
  });
  page.on('pageerror', (err) => problems.push(`pageerror: ${err.message}`));
  return problems;
}

async function serious(page: Page) {
  await page.evaluate(() => Promise.all(document.getAnimations().map((a) => a.finished.catch(() => undefined))));
  const { violations } = await new AxeBuilder({ page }).analyze();
  return violations.filter((v) => v.impact === 'serious' || v.impact === 'critical').map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(' | ')}`);
}

const SHOWCASE = 'Call for contributions, Q3 2026';
const results = (page: Page) => page.getByTestId('results-table');
const count = (page: Page) => page.getByTestId('results-count');
const panel = (page: Page) => page.locator('[role="complementary"][aria-label="Mona"]');

async function documentId(page: Page, title: string): Promise<string> {
  await page.waitForFunction(() => '__mock' in window);
  return page.evaluate((t) => {
    const world = (window as unknown as { __mock: { docs: Map<string, { summary: { id: string; title: string } }> } }).__mock;
    return [...world.docs.values()].find((d) => d.summary.title === t)!.summary.id;
  }, title);
}

async function pdfFrame(page: Page): Promise<FrameLocator> {
  const frame = page.frameLocator('iframe[data-testid="pdf-frame"]');
  await expect(frame.locator('.textLayer').first()).toContainText('Montant à payer', { timeout: 20_000 });
  return frame;
}

test.describe('archive search', () => {
  test('lists filed and review documents, 25 to a page, and pages through them', async ({ page }) => {
    await page.goto('/archive');
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Archive');
    await expect(results(page).getByRole('row')).toHaveCount(26);
    await expect(count(page)).toContainText('27 documents');
    await expect(page.getByRole('navigation', { name: /Page 1 of 2/ })).toBeVisible();
    await page.getByRole('button', { name: 'Next page' }).click();
    await expect(results(page).getByRole('row')).toHaveCount(3);
    await expect(page).toHaveURL(/page=2/);
  });

  test('searches, filters by every facet, and removes the filters again', async ({ page }) => {
    const problems = watchConsole(page);
    await page.goto('/archive');
    await page.getByRole('searchbox', { name: 'Search the archive' }).fill('URSSAF');
    await page.keyboard.press('Enter');
    await expect(count(page)).toHaveText('9 documents for “URSSAF”');
    await expect(page).toHaveURL(/q=URSSAF/);

    await page.getByRole('button', { name: /^2026 · / }).click();
    await expect(count(page)).toHaveText('4 documents for “URSSAF”');
    await expect(page.getByTestId('active-filters').getByText('2026')).toBeVisible();

    await page.getByRole('button', { name: /^2026 · / }).click();
    await page.getByLabel('Category').selectOption({ label: 'Tax · 9' });
    await expect(page.getByTestId('active-filters').getByText('Tax')).toBeVisible();
    await page.getByRole('combobox', { name: 'Counterparty' }).click();
    await page.getByRole('option', { name: /^URSSAF/ }).click();
    await expect(page.getByTestId('active-filters').getByText('URSSAF')).toBeVisible();

    await page.getByLabel('Minimum amount').fill('1250');
    await page.getByLabel('Minimum amount').blur();
    await expect(count(page)).toHaveText('3 documents for “URSSAF”');
    await expect(page.getByTestId('active-filters').getByText('≥ 1,250')).toBeVisible();
    for (const row of await results(page).getByRole('row').filter({ hasText: 'Call for contributions' }).all()) await expect(row).toContainText(/€1,284.00|€4,788.00/);

    await page.getByRole('checkbox', { name: /Filed/ }).uncheck();
    await expect(page.getByTestId('active-filters').getByText('Needs review, Unreadable')).toBeVisible();
    await expect(page.getByTestId('results-table')).toHaveCount(0);
    await expect(page.getByText('No documents match')).toBeVisible();

    await page.getByRole('button', { name: 'Clear search and filters' }).click();
    await expect(count(page)).toContainText('27 documents');
    await expect(page.getByTestId('active-filters')).toHaveCount(0);
    expect(problems).toEqual([]);
  });

  test('the sidebar entity scope applies, and the chat panel names the search', async ({ page }) => {
    await page.goto('/archive');
    await page.getByRole('searchbox', { name: 'Search the archive' }).fill('Nordtel');
    await page.keyboard.press('Enter');
    await expect(count(page)).toHaveText('4 documents for “Nordtel”');
    await page.getByRole('button', { name: 'Ask Mona', exact: true }).click();
    await expect(panel(page).getByTestId('page-context')).toHaveText('Mona can see: Archive, search “Nordtel”, 4 results');
    await page.getByLabel('Showing').selectOption({ label: 'Cabinet Marchand' });
    await expect(count(page)).toHaveText('0 documents for “Nordtel”');
    await expect(page.getByRole('group', { name: 'Entity' })).toHaveCount(0);
    await expect(panel(page).getByTestId('page-context')).toHaveText('Mona can see: Archive, search “Nordtel”, 0 results, filtered to Cabinet Marchand');
  });

  test('"Ask Mona instead" sends the search text with the page context in English', async ({ page }) => {
    await page.goto('/archive');
    await page.getByRole('searchbox', { name: 'Search the archive' }).fill('how much did URSSAF take in 2026');
    await page.getByRole('button', { name: 'Ask Mona instead' }).click();
    await expect(panel(page).getByText('how much did URSSAF take in 2026')).toBeVisible();
    const bodies = await page.evaluate(() => (window as unknown as { __chatBodies: { message: string; pageContext: { route: string; summary: string } }[] }).__chatBodies);
    expect(bodies[0]!.message).toBe('how much did URSSAF take in 2026');
    expect(bodies[0]!.pageContext.summary).toMatch(/^Archive, \d+ results$/);
  });

  test('the page context line follows the interface language, the model summary stays English', async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem('mona.stub.language', 'fr'));
    await page.goto('/archive?q=URSSAF');
    await expect(count(page)).toContainText('9 documents');
    await page.getByRole('button', { name: 'Demander à Mona', exact: true }).click();
    await expect(panel(page).getByTestId('page-context')).toContainText('Mona voit : Archives, recherche « URSSAF », 9 résultats');
  });
});

test.describe('folders', () => {
  test('the tree mirrors the archive: expand, select, and the folder lists its files', async ({ page }) => {
    const problems = watchConsole(page);
    await page.goto('/archive');
    await page.getByRole('radio', { name: 'Folders' }).click();
    await expect(page).toHaveURL(/\/archive\/folders$/);
    const tree = page.getByRole('tree', { name: 'Archive folders' });
    await expect(tree.getByRole('treeitem', { name: /^Cabinet Marchand, 14 documents/ })).toBeVisible();
    const cabinet = tree.getByRole('treeitem', { name: /^Cabinet Marchand,/ });
    await expect(cabinet).toHaveAttribute('aria-expanded', 'false');
    await cabinet.click();
    await expect(cabinet).toHaveAttribute('aria-expanded', 'true');
    await expect(cabinet).toHaveAttribute('aria-level', '1');
    const year = tree.getByRole('treeitem', { name: /^2026 Cabinet Marchand,/ });
    await expect(year).toHaveAttribute('aria-level', '2');
    await year.click();
    await tree.getByRole('treeitem', { name: /^Impôts,/ }).first().click();
    await tree.getByRole('treeitem', { name: /^Appels de paiement,/ }).click();
    await expect(page).toHaveURL(/\/archive\/folders\/Cabinet%20Marchand\/2026%20Cabinet%20Marchand\/Imp%C3%B4ts\/Appels%20de%20paiement$/);
    await expect(tree.getByRole('treeitem', { name: /^Appels de paiement,/ })).toHaveAttribute('aria-selected', 'true');

    const contents = page.getByTestId('folder-contents');
    await expect(contents.getByRole('heading', { level: 2 })).toHaveText('Appels de paiement');
    await expect(page.getByTestId('disk-path')).toHaveText('Cabinet Marchand / 2026 Cabinet Marchand / Impôts / Appels de paiement');
    await expect(contents.getByRole('row').filter({ hasText: '.pdf' })).toHaveCount(4);
    await expect(contents.getByRole('row', { name: /2026-09-22_URSSAF_Appel_T3\.pdf/ })).toContainText('Mona · rule “URSSAF calls”');
    await expect(contents.getByText('This view mirrors the archive on disk')).toBeVisible();
    await contents.getByRole('button', { name: 'Show in Explorer' }).click();
    await expect(contents.getByText(/isn't available in the web app yet/)).toBeVisible();
    expect(problems).toEqual([]);
  });

  test('the tree is keyboard-operable: arrows move, right expands, left collapses, Enter opens', async ({ page }) => {
    await page.goto('/archive/folders');
    const tree = page.getByRole('tree', { name: 'Archive folders' });
    const first = tree.getByRole('treeitem').first();
    await expect(first).toBeVisible();
    await first.focus();
    await page.keyboard.press('ArrowRight');
    await expect(first).toHaveAttribute('aria-expanded', 'true');
    await page.keyboard.press('ArrowRight');
    await expect(tree.getByRole('treeitem').nth(1)).toBeFocused();
    await page.keyboard.press('ArrowLeft');
    await expect(first).toBeFocused();
    await page.keyboard.press('ArrowLeft');
    await expect(first).toHaveAttribute('aria-expanded', 'false');
    await page.keyboard.press('ArrowDown');
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(/\/archive\/folders\/[^/]+$/);
    await expect(tree.getByRole('treeitem', { selected: true })).toHaveCount(1);
  });

  test('a deep link opens the tree on its folder', async ({ page }) => {
    await page.goto('/archive/folders/Cabinet%20Marchand/2025%20Cabinet%20Marchand');
    const tree = page.getByRole('tree', { name: 'Archive folders' });
    await expect(tree.getByRole('treeitem', { name: /^2025 Cabinet Marchand,/ })).toHaveAttribute('aria-selected', 'true');
    await expect(tree.getByRole('treeitem', { name: /^Cabinet Marchand,/ })).toHaveAttribute('aria-expanded', 'true');
    await expect(page.getByTestId('folder-contents').getByRole('heading', { level: 2 })).toHaveText('2025 Cabinet Marchand');
  });
});

test.describe('document viewer', () => {
  test('opens from a result with the search text, highlights it on load and shows what Mona read', async ({ page }) => {
    const problems = watchConsole(page);
    await page.goto('/archive?q=URSSAF');
    await results(page).getByRole('link', { name: SHOWCASE }).click();
    await expect(page).toHaveURL(/\/documents\/doc_[0-9a-z]{26}\?q=URSSAF$/);
    await expect(page.getByRole('heading', { level: 1 })).toHaveText(SHOWCASE);
    const frame = await pdfFrame(page);
    await expect(frame.locator('.textLayer .highlight').first()).toContainText('URSSAF');

    const side = page.getByTestId('side-panel');
    await expect(side.getByRole('heading', { name: 'What Mona read' })).toBeVisible();
    await expect(side.locator('[data-field="amount"]')).toContainText('€1,284.00');
    await expect(side.locator('[data-field="amount"] q')).toHaveText('Montant à payer 1 284,00 €');
    await expect(side.locator('[data-field="amount"] q')).toHaveAttribute('lang', 'fr');
    await expect(side.locator('[data-field="due_date"]')).toContainText('15 October 2026');
    await expect(side.locator('[data-field="addressee"]')).toContainText('Not found on the page');
    await expect(side.locator('[data-field="amount"]')).toContainText('Found on the page');
    await expect(page.getByTestId('filed-section')).toContainText('Cabinet Marchand');
    await expect(page.getByTestId('filed-name')).toHaveText('2026-09-22_URSSAF_Appel_T3.pdf');
    await expect(page.getByTestId('filed-section').getByRole('link', { name: 'URSSAF calls' })).toBeVisible();
    expect(problems).toEqual([]);
  });

  test('Show on page finds the field in the PDF with its findQuery', async ({ page }) => {
    await page.goto('/archive');
    const id = await documentId(page, SHOWCASE);
    await page.goto(`/documents/${id}`);
    const frame = await pdfFrame(page);
    await expect(frame.locator('.textLayer .highlight')).toHaveCount(0);
    const amount = page.getByTestId('side-panel').locator('[data-field="amount"]');
    await amount.getByRole('button', { name: 'Show on page: Amount' }).click();
    await expect(frame.locator('.textLayer .highlight').first()).toContainText('284,00');
    await expect(amount.getByRole('button', { name: 'Show on page: Amount' })).toHaveText('Showing');
    await expect(amount.getByRole('button', { name: 'Show on page: Amount' })).toHaveAttribute('aria-pressed', 'true');

    const issuer = page.getByTestId('side-panel').locator('[data-field="issuer"]');
    await issuer.getByRole('button', { name: 'Show on page: Issuer' }).click();
    await expect(frame.locator('.textLayer .highlight').first()).toContainText('Union de recouvrement fictive');
  });

  test('an unverified field falls back to its value', async ({ page }) => {
    await page.goto('/archive');
    const id = await documentId(page, SHOWCASE);
    await page.goto(`/documents/${id}`);
    const frame = await pdfFrame(page);
    await page.getByTestId('side-panel').locator('[data-field="addressee"]').getByRole('button', { name: /Show on page/ }).click();
    await expect(frame.locator('.textLayer .highlight').first()).toContainText('Cabinet dentaire Exemple');
  });

  test('the deep link highlights q on load, opens at the page, and focuses the field', async ({ page }) => {
    await page.goto('/archive');
    const id = await documentId(page, SHOWCASE);
    await page.goto(`/documents/${id}?page=1&q=${encodeURIComponent('1 284,00')}&field=amount`);
    const frame = await pdfFrame(page);
    await expect(frame.locator('.textLayer .highlight').first()).toContainText('284,00');
    await expect(page.getByTestId('side-panel').locator('[data-field="amount"]')).toBeFocused();
    await expect(page.getByTestId('pdf-frame')).toHaveAttribute('src', /viewer\.html\?file=%2Fapi%2Fdocuments%2Fdoc_[0-9a-z]{26}%2Fpdf$/);
  });

  test('the history lists the journal; Undo sends the document back to review and Redo files it again', async ({ page }) => {
    await page.goto('/archive');
    const id = await documentId(page, SHOWCASE);
    await page.goto(`/documents/${id}`);
    const history = page.getByRole('region', { name: 'Document details' }).getByRole('list', { name: 'History of this document' });
    await expect(history.getByRole('listitem')).toHaveCount(2);
    await expect(history.getByRole('listitem').first()).toContainText('Journal #');
    const filed = history.getByRole('listitem').filter({ hasText: 'filed' });
    await filed.getByRole('button', { name: 'Undo' }).click();
    await expect(page.getByTestId('toast-region').getByText('Undid 1 change')).toBeVisible();
    await expect(page.getByTestId('filed-section')).toHaveCount(0);
    await expect(page.getByRole('region', { name: 'Document details' }).getByText("This document isn't filed yet.")).toBeVisible();
    await expect(history.getByRole('listitem').first()).toContainText('You undid');
    await history.getByRole('button', { name: 'Redo' }).first().click();
    await expect(page.getByTestId('filed-section')).toBeVisible();
    await expect(page.getByTestId('toast-region').getByText('Redid 1 change')).toBeVisible();
  });

  test('sets a reminder, shows it, and cancels it', async ({ page }) => {
    await page.goto('/archive');
    const id = await documentId(page, SHOWCASE);
    await page.goto(`/documents/${id}`);
    const reminder = page.getByTestId('reminder');
    await expect(reminder.getByTestId('deadline-line')).toContainText('Due 15 October 2026');
    await reminder.getByRole('button', { name: 'Remind me' }).click();
    await reminder.getByLabel('Remind me on').fill('2030-01-15');
    await reminder.getByRole('button', { name: 'Set reminder' }).click();
    await expect(reminder.getByRole('status')).toHaveText('Reminder set for 15 January 2030');
    await reminder.getByRole('button', { name: 'Cancel reminder' }).click();
    await expect(reminder.getByRole('button', { name: 'Remind me' })).toBeVisible();
  });

  test('a document that is still processing shows its progress, not a PDF', async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem('mona.msw.step', '600000'));
    await page.goto('/intake');
    await page.getByTestId('file-input').setInputFiles([{ name: 'new_invoice.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4\nx\n%%EOF') }]);
    await expect(page.getByTestId('batch-progress')).toBeVisible();
    const id = await page.evaluate(() => {
      const world = (window as unknown as { __mock: { docs: Map<string, { summary: { id: string; originalName: string } }> } }).__mock;
      return [...world.docs.values()].find((d) => d.summary.originalName === 'new_invoice.pdf')!.summary.id;
    });
    await page.evaluate((target) => {
      history.pushState({}, '', `/documents/${target}`);
      dispatchEvent(new PopStateEvent('popstate'));
    }, id);
    await expect(page.getByTestId('viewer-processing')).toBeVisible();
    await expect(page.getByTestId('pdf-frame')).toHaveCount(0);
  });

  test('an unreadable document says so and offers the review queue', async ({ page }) => {
    await page.goto('/archive');
    const id = await documentId(page, 'IMG_2231.jpg');
    await page.goto(`/documents/${id}`);
    await expect(page.getByTestId('viewer-unreadable')).toContainText("I couldn't read this document");
    await expect(page.getByTestId('pdf-frame')).toHaveCount(0);
    await expect(page.getByRole('region', { name: 'Document details' }).getByRole('link', { name: 'Open it in the review queue' })).toBeVisible();
  });

  test('an unknown document shows the not-found state, not a server 404', async ({ page }) => {
    await page.goto('/documents/doc_0000000000000000000000zzzz');
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Document');
    await expect(page.getByText("I can't find this document")).toBeVisible();
  });
});

test.describe('accountant export', () => {
  test('entity and year, what is included, build, ready, download', async ({ page }) => {
    const problems = watchConsole(page);
    await page.goto('/archive');
    await page.getByRole('button', { name: 'Export for accountant…' }).click();
    const dialog = page.getByRole('dialog', { name: 'Export for your accountant' });
    await expect(dialog).toBeVisible();

    const entity = dialog.getByLabel('Entity');
    await expect(entity.locator('option')).toHaveText(['Cabinet Marchand', 'SCI Les Tilleuls', 'Atelier Numérique']);
    await expect(dialog.getByLabel('Fiscal year').locator('option')).toHaveText(['2026', '2025']);
    await expect(dialog.getByTestId('export-count')).toHaveText('7 documents, as filed, in their folders');
    await expect(dialog.getByTestId('export-included')).toContainText('Tax 4 · Bank 2 · Insurance 1');
    await expect(dialog.getByTestId('export-in-review')).toContainText("2 documents are left out until they're filed.");
    await expect(dialog.getByText('Personal entities and Visitors are never included.')).toBeVisible();

    await dialog.getByLabel('Fiscal year').selectOption('2025');
    await expect(dialog.getByTestId('export-count')).toHaveText('7 documents, as filed, in their folders');
    await expect(dialog.getByTestId('export-included')).toContainText('Tax 7');
    await expect(dialog.getByTestId('export-in-review')).toHaveCount(0);

    await dialog.getByRole('button', { name: 'Export 7 documents' }).click();
    await expect(dialog.getByTestId('export-building')).toBeVisible();
    await expect(dialog.getByTestId('export-ready')).toBeVisible({ timeout: 20_000 });
    await expect(dialog.getByText('The pack is ready')).toBeVisible();
    const zip = dialog.getByRole('link', { name: 'Download the zip' });
    await expect(zip).toHaveAttribute('download', '');
    const href = (await zip.getAttribute('href'))!;
    expect(href).toMatch(/^\/api\/exports\/exp_[0-9a-z]{26}\/zip$/);
    const served = await page.evaluate(async (url) => {
      const res = await fetch(url);
      return { status: res.status, type: res.headers.get('content-type'), disposition: res.headers.get('content-disposition'), size: (await res.arrayBuffer()).byteLength };
    }, href);
    expect(served).toMatchObject({ status: 200, type: 'application/zip', size: 22 });
    expect(served.disposition).toContain('attachment');
    await expect(dialog.getByRole('link', { name: 'Download the CSV index' })).toHaveAttribute('href', /\/csv$/);
    await dialog.getByRole('button', { name: 'Close' }).first().click();
    await expect(dialog).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Export for accountant…' })).toBeFocused();
    expect(problems).toEqual([]);
  });

  test('a failed build says so and can be retried', async ({ page }) => {
    await page.goto('/archive');
    await page.waitForFunction(() => '__mock' in window);
    await page.evaluate(() => {
      (window as unknown as { __mock: { exports: { control: { failNext: boolean } } } }).__mock.exports.control.failNext = true;
    });
    await page.getByRole('button', { name: 'Export for accountant…' }).click();
    const dialog = page.getByRole('dialog', { name: 'Export for your accountant' });
    await dialog.getByRole('button', { name: /^Export \d+ documents$/ }).click();
    await expect(dialog.getByText("The export didn't finish")).toBeVisible({ timeout: 20_000 });
    await dialog.getByRole('button', { name: 'Try again' }).click();
    await dialog.getByRole('button', { name: /^Export \d+ documents$/ }).click();
    await expect(dialog.getByTestId('export-ready')).toBeVisible({ timeout: 20_000 });
  });

  test('personal entities and Visitors are not offered, and Esc closes the dialog', async ({ page }) => {
    await page.goto('/archive');
    await page.getByRole('button', { name: 'Export for accountant…' }).click();
    const dialog = page.getByRole('dialog', { name: 'Export for your accountant' });
    await expect(dialog.getByLabel('Entity').locator('option', { hasText: /Personnel|Visitors/ })).toHaveCount(0);
    await page.keyboard.press('Escape');
    await expect(dialog).toHaveCount(0);
  });

  test('the dialog opens over the folder view too', async ({ page }) => {
    await page.goto('/archive/folders');
    await page.getByRole('button', { name: 'Export for accountant…' }).click();
    await expect(page.getByRole('dialog', { name: 'Export for your accountant' })).toBeVisible();
  });
});

test.describe('accessibility and languages', () => {
  test('axe: no serious or critical violations on the archive, folders, the viewer and the dialog', async ({ page }) => {
    await page.goto('/archive?q=URSSAF');
    await expect(results(page)).toBeVisible();
    expect(await serious(page)).toEqual([]);

    await page.getByRole('button', { name: 'Export for accountant…' }).click();
    await expect(page.getByTestId('export-included')).toBeVisible();
    expect(await serious(page)).toEqual([]);
    await page.keyboard.press('Escape');

    await page.goto('/archive/folders/Cabinet%20Marchand/2025%20Cabinet%20Marchand');
    await expect(page.getByTestId('folder-contents').getByRole('heading', { level: 2 })).toBeVisible();
    expect(await serious(page)).toEqual([]);

    await page.goto('/archive');
    const id = await documentId(page, SHOWCASE);
    await page.goto(`/documents/${id}`);
    await pdfFrame(page);
    expect(await serious(page)).toEqual([]);
  });

  for (const [lng, ask, heading] of [
    ['fr', 'Exporter pour le comptable…', 'Archives'],
    ['ro', 'Exportați pentru contabil…', 'Arhivă'],
  ] as const) {
    test(`the archive, the viewer and the dialog render in ${lng}`, async ({ page }) => {
      await page.addInitScript((l) => localStorage.setItem('mona.stub.language', l), lng);
      await page.goto('/archive');
      await expect(page.getByRole('heading', { level: 1 })).toHaveText(heading);
      await expect(page.getByRole('button', { name: ask })).toBeVisible();
      await expect(results(page).getByRole('row').nth(1)).toBeVisible();
      expect(await serious(page)).toEqual([]);
      await page.getByRole('button', { name: ask }).click();
      await expect(page.getByTestId('export-included')).toBeVisible();
      expect(await serious(page)).toEqual([]);
      await page.keyboard.press('Escape');
      const id = await documentId(page, SHOWCASE);
      await page.goto(`/documents/${id}`);
      const quote = page.getByTestId('side-panel').locator('[data-field="amount"] q');
      if (lng === 'fr') await expect(quote).not.toHaveAttribute('lang', /.+/);
      else await expect(quote).toHaveAttribute('lang', 'fr');
    });
  }

  test('at 390 wide the facets fold away and nothing scrolls sideways', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/archive');
    await expect(page.getByText('Filters', { exact: true })).toBeVisible();
    await expect(results(page)).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });
});
