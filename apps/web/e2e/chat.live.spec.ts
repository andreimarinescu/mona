import { mkdirSync, writeFileSync } from 'node:fs';
import { expect, test, type Page } from '@playwright/test';

// Needs the compose stack with Hermes: E2E_BASE_URL=<web> MONA_LIVE=1.
test.skip(!process.env.MONA_LIVE, 'live Hermes stack not requested (MONA_LIVE=1)');
test.describe.configure({ mode: 'serial', timeout: 240_000 });

const TURN_TIMEOUT = 90_000;

async function send(page: Page, text: string) {
  await page.getByRole('textbox', { name: 'Ask Mona…' }).fill(text);
  await page.evaluate(() => {
    const w = window as unknown as { s5: Record<string, number> };
    const before = document.querySelectorAll('[data-role="assistant"]').length;
    const t0 = performance.now();
    const marks: Record<string, string> = {
      reasoning: '[data-testid="thinking"] p',
      text: '[data-testid="mona-text"]',
      tool: '[data-testid="tool-chip"]',
    };
    w.s5 = {};
    new MutationObserver(() => {
      const scope = document.querySelectorAll('[data-role="assistant"]')[before];
      if (!scope) return;
      for (const [key, selector] of Object.entries(marks)) {
        if (w.s5[key] === undefined && scope.querySelector(selector)?.textContent?.trim())
          w.s5[key] = Math.round(performance.now() - t0);
      }
    }).observe(document.body, { subtree: true, childList: true, characterData: true });
  });
  await page.getByRole('button', { name: 'Send' }).click();
}

async function timings(page: Page) {
  return page.evaluate(() => (window as unknown as { s5: Record<string, number> }).s5);
}

async function waitForTurnEnd(page: Page) {
  await expect(page.locator('[data-chat-status="ready"]')).toBeVisible({ timeout: TURN_TIMEOUT });
  await expect(page).toHaveURL(/[?&]c=cnv_/);
}

test('first reasoning token within 10 s @timing', async ({ page }) => {
  await page.goto('/dev/chat');
  await send(page, 'Find the URSSAF letter');
  await expect(page.locator('[data-testid="mona-text"]').first()).not.toBeEmpty({ timeout: TURN_TIMEOUT });
  const t = await timings(page);
  const label = process.env.S5_TIMING_LABEL ?? 'run';
  mkdirSync('test-results', { recursive: true });
  writeFileSync(`test-results/s5-timing-${label}.json`, JSON.stringify(t));
  console.log(`S5 timing ${label}: ${JSON.stringify(t)}`);
  expect(t.reasoning).toBeLessThanOrEqual(10_000);
});

test('URSSAF search streams thinking, text, a tool chip and a doc card; AGIPI interview; reload', async ({
  page,
}) => {
  const problems: string[] = [];
  page.on('pageerror', (err) => problems.push(err.message));

  await page.goto('/dev/chat');
  await send(page, 'Find the URSSAF letter');
  const first = page.locator('[data-role="assistant"]').first();
  await expect(first.locator('[data-testid="thinking"]').first()).toBeVisible({ timeout: TURN_TIMEOUT });
  await expect(first.locator('[data-testid="tool-chip"]').first()).toBeVisible({ timeout: TURN_TIMEOUT });
  await expect(first.locator('[data-card="doc"][data-id="doc_urssaf_q3"]')).toBeVisible({ timeout: TURN_TIMEOUT });
  await expect(first.locator('[data-testid="mona-text"]').first()).not.toBeEmpty({ timeout: TURN_TIMEOUT });
  await waitForTurnEnd(page);
  await expect(first.locator('[data-card="doc"]').first()).toContainText('URSSAF appel de cotisation T3');

  await send(page, 'Start an interview about AGIPI');
  const second = page.locator('[data-role="assistant"]').nth(1);
  const card = second.locator('[data-card="interview"]');
  await expect(card).toBeVisible({ timeout: TURN_TIMEOUT });
  await expect(card.locator('button[data-option]')).toHaveCount(3);
  await waitForTurnEnd(page);

  const url = page.url();
  const docCards = await page.locator('[data-card="doc"]').count();
  await page.goto(url);
  await expect(page.locator('[data-role="user"]')).toHaveCount(2);
  await expect(page.locator('[data-card="doc"][data-id="doc_urssaf_q3"]').first()).toBeVisible();
  await expect(page.locator('[data-card="doc"]')).toHaveCount(docCards);
  await expect(page.locator('[data-card="interview"] button[data-option]')).toHaveCount(3);
  await expect(page.locator('[data-testid="tool-chip"]').first()).toBeVisible();
  await expect(page.locator('[data-testid="thinking"]').first()).toBeVisible();
  expect(problems).toEqual([]);
});
