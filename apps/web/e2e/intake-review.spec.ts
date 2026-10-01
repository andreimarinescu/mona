import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';

const PDF = (text: string) => Buffer.from(`%PDF-1.4\n${text}\n%%EOF`);
const JPG = Buffer.from([0xff, 0xd8, 0xff, 0xe0, 0x00, 0x10, 0x4a, 0x46, 0x49, 0x46]);

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
  const { violations } = await new AxeBuilder({ page }).analyze();
  return violations.filter((v) => v.impact === 'serious' || v.impact === 'critical').map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(' | ')}`);
}

const panel = (page: Page) => page.locator('[role="complementary"][aria-label="Mona"]');
const toastRegion = (page: Page) => page.getByTestId('toast-region');

test.describe('intake', () => {
  test('drop 3 files: progress, summary line, then the questions banner opens the chat on the debrief', async ({ page }) => {
    const problems = watchConsole(page);
    await page.goto('/intake');
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Intake');
    await page.getByTestId('file-input').setInputFiles([
      { name: 'invoice_a.pdf', mimeType: 'application/pdf', buffer: PDF('a') },
      { name: 'scan_b.pdf', mimeType: 'application/pdf', buffer: PDF('b') },
      { name: 'blurry.jpg', mimeType: 'image/jpeg', buffer: JPG },
    ]);

    const progress = page.getByTestId('batch-progress');
    await expect(progress).toBeVisible();
    await expect(page.getByRole('progressbar')).toBeVisible();
    await expect(page.getByRole('list', { name: /Step \d of 5/ }).first()).toBeVisible();
    await expect(page.getByTestId('batch-summary')).toHaveText('1 filed, 1 need you, 1 unreadable, 0 already had', { timeout: 15_000 });
    await expect(progress.getByText('Filed · 1')).toBeVisible();

    const rows = page.getByRole('row').filter({ hasText: /\.(pdf|jpg)/ });
    await expect(rows).toHaveCount(3);
    await expect(rows.nth(0)).toContainText('Filed');
    await expect(rows.nth(1)).toContainText('Needs review');
    await expect(rows.nth(2)).toContainText('Unreadable');

    await expect(toastRegion(page).getByText('Filed 1 document')).toBeVisible();

    const banner = page.getByRole('status').filter({ hasText: 'Mona has 2 questions about this batch' });
    await expect(banner).toBeVisible({ timeout: 10_000 });
    await banner.getByRole('button', { name: 'Answer now' }).click();
    await expect(panel(page)).toBeVisible();
    await expect(panel(page).getByText("Let's go through your questions about this batch.")).toBeVisible();
    await expect(panel(page).getByText('Let us go through your questions.')).toBeVisible();
    const bodies = await page.evaluate(() => (window as unknown as { __chatBodies: { message: string; pageContext: { route: string; summary: string } }[] }).__chatBodies);
    expect(bodies[0]!.message).toBe("Let's go through your questions about this batch.");
    expect(bodies[0]!.pageContext.route).toBe('/intake');
    expect(bodies[0]!.pageContext.summary).toMatch(/^Intake, batch bat_[0-9a-z]{26} finished, 2 questions$/);
    expect(problems).toEqual([]);
  });

  test('a dropped duplicate and an unsupported file are reported per file', async ({ page }) => {
    await page.goto('/intake');
    await page.getByTestId('file-input').setInputFiles([{ name: 'invoice_a.pdf', mimeType: 'application/pdf', buffer: PDF('same') }]);
    await expect(page.getByTestId('batch-summary')).toBeVisible({ timeout: 15_000 });
    await page.getByTestId('file-input').setInputFiles([
      { name: 'again.pdf', mimeType: 'application/pdf', buffer: PDF('same') },
      { name: 'macro.exe', mimeType: 'application/octet-stream', buffer: Buffer.from('MZ....') },
    ]);
    await expect(page.getByTestId('batch-summary')).toHaveText('0 filed, 0 need you, 1 unreadable, 1 already had', { timeout: 10_000 });
    await expect(page.getByRole('row', { name: /again\.pdf/ })).toContainText('Already had');
    await expect(page.getByRole('row', { name: /macro\.exe/ })).toContainText('Only PDF, JPG and PNG files can be read.');
  });

  test('the drop zone is keyboard-operable and shows a drag-over state', async ({ page }) => {
    await page.goto('/intake');
    const choose = page.getByRole('button', { name: 'Choose files…' });
    await choose.focus();
    await expect(choose).toBeFocused();
    const chooser = page.waitForEvent('filechooser');
    await page.keyboard.press('Enter');
    await chooser;
    const zone = page.getByRole('region', { name: 'Add documents' });
    await zone.dispatchEvent('dragenter', { dataTransfer: await page.evaluateHandle(() => { const dt = new DataTransfer(); dt.items.add(new File(['x'], 'x.pdf')); return dt; }) });
    await expect(zone).toHaveAttribute('data-drag-over', '');
    await expect(page.getByRole('heading', { name: 'Drop to add them' })).toBeVisible();
    await page.getByRole('checkbox', { name: /Visitor document/ }).check();
    await expect(page.getByRole('checkbox', { name: /Visitor document/ })).toBeChecked();
  });
});

test.describe('review', () => {
  test('J and K move between documents, Enter confirms, and Undo on the toast puts it back', async ({ page }) => {
    await page.goto('/review');
    const items = page.getByTestId('review-item');
    await expect(items).toHaveCount(6);
    await expect(page.getByTestId('review-position')).toHaveText('1 of 6');
    await expect(page.getByTestId('review-detail')).toContainText('Nordtel invoice, September 2026');
    await page.keyboard.press('j');
    await expect(page).toHaveURL(/\/review\/doc_/);
    await expect(page.getByTestId('review-detail')).toContainText('Horizon letter of 24 September');
    await page.keyboard.press('k');
    await expect(page.getByTestId('review-detail')).toContainText('Nordtel invoice, September 2026');

    await page.keyboard.press('Enter');
    await expect(toastRegion(page).getByText('Filed 1 document')).toBeVisible();
    await expect(items).toHaveCount(5);
    await expect(page.getByRole('link', { name: /Review queue.*5/ })).toBeVisible();

    await toastRegion(page).getByRole('button', { name: 'Undo' }).click();
    await expect(toastRegion(page).getByText('Undid 1 change')).toBeVisible();
    await expect(items).toHaveCount(6);
  });

  test('correct a document, choose every document like this, preview, apply', async ({ page }) => {
    await page.goto('/review');
    const detail = page.getByTestId('review-detail');
    await expect(detail).toContainText('Nordtel invoice, September 2026');
    await expect(detail.getByTestId('suggestion-sentence')).toContainText("Atelier's line");
    await expect(detail.getByRole('meter')).toBeVisible();
    await detail.getByLabel('Entity').selectOption({ label: 'Cabinet Marchand' });
    await detail.getByRole('button', { name: 'Correct and file' }).click();

    const prompt = page.getByTestId('scope-prompt');
    await expect(prompt).toBeVisible();
    await expect(toastRegion(page).getByText(/Moved “Nordtel invoice, September 2026” to Cabinet Marchand/)).toBeVisible();
    await expect(page.getByTestId('review-item').first()).toContainText('Corrected by you');
    await prompt.getByRole('radio', { name: /Every document like this/ }).check();

    const preview = prompt.getByTestId('rule-preview');
    await expect(preview).toBeVisible();
    await expect(preview).toContainText('3 move · 1 stay');
    await expect(preview.getByTestId('path-diff')).toHaveCount(3);
    await prompt.getByRole('button', { name: 'Apply' }).click();
    await expect(toastRegion(page).getByText('Rule applied: moved 3 documents')).toBeVisible();
    await expect(page.getByTestId('scope-prompt')).toHaveCount(0);
    await expect(page.getByTestId('review-detail')).toContainText('Horizon letter of 24 September');
  });

  test('a corrected visitor document files to Visitors without offering every document like this', async ({ page }) => {
    await page.goto('/intake');
    await page.getByRole('checkbox', { name: /Visitor document/ }).check();
    await page.getByTestId('file-input').setInputFiles([{ name: 'scan_visitor.pdf', mimeType: 'application/pdf', buffer: PDF('visitor') }]);
    await expect(page.getByTestId('batch-summary')).toHaveText('0 filed, 1 need you, 0 unreadable, 0 already had', { timeout: 15_000 });
    await page.getByRole('navigation').getByRole('link', { name: /Review queue/ }).click();
    await page.getByTestId('review-item').getByRole('link', { name: 'scan visitor' }).click();
    const detail = page.getByTestId('review-detail');
    await expect(detail.getByTestId('visitors-entity')).toHaveValue('Visitors');
    await detail.getByLabel('Category', { exact: true }).selectOption({ label: 'Bank' });
    await detail.getByRole('button', { name: 'Correct and file' }).click();
    await expect(toastRegion(page).getByText('Moved “scan visitor” to Visitors')).toBeVisible();
    await expect(page.getByTestId('review-item').filter({ hasText: 'scan visitor' })).toHaveCount(0);
    await expect(page.getByTestId('scope-prompt')).toHaveCount(0);
  });

  test('Just this one closes the prompt without a rule', async ({ page }) => {
    await page.goto('/review');
    const detail = page.getByTestId('review-detail');
    await detail.getByLabel('Entity').selectOption({ label: 'Cabinet Marchand' });
    await detail.getByRole('button', { name: 'Correct and file' }).click();
    const prompt = page.getByTestId('scope-prompt');
    await prompt.getByRole('radio', { name: /Just this one/ }).check();
    await prompt.getByRole('button', { name: 'Done' }).click();
    await expect(page.getByTestId('scope-prompt')).toHaveCount(0);
    await expect(page.getByTestId('review-item')).toHaveCount(5);
  });

  test('bulk approve files the checked documents under one grouped toast', async ({ page }) => {
    await page.goto('/review');
    await page.getByRole('checkbox', { name: 'Select Martin Supplies credit note AV-2291' }).check();
    await page.getByRole('checkbox', { name: 'Select Horizon letter of 24 September' }).check();
    await page.getByRole('button', { name: 'Approve 2 selected' }).click();
    await expect(toastRegion(page).getByText('Filed 2 documents')).toBeVisible();
    await expect(page.getByTestId('review-item')).toHaveCount(4);
  });

  test('filters by reason', async ({ page }) => {
    await page.goto('/review');
    await page.getByRole('button', { name: /Unknown entity · 2/ }).click();
    await expect(page.getByTestId('review-item')).toHaveCount(2);
    await expect(page.getByTestId('review-item').first().getByText('Unknown entity')).toBeVisible();
  });
});

test.describe('activity', () => {
  test('undo from the Activity log, then redo; a whole batch undoes as one action', async ({ page }) => {
    await page.goto('/review');
    await expect(page.getByTestId('review-detail')).toContainText('Nordtel invoice, September 2026');
    await page.keyboard.press('Enter');
    await expect(page.getByTestId('review-item')).toHaveCount(5);
    await page.getByRole('navigation').getByRole('link', { name: 'Activity log' }).click();
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Activity log');
    const mine = page.locator('li[data-journal-id]').filter({ hasText: 'You filed Nordtel invoice, September 2026' });
    await expect(mine).toHaveAttribute('data-undo-state', 'undoable');
    await mine.getByRole('button', { name: 'Undo' }).click();
    await expect(mine).toHaveAttribute('data-undo-state', 'undone');
    await expect(mine.getByText('Undone at')).toBeVisible();
    await mine.getByRole('button', { name: 'Redo' }).click();
    await expect(mine).toHaveAttribute('data-undo-state', 'undoable');

    const batchId = (await page.locator('li[data-group-id]').filter({ hasText: 'Mona processed an intake batch' }).first().getAttribute('data-group-id'))!;
    const batch = page.locator(`li[data-group-id="${batchId}"]`);
    await batch.getByRole('button', { name: 'Undo whole batch' }).click();
    await expect(batch).toHaveAttribute('data-undo-state', 'undone');
    await batch.getByRole('button', { name: 'Show the changes in this group' }).click();
    await expect(batch.locator('li[data-undo-state="undone"]').first()).toBeVisible();
    await expect(batch.getByRole('button', { name: 'Redo' }).first()).toBeVisible();
  });

  test('superseded entries are shown disabled', async ({ page }) => {
    await page.goto('/activity');
    const filed = page.locator('li[data-group-id] >> xpath=..').first();
    await expect(filed).toBeVisible();
    await page.locator('li[data-group-id]').first().getByRole('button', { name: 'Show the changes in this group' }).click();
    const superseded = page.locator('li[data-undo-state="superseded"]').first();
    await expect(superseded.getByRole('button', { name: 'Undo' })).toBeDisabled();
    await expect(superseded.getByText('Moved since')).toBeVisible();
  });

  test('filters by actor and searches the journal', async ({ page }) => {
    await page.goto('/activity');
    await page.getByRole('radio', { name: 'By you' }).check();
    await expect(page.locator('li[data-group-id]')).toHaveCount(0);
    await page.getByRole('radio', { name: 'All' }).check();
    await page.getByRole('searchbox', { name: 'Search the journal' }).fill('Energie');
    await expect(page.locator('li[data-journal-id]').first()).toContainText('Energie');
  });
});

test.describe('mobile (390 wide)', () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test('Review shows the list, then one document with back and next', async ({ page }) => {
    const problems = watchConsole(page);
    await page.goto('/review');
    await expect(page.getByTestId('review-item')).toHaveCount(6);
    await expect(page.getByTestId('review-detail')).toBeHidden();
    await page.getByRole('link', { name: 'Nordtel invoice, September 2026' }).click();
    await expect(page.getByTestId('review-detail')).toBeVisible();
    await expect(page.getByRole('list', { name: 'Documents to review' })).toBeHidden();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(0);
    await page.getByRole('button', { name: 'Next document' }).click();
    await expect(page.getByTestId('review-detail')).toContainText('Horizon letter of 24 September');
    await page.getByRole('button', { name: 'Review queue' }).click();
    await expect(page.getByTestId('review-item')).toHaveCount(6);
    expect(await serious(page)).toEqual([]);
    expect(problems).toEqual([]);
  });

  test('Intake and Activity fit without sideways scrolling', async ({ page }) => {
    for (const path of ['/intake', '/activity']) {
      await page.goto(path);
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow).toBeLessThanOrEqual(0);
    }
  });
});

test.describe('console and accessibility', () => {
  test('no console errors or warnings across the new screens', async ({ page }) => {
    const problems = watchConsole(page);
    for (const path of ['/intake', '/review', '/activity']) {
      await page.goto(path);
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    }
    await page.goto('/review');
    const id = await page.getByTestId('review-detail').getAttribute('data-document-id');
    await page.goto(`/review/${id}`);
    await expect(page.getByTestId('review-detail')).toBeVisible();
    expect(problems).toEqual([]);
  });

  for (const path of ['/intake', '/review', '/activity']) {
    test(`axe: no serious or critical violations on ${path}`, async ({ page }) => {
      await page.goto(path);
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
      if (path === '/review') await expect(page.getByTestId('review-detail')).toBeVisible();
      if (path === '/activity') await expect(page.locator('li[data-group-id]').first()).toBeVisible();
      expect(await serious(page)).toEqual([]);
    });
  }

  test('axe: Intake with a batch, Review after a correction, Activity expanded', async ({ page }) => {
    await page.goto('/intake');
    await page.getByTestId('file-input').setInputFiles([{ name: 'scan_b.pdf', mimeType: 'application/pdf', buffer: PDF('b') }]);
    await expect(page.getByTestId('batch-summary')).toBeVisible({ timeout: 15_000 });
    expect(await serious(page)).toEqual([]);

    await page.goto('/review');
    const detail = page.getByTestId('review-detail');
    await detail.getByLabel('Entity').selectOption({ label: 'Cabinet Marchand' });
    await detail.getByRole('button', { name: 'Correct and file' }).click();
    await page.getByTestId('scope-prompt').getByRole('radio', { name: /Every document like this/ }).check();
    await expect(page.getByTestId('rule-preview')).toBeVisible();
    expect(await serious(page)).toEqual([]);

    await page.getByRole('navigation').getByRole('link', { name: 'Activity log' }).click();
    await page.locator('li[data-group-id]').first().getByRole('button', { name: 'Show the changes in this group' }).click();
    expect(await serious(page)).toEqual([]);
  });
});

test.describe('French and Romanian', () => {
  for (const [lng, words] of [
    ['fr', { h1: 'Réception', review: 'À vérifier', activity: "Journal d’activité" }],
    ['ro', { h1: 'Primire', review: 'De verificat', activity: 'Jurnal de activitate' }],
  ] as const) {
    test(`${lng}: the three screens render translated, with no raw keys or console errors`, async ({ page }) => {
      const problems = watchConsole(page);
      await page.addInitScript((l) => localStorage.setItem('mona.msw.locale', l), lng);
      const rawKey = /\b(intake|review|activity|common|toast|rules|errors)\.[a-zA-Z_]+/;
      await page.goto('/intake');
      await expect(page.getByRole('heading', { level: 1 })).toHaveText(words.h1);
      await expect(page.locator('main')).not.toContainText(rawKey);
      await page.goto('/review');
      await expect(page.getByRole('heading', { level: 1 })).toHaveText(words.review);
      await expect(page.getByTestId('review-detail')).toBeVisible();
      await expect(page.locator('main')).not.toContainText(rawKey);
      await page.getByRole('navigation').getByRole('link', { name: words.activity }).click();
      await expect(page.getByRole('heading', { level: 1 })).toHaveText(words.activity);
      await expect(page.locator('li[data-group-id]').first()).toBeVisible();
      await expect(page.locator('main')).not.toContainText(rawKey);
      expect(problems).toEqual([]);
    });
  }
});
