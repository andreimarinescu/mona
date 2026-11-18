import { readFileSync } from 'node:fs';
import { expect, test } from '@playwright/test';
import type { RulePreview } from '../src/data/dto';
import { DEADLINE, DOC, INTERVIEW, RULE } from '../src/test/chatFixtures';

const golden: { type: string }[] = JSON.parse(
  readFileSync(new URL('../../../docs/spikes/s5/fixtures/completions-stream-overlay.ui-chunks.json', import.meta.url), 'utf8'),
);

function sse(): string {
  const chunks: unknown[] = [
    { type: 'start', messageId: 'msg_1', messageMetadata: { conversationId: 'cnv_mock' } },
    { type: 'start-step' },
  ];
  for (const c of golden) {
    chunks.push(c);
    if (c.type === 'tool-output-available') {
      chunks.push(
        { type: 'data-doc', id: DOC.id, data: DOC },
        { type: 'data-deadline', id: DEADLINE.id, data: { ...DEADLINE, daysLeft: -2 } },
        { type: 'data-interview', id: INTERVIEW.id, data: INTERVIEW },
      );
    }
  }
  chunks.push({ type: 'finish-step' }, { type: 'finish', finishReason: 'stop', messageMetadata: { reasoningMs: 2400 } });
  return chunks.map((c) => `data: ${JSON.stringify(c)}\n\n`).join('') + 'data: [DONE]\n\n';
}

test.beforeEach(async ({ page }) => {
  await page.route((url) => url.pathname.startsWith('/api/'), (route) => route.fulfill({ status: 404, json: { error: { code: 'not_found', message: 'not mocked' } } }));
  await page.route('**/api/health', (route) => route.fulfill({ json: { status: 'ok', db: 'ok', version: '0.1.0' } }));
});

test('/dev/chat renders reasoning, tool chip, text and data-doc/deadline/interview parts', async ({ page }) => {
  const problems: string[] = [];
  page.on('pageerror', (err) => problems.push(err.message));
  let body: Record<string, unknown> | undefined;
  await page.route('**/api/chat', async (route) => {
    body = route.request().postDataJSON();
    await route.fulfill({
      status: 200,
      headers: { 'content-type': 'text/event-stream', 'x-vercel-ai-ui-message-stream': 'v1' },
      body: sse(),
    });
  });

  await page.goto('/dev/chat');
  await page.getByRole('textbox', { name: 'Write to Mona…' }).fill('What am I looking at?');
  await page.getByRole('button', { name: 'Send' }).click();

  const reply = page.locator('[data-role="assistant"]');
  await expect(reply.locator('[data-testid="thinking"]')).toHaveCount(2);
  await expect(reply.locator('[data-testid="thinking"][data-live="true"]')).toHaveCount(0);
  await expect(reply.locator('[data-testid="tool-chip"][data-tool="get_document"]')).toHaveText('Opened the document');
  await expect(reply.locator('[data-card="doc"]')).toContainText(DOC.title);
  await expect(reply.locator(`[data-card="deadline"][data-id="${DEADLINE.id}"]`)).toContainText(DEADLINE.label);
  await expect(reply.locator('[data-card="deadline"]')).toContainText('Overdue by 2 days');
  await expect(reply.locator('[data-card="interview"] button[data-option]')).toHaveCount(3);
  await expect(reply.locator('[data-testid="mona-text"]')).toContainText('Vous regardez');
  await expect(page).toHaveURL(/\?c=cnv_mock/);
  expect(body).toEqual({
    message: 'What am I looking at?',
    pageContext: { route: '/dev/chat', summary: 'Chat page' },
    locale: 'en',
  });
  expect(problems).toEqual([]);
});

test('/dev/chat sends the page context given in the URL', async ({ page }) => {
  let body: Record<string, unknown> | undefined;
  await page.route('**/api/chat', async (route) => {
    body = route.request().postDataJSON();
    await route.fulfill({
      status: 200,
      headers: { 'content-type': 'text/event-stream', 'x-vercel-ai-ui-message-stream': 'v1' },
      body: sse(),
    });
  });
  await page.goto('/dev/chat?route=%2Fdocuments%2Fdoc_x&summary=Document%20doc_x%2C%20page%201');
  await page.getByRole('textbox', { name: 'Write to Mona…' }).fill('What is this?');
  await page.getByRole('button', { name: 'Send' }).click();
  await expect(page.locator('[data-role="assistant"] [data-testid="mona-text"]')).toBeVisible();
  expect(body?.pageContext).toEqual({ route: '/documents/doc_x', summary: 'Document doc_x, page 1' });
  await expect(page).toHaveURL(/route=%2Fdocuments%2Fdoc_x/);
});

