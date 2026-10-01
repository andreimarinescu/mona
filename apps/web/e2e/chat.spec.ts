import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Locator, type Page } from '@playwright/test';

const PDF = (text: string) => Buffer.from(`%PDF-1.4\n${text}\n%%EOF`);

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('mona.msw', '1');
    localStorage.setItem('mona.msw.step', '150');
    localStorage.setItem('mona.msw.chatDelay', '15');
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
const composer = (scope: Page | Locator) => scope.getByRole('textbox', { name: 'Write to Mona…' });

async function ask(scope: Page | Locator, page: Page, text: string) {
  const before = await page.locator('[data-role="assistant"]').count();
  await composer(scope).fill(text);
  await composer(scope).press('Enter');
  await expect(page.locator('[data-role="assistant"]')).toHaveCount(before + 1);
  await expect(page.locator('[data-chat-status="ready"]')).toBeVisible();
}

test.describe('the debrief (demo 4:00)', () => {
  test('banner → panel → InterviewCard → answer 1 → two RulePreviewCards → Apply all → applied → undo from the toast → back to draft', async ({ page }) => {
    const problems = watchConsole(page);
    await page.goto('/intake');
    await page.getByTestId('file-input').setInputFiles(['scan_per_1.pdf', 'scan_vie_1.pdf', 'scan_per_2.pdf', 'invoice_x.pdf'].map((name) => ({ name, mimeType: 'application/pdf', buffer: PDF(name) })));
    const banner = page.getByRole('status').filter({ hasText: 'Mona has 2 questions about this batch' });
    await banner.getByRole('button', { name: 'Answer now' }).click({ timeout: 20_000 });

    await expect(panel(page)).toBeVisible();
    const card = panel(page).locator('[data-card="interview"]');
    await expect(card).toBeVisible();
    await expect(card).toContainText('A question from Mona');
    await expect(card).toContainText('Affects 3 documents');
    await expect(card.getByTestId('evidence-snippet')).toHaveCount(3);
    await expect(card.getByTestId('evidence-snippet').first()).toHaveAttribute('href', /^\/documents\/doc_[0-9a-z]{26}\?page=1&q=contrat\+retraite$/);
    const suggested = card.getByRole('button', { name: 'Personal: split retirement and life insurance' });
    await expect(suggested).toHaveClass(/mona-btn--primary/);
    expect(await serious(page)).toEqual([]);

    await card.getByRole('group').first().focus();
    await page.keyboard.press('1');
    const previews = card.locator('[data-card="rulePreview"]');
    await expect(previews).toHaveCount(2);
    await expect(previews.nth(0)).toContainText('2 move · 0 stay');
    await expect(previews.nth(1)).toContainText('1 move · 0 stay');
    await expect(previews.nth(0)).toHaveAttribute('data-state', 'draft');

    await card.getByRole('button', { name: 'Apply all (2 rules)' }).click();
    await expect(previews.nth(0)).toHaveAttribute('data-applied', 'true');
    await expect(previews.nth(1)).toHaveAttribute('data-applied', 'true');
    await expect(previews.nth(0).getByRole('status')).toHaveText('Applied: 2 documents moved');
    await expect(previews.nth(1).getByRole('status')).toHaveText('Applied: 1 document moved');
    await expect(card).toContainText('All 2 rules applied');
    await expect(page.getByTestId('batch-summary')).toHaveText('4 filed, 0 need you, 0 unreadable, 0 already had');

    const toast = page.getByTestId('toast-region').getByRole('status').filter({ hasText: 'Applied the rules: moved 3 documents' });
    await toast.getByRole('button', { name: 'Undo' }).click();
    await expect(previews.nth(0)).toHaveAttribute('data-applied', 'false');
    await expect(previews.nth(1)).toHaveAttribute('data-applied', 'false');
    await expect(previews.nth(0)).toHaveAttribute('data-state', 'draft');
    await expect(previews.nth(1)).toHaveAttribute('data-state', 'draft');
    await expect(card.getByRole('button', { name: 'Apply all (2 rules)' })).toBeEnabled();
    await expect(page.getByTestId('batch-summary')).toHaveText('1 filed, 3 need you, 0 unreadable, 0 already had');

    await ask(panel(page), page, 'What happens next?');
    await expect(panel(page).getByTestId('mona-text').last()).toContainText(/^Noted: Answered interview question .* Applied the rule .* Undid/);
    expect(problems).toEqual([]);
  });
});

