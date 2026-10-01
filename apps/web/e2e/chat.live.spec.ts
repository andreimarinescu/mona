import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { expect, test, type Page } from '@playwright/test';

// Needs the compose stack with Hermes and `python -m tests.live_fixtures` output in MONA_LIVE_FIXTURES:
// E2E_BASE_URL=<web> MONA_LIVE=1 MONA_LIVE_FIXTURES=<json> MONA_OWNER_PASSWORD=<the seeded password>.
test.skip(!process.env.MONA_LIVE, 'live Hermes stack not requested (MONA_LIVE=1)');
test.describe.configure({ mode: 'serial', timeout: 240_000 });

const TURN_TIMEOUT = 120_000;
const fixtures: Record<string, string> = process.env.MONA_LIVE_FIXTURES
  ? JSON.parse(readFileSync(process.env.MONA_LIVE_FIXTURES, 'utf8'))
  : {};
const timings: Record<string, Record<string, number>> = {};

const STOPWORDS = {
  en: ['the', 'and', 'is', 'of', 'to', 'for', 'you', 'your', 'this', 'it', 'was', 'with'],
  fr: ['le', 'la', 'les', 'des', 'et', 'est', 'pour', 'vous', 'une', 'du', 'cette', 'avec'],
};

function language(text: string): 'en' | 'fr' {
  const words = text.toLowerCase().match(/[\p{L}']+/gu) ?? [];
  const score = (l: 'en' | 'fr') => words.filter((w) => STOPWORDS[l].includes(w)).length;
  return score('fr') > score('en') ? 'fr' : 'en';
}

async function send(page: Page, text: string) {
  await page.getByRole('textbox', { name: 'Ask Mona…' }).fill(text);
  await page.evaluate(() => {
    const w = window as unknown as { turn: Record<string, number> };
    const before = document.querySelectorAll('[data-role="assistant"]').length;
    const t0 = performance.now();
    const marks: Record<string, string> = {
      reasoning: '[data-testid="thinking"] p',
      text: '[data-testid="mona-text"]',
      tool: '[data-testid="tool-chip"]',
    };
    w.turn = {};
    new MutationObserver(() => {
      const scope = document.querySelectorAll('[data-role="assistant"]')[before];
      if (!scope) return;
      for (const [key, selector] of Object.entries(marks)) {
        if (w.turn[key] === undefined && scope.querySelector(selector)?.textContent?.trim())
          w.turn[key] = Math.round(performance.now() - t0);
      }
    }).observe(document.body, { subtree: true, childList: true, characterData: true });
  });
  await page.getByRole('button', { name: 'Send' }).click();
}

async function turn(page: Page, name: string, text: string) {
  await send(page, text);
  await expect(page.locator('[data-chat-status="ready"]')).toBeVisible({ timeout: TURN_TIMEOUT });
  await expect(page).toHaveURL(/[?&]c=cnv_/);
  timings[name] = await page.evaluate(() => (window as unknown as { turn: Record<string, number> }).turn);
  const reply = page.locator('[data-role="assistant"]').last();
  await expect(reply.locator('[data-testid="mona-text"]').first()).not.toBeEmpty();
  return reply;
}

async function tools(reply: ReturnType<Page['locator']>) {
  return reply.locator('[data-testid="tool-chip"]').evaluateAll((els) => els.map((e) => e.getAttribute('data-tool')));
}

// The web has no unlock screen or CSRF middleware yet (L3), so the test unlocks and adds the token.
test.beforeEach(async ({ page }) => {
  const res = await page.request.post('/api/auth/unlock', { data: { password: process.env.MONA_OWNER_PASSWORD } });
  expect(res.ok()).toBe(true);
  const { csrfToken } = (await res.json()) as { csrfToken: string };
  await page.route('**/api/chat', (route) =>
    route.continue({ headers: { ...route.request().headers(), 'x-csrf-token': csrfToken } }),
  );
});

test.afterAll(() => {
  const label = process.env.LIVE_TIMING_LABEL ?? 'run';
  mkdirSync('test-results', { recursive: true });
  writeFileSync(`test-results/live-timings-${label}.json`, JSON.stringify(timings, null, 2));
  console.log(`live timings ${label}: ${JSON.stringify(timings)}`);
});

test('AGIPI last year: one sum_amounts call, the right total, doc cards; reload keeps them', async ({ page }) => {
  const problems: string[] = [];
  page.on('pageerror', (err) => problems.push(err.message));
  await page.goto('/dev/chat');
  const reply = await turn(page, 'agipi', 'How much did we pay AGIPI last year?');
  const called = await tools(reply);
  console.log(`agipi tools: ${JSON.stringify(called)}`);
  expect(called.filter((t) => t === 'sum_amounts')).toHaveLength(1);
  await expect(reply.locator('[data-testid="mona-text"]').last()).toContainText(/1[\s\u00a0\u202f.,]?000/);
  const cards = reply.locator('[data-card="doc"]');
  expect(await cards.count()).toBeGreaterThan(0);
  const ids = await cards.evaluateAll((els) => els.map((e) => e.getAttribute('data-id')));
  expect(ids.every((id) => id === fixtures.agipi_a || id === fixtures.agipi_b)).toBe(true);

  const shown = await page.locator('[data-card="doc"]').count();
  await page.goto(page.url());
  await expect(page.locator('[data-role="user"]')).toHaveCount(1);
  await expect(page.locator('[data-card="doc"]')).toHaveCount(shown);
  await expect(page.locator('[data-testid="tool-chip"][data-tool="sum_amounts"]')).toHaveCount(1);
  expect(problems).toEqual([]);
});

test("what's due this month: a deadline card", async ({ page }) => {
  await page.goto('/dev/chat');
  const reply = await turn(page, 'due', "What's due this month?");
  console.log(`due tools: ${JSON.stringify(await tools(reply))}`);
  await expect(reply.locator('[data-card="deadline"]').first()).toBeVisible();
  const ids = await reply.locator('[data-card="deadline"]').evaluateAll((els) => els.map((e) => e.getAttribute('data-id')));
  expect(ids).toContain(fixtures.ddl_urssaf);
});

test('page context from /documents/:id is honoured, and an English question about a French document gets English', async ({
  page,
}) => {
  const id = fixtures.urssaf;
  await page.goto(`/dev/chat?route=${encodeURIComponent(`/documents/${id}`)}&summary=${encodeURIComponent(`Document ${id}, page 1`)}`);
  const reply = await turn(page, 'page', 'What is this document, and how much is due?');
  console.log(`page tools: ${JSON.stringify(await tools(reply))}`);
  const text = (await reply.locator('[data-testid="mona-text"]').allTextContents()).join(' ');
  await expect(reply.locator(`[data-card="doc"][data-id="${id}"]`).first()).toBeVisible();
  expect(text).toMatch(/URSSAF/);
  expect(text).toMatch(/1[\s\u00a0\u202f.,]?284/);
  expect(language(text)).toBe('en');
});

test('a French prompt gets a French reply', async ({ page }) => {
  await page.goto('/dev/chat');
  const reply = await turn(page, 'french', "Combien avons-nous payé à AGIPI l'année dernière ?");
  const text = (await reply.locator('[data-testid="mona-text"]').allTextContents()).join(' ');
  console.log(`french tools: ${JSON.stringify(await tools(reply))}; reply: ${text.slice(0, 120)}`);
  expect(language(text)).toBe('fr');
});

test('move the URSSAF letter to the SCI: correct_document, a card, and an undo that restores it', async ({ page }) => {
  const id = fixtures.urssaf;
  const folder = async () =>
    ((await (await page.request.get(`/api/documents/${id}`)).json()) as { path: string[] }).path[0];
  expect(await folder()).toBe('Cabinet Marchand');
  await page.goto('/dev/chat');
  const moved = await turn(page, 'move', 'Move the URSSAF letter to the SCI.');
  const called = await tools(moved);
  console.log(`move tools: ${JSON.stringify(called)}`);
  expect(called).toContain('correct_document');
  await expect(moved.locator(`[data-card="doc"][data-id="${id}"]`).first()).toBeVisible();
  expect(await folder()).toBe(fixtures.sci_folder);
  const undone = await turn(page, 'undo', 'Undo that, please.');
  const undoTools = await tools(undone);
  console.log(`undo tools: ${JSON.stringify(undoTools)}`);
  expect(undoTools).toContain('undo');
  expect(await folder()).toBe('Cabinet Marchand');
});