test('a rename ask: the rulePreview card shows old → new names, Apply, then Undo restores the old names (A62)', async ({ page }) => {
  const problems: string[] = [];
  page.on('pageerror', (err) => problems.push(err.message));
  const folder = ['LMNP', 'Angers-Strasbourg', 'Banque', '2026'];
  const names = [
    ['2026-01-16_Hello-bank_Releve-de-compte.pdf', '2026-01-HB-LMNP-Janvier.pdf'],
    ['2026-02-16_Hello-bank_Releve-de-compte.pdf', '2026-02-HB-LMNP-Fevrier.pdf'],
  ];
  const groupId = 'grp_01j9zq3k8e6y4v2m7c5r1t0b9b';
  const rule = { ...RULE, name: 'Rename Hello bank Bank', state: 'draft' as const, enabled: false, source: 'correction' as const };
  const moves = names.map(([old, next], i) => ({ documentId: `doc_01j9zq3k8f7z5w3n8d6s2v1c0${i}`, title: `Hello bank statement ${i + 1}`, from: folder, fromFileName: old!, to: folder, toFileName: next! }));
  const preview = (applied: boolean): RulePreview => ({
    rule: { ...rule, state: applied ? 'active' : 'draft', enabled: applied },
    moves,
    movesTotal: 2,
    stays: [],
    staysTotal: 0,
    applied,
    groupId: applied ? groupId : null,
  });
  let applied = false;
  const calls: string[] = [];
  await page.route(`**/api/rules/${RULE.id}/preview**`, (route) => route.fulfill({ json: preview(applied) }));
  await page.route(`**/api/rules/${RULE.id}/apply`, (route) => {
    calls.push('apply');
    applied = true;
    return route.fulfill({ json: { preview: preview(true), groupId, moved: 2, unchanged: 0, failed: [] } });
  });
  await page.route(`**/api/journal/groups/${groupId}/undo`, (route) => {
    calls.push('undo');
    applied = false;
    return route.fulfill({ json: { groupId: 'grp_01j9zq3k8e6y4v2m7c5r1t0b9c', undone: [], skipped: [], entries: [], ruleStates: [{ ruleId: RULE.id, state: 'draft' }] } });
  });
  await page.route('**/api/chat', (route) => {
    const chunks: unknown[] = [
      { type: 'start', messageId: 'msg_2', messageMetadata: { conversationId: 'cnv_rename' } },
      { type: 'start-step' },
      { type: 'tool-input-available', toolCallId: 'call_1', toolName: 'rename_documents', input: {}, dynamic: true },
      { type: 'tool-output-available', toolCallId: 'call_1', output: { status: 'completed' }, dynamic: true },
      { type: 'data-rulePreview', id: RULE.id, data: preview(false) },
      { type: 'text-start', id: 't1' },
      { type: 'text-delta', id: 't1', delta: 'Iată noile nume. Le aplic când îmi spui.' },
      { type: 'text-end', id: 't1' },
      { type: 'finish-step' },
      { type: 'finish', finishReason: 'stop' },
    ];
    return route.fulfill({
      status: 200,
      headers: { 'content-type': 'text/event-stream', 'x-vercel-ai-ui-message-stream': 'v1' },
      body: chunks.map((c) => `data: ${JSON.stringify(c)}\n\n`).join('') + 'data: [DONE]\n\n',
    });
  });

  await page.goto('/dev/chat');
  await page.getByRole('textbox', { name: 'Write to Mona…' }).fill('poți să redenumești toate extrasele de la Hello bank în formatul 2026-01-HB-LMNP-Ianuarie?');
  await page.getByRole('button', { name: 'Send' }).click();

  const reply = page.locator('[data-role="assistant"]');
  await expect(reply.locator('[data-testid="tool-chip"][data-tool="rename_documents"]')).toHaveText('Prepared the new names');
  const card = reply.locator(`[data-card="rulePreview"][data-id="${RULE.id}"]`);
  await expect(card).toHaveAttribute('data-applied', 'false');
  await expect(card).toContainText('2 move · 0 stay');
  for (const [old, next] of names) await expect(card).toContainText(`${old} → ${next}`);

  await card.getByRole('button', { name: 'Apply' }).click();
  await expect(card).toHaveAttribute('data-applied', 'true');
  await expect(card.getByRole('status')).toHaveText('Applied: 2 documents moved');

  const toast = page.getByTestId('toast-region').getByRole('status').filter({ hasText: 'Rule applied: moved 2 documents' });
  await toast.getByRole('button', { name: 'Undo' }).click();
  await expect(card).toHaveAttribute('data-applied', 'false');
  await expect(card).toHaveAttribute('data-state', 'draft');
  await expect(card.getByRole('button', { name: 'Apply' })).toBeEnabled();
  for (const [old, next] of names) await expect(card).toContainText(`${old} → ${next}`);
  expect(calls).toEqual(['apply', 'undo']);
  expect(problems).toEqual([]);
});