test.describe('the /chat page (demo 7:00)', () => {
  test('a French ask gets a DraftCard: Copy and Download .docx, never Send; the download reaches Mona as a note', async ({ page, context }) => {
    await context.grantPermissions(['clipboard-read', 'clipboard-write']);
    const problems = watchConsole(page);
    await page.goto('/chat');
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Chat');
    await ask(page, page, 'Pouvez-vous rédiger une réponse pour demander un échéancier ?');
    await expect(page).toHaveURL(/\/chat\/cnv_[0-9a-z]{26}$/);
    const draft = page.locator('[data-card="draft"]');
    await expect(draft.getByTestId('draft-body')).toBeVisible({ timeout: 10_000 });
    await expect(draft.getByTestId('draft-body')).toHaveAttribute('lang', 'fr');
    await expect(draft.locator('mark').first()).toHaveText('[VOTRE N° DE COMPTE]');
    await expect(draft).toContainText('Mona never sends anything');
    await expect(draft.getByRole('button', { name: /send/i })).toHaveCount(0);

    await draft.getByRole('button', { name: 'Copy' }).click();
    await expect(draft.getByRole('button', { name: 'Copied' })).toBeVisible();
    expect(await page.evaluate(() => navigator.clipboard.readText())).toMatch(/^Objet : demande d’échéancier/);

    const download = page.waitForEvent('download');
    await draft.getByRole('button', { name: 'Download .docx' }).click();
    expect((await download).suggestedFilename()).toBe('Réponse au centre des cotisations.docx');

    await ask(page, page, 'Merci beaucoup pour la suite');
    await expect(page.getByTestId('mona-text').last()).toContainText('Noted: Downloaded the draft "Réponse au centre des cotisations".');
    expect(problems).toEqual([]);
  });

  test('the conversation list: newest first, search, and opening one reloads its transcript (C3 §7.2)', async ({ page }) => {
    await page.goto('/chat');
    await ask(page, page, 'How much did we pay last year?');
    await expect(page.locator('[data-card="doc"]')).toHaveCount(2);
    await page.getByRole('link', { name: 'New conversation' }).click();
    await expect(page).toHaveURL(/\/chat$/);
    await expect(page.getByTestId('chat-title')).toHaveText('New conversation');
    await ask(page, page, "What's due this month?");
    const list = page.getByTestId('conversation-list');
    await expect(list.locator('[data-conversation]')).toHaveText([/What's due this month\?/, /How much did we pay last year\?/]);
    await expect(list.locator('[data-conversation][aria-current="page"]')).toContainText("What's due this month?");

    await list.getByRole('searchbox', { name: 'Search conversations' }).fill('how much');
    await expect(list.locator('[data-conversation]')).toHaveText([/How much did we pay last year\?/]);
    await list.locator('[data-conversation]').first().click();
    await expect(page).toHaveURL(/\/chat\/cnv_[0-9a-z]{26}$/);
    await expect(page.getByTestId('chat-title')).toHaveText('How much did we pay last year?');
    await expect(page.locator('[data-role="user"]')).toHaveCount(1);
    await expect(page.locator('[data-card="doc"]')).toHaveCount(2);
    await expect(page.locator('[data-testid="tool-chip"]')).toHaveText(['Searched the archive', 'Added up the amounts']);
    await expect(page.getByRole('button', { name: /^Source 1:/ })).toBeVisible();

    await page.getByRole('navigation').first().getByRole('link', { name: 'Archive' }).click();
    await page.goBack();
    await expect(page.locator('[data-role="user"]')).toHaveCount(1);
    await expect(page.locator('[data-card="doc"]')).toHaveCount(2);
    expect(await serious(page)).toEqual([]);

    await page.getByRole('button', { name: 'Open as panel' }).click();
    await expect(page).toHaveURL(/\/$/);
    await expect(panel(page).locator('[data-role="user"]')).toHaveCount(1);
    await expect(panel(page).locator('[data-role="user"]')).toContainText('How much did we pay last year?');
    await expect(panel(page).locator('[data-card="doc"]')).toHaveCount(2);
  });

  test('Stop ends a streaming answer; the composer is back for the next one', async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem('mona.msw.chatDelay', '120'));
    await page.goto('/chat');
    await composer(page).fill('How much did we pay last year?');
    await composer(page).press('Enter');
    await expect(page.getByTestId('chat-composer')).toHaveAttribute('data-state', 'sending');
    await page.getByRole('button', { name: 'Stop' }).click();
    await expect(page.getByRole('button', { name: 'Send' })).toBeVisible();
    await expect(page.locator('[data-chat-status="ready"]')).toBeVisible();
  });

  test('a file dropped on the conversation goes to Intake as an AttachmentChip', async ({ page }) => {
    await page.goto('/chat');
    await page.getByTestId('composer-file-input').setInputFiles([{ name: 'Relance_2026-09-22.pdf', mimeType: 'application/pdf', buffer: PDF('relance') }]);
    const chip = page.getByTestId('chat-composer').getByTestId('attachment-chip');
    await expect(chip).toHaveAttribute('data-outcome', 'accepted');
    await expect(chip).toContainText('Added to Intake');
    await ask(page, page, 'I attached the reminder, can you read it?');
    await expect(page.locator('[data-role="user"]').getByTestId('attachment-chip')).toContainText('Relance_2026-09-22.pdf');
    const bodies = await page.evaluate(() => (window as unknown as { __chatBodies: Record<string, unknown>[] }).__chatBodies);
    expect(Object.keys(bodies.at(-1)!).sort()).toEqual(['locale', 'message', 'pageContext']);
  });
});

