import { readFileSync } from 'node:fs';
import { expect, test } from '@playwright/test';
import { DEADLINE, DOC, INTERVIEW } from '../src/test/chatFixtures';

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
