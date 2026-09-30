import { readFileSync } from 'node:fs';
import { expect, test } from '@playwright/test';

const golden: { type: string }[] = JSON.parse(
  readFileSync(new URL('../../../docs/spikes/s5/fixtures/completions-stream-overlay.ui-chunks.json', import.meta.url), 'utf8'),
);

const doc = {
  id: 'doc_urssaf_q3',
  title: 'URSSAF appel de cotisation T3',
  fileName: '2026-09-22_URSSAF_Appel_T3.pdf',
  path: ['Cabinet Marchand', '2026', 'Cotisations sociales'],
  entityName: 'Cabinet Marchand',
  categoryId: 'tax',
  date: '2026-09-22',
  amount: { value: 1284, currency: 'EUR' },
  dueDate: '2026-10-14',
  status: 'filed',
  confidence: 0.93,
};
const deadline = {
  id: 'ddl_1',
  documentId: 'doc_urssaf_q3',
  label: 'URSSAF 3e trimestre',
  entityId: 'ent_1',
  entityName: 'Cabinet Marchand',
  dueDate: '2026-10-14',
  amount: { value: 1284, currency: 'EUR' },
  status: 'open',
  daysLeft: -2,
  reminder: null,
};
const interview = {
  id: 'int_1',
  status: 'ready',
  questions: [
    {
      id: 'qst_1',
      question: 'Who holds the AGIPI contracts?',
      lang: 'en',
      affectsCount: 2,
      options: [
        { id: 'opt_1', label: 'Always personal', suggested: true },
        { id: 'opt_2', label: 'The practice' },
        { id: 'opt_3', label: 'Shared' },
      ],
    },
  ],
};

function sse(): string {
  const chunks: unknown[] = [
    { type: 'start', messageId: 'msg_1', messageMetadata: { conversationId: 'cnv_mock' } },
    { type: 'start-step' },
  ];
  for (const c of golden) {
    chunks.push(c);
    if (c.type === 'tool-output-available') {
      chunks.push(
        { type: 'data-doc', id: doc.id, data: doc },
        { type: 'data-deadline', id: deadline.id, data: deadline },
        { type: 'data-interview', id: interview.id, data: interview },
      );
    }
  }
  chunks.push({ type: 'finish-step' }, { type: 'finish', finishReason: 'stop', messageMetadata: { reasoningMs: 2400 } });
  return chunks.map((c) => `data: ${JSON.stringify(c)}\n\n`).join('') + 'data: [DONE]\n\n';
}

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
  await page.getByRole('textbox', { name: 'Ask Mona…' }).fill('What am I looking at?');
  await page.getByRole('button', { name: 'Send' }).click();

  const reply = page.locator('[data-role="assistant"]');
  await expect(reply.locator('[data-testid="thinking"]')).toHaveCount(2);
  await expect(reply.locator('[data-testid="thinking"]').first()).toContainText('Thought for 2 seconds');
  await expect(reply.locator('[data-testid="tool-chip"][data-tool="get_document"]')).toHaveText('Opened the document');
  await expect(reply.locator('[data-card="doc"]')).toContainText('URSSAF appel de cotisation T3');
  await expect(reply.locator('[data-card="deadline"][data-id="ddl_1"]')).toContainText('URSSAF 3e trimestre');
  await expect(reply.locator('[data-card="deadline"]')).toContainText('Overdue');
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
  await page.getByRole('textbox', { name: 'Ask Mona…' }).fill('What is this?');
  await page.getByRole('button', { name: 'Send' }).click();
  await expect(page.locator('[data-role="assistant"] [data-testid="mona-text"]')).toBeVisible();
  expect(body?.pageContext).toEqual({ route: '/documents/doc_x', summary: 'Document doc_x, page 1' });
  await expect(page).toHaveURL(/route=%2Fdocuments%2Fdoc_x/);
});