test.describe('the panel over a page (demo 7:00, p5)', () => {
  test('knows the page, shows a DeadlineCard with Remind me, and Esc closes it', async ({ page }) => {
    const problems = watchConsole(page);
    await page.goto('/archive?q=URSSAF');
    await page.getByTestId('results-table').waitFor();
    await page.getByRole('button', { name: 'Ask Mona', exact: true }).click();
    await expect(panel(page).getByTestId('page-context')).toHaveText(/^Mona can see: Archive, search “URSSAF”, \d+ results?$/);
    await ask(panel(page), page, "What's due this month?");
    const deadline = panel(page).locator('[data-card="deadline"]').first();
    await expect(deadline).toBeVisible();
    await deadline.getByRole('button', { name: /^Remind me on/ }).click();
    await expect(deadline.getByTestId('reminder-set')).toBeVisible();
    const bodies = await page.evaluate(() => (window as unknown as { __chatBodies: { pageContext: { summary: string } }[] }).__chatBodies);
    expect(bodies.at(-1)!.pageContext.summary).toMatch(/^Archive, search 'URSSAF', \d+ results?$/);
    expect(await serious(page)).toEqual([]);
    await composer(panel(page)).focus();
    await page.keyboard.press('Escape');
    await expect(panel(page)).toBeHidden();
    expect(problems).toEqual([]);
  });
});

test.describe('Chat at 390', () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test('the thread fills the screen, the list is one tap away, and nothing overflows', async ({ page }) => {
    const problems = watchConsole(page);
    await page.goto('/chat');
    await expect(page.getByTestId('conversation-list')).toBeHidden();
    await ask(page, page, 'How much did we pay last year?');
    await ask(page, page, "What's due this month?");
    await expect(page.locator('[data-card="deadline"]').first()).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    expect(await serious(page)).toEqual([]);
    await page.getByRole('button', { name: 'Conversations' }).click();
    await expect(page.getByTestId('conversation-list')).toBeVisible();
    await page.getByTestId('conversation-list').locator('[data-conversation]').last().click();
    await expect(page.getByTestId('conversation-list')).toBeHidden();
    await expect(page.getByTestId('chat-title')).toHaveText('How much did we pay last year?');
    expect(problems).toEqual([]);
  });
});
