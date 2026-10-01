import { expect, test } from '@playwright/test';

// The real stack, no MSW and no injected headers: E2E_BASE_URL=<web> MONA_LIVE=1 MONA_OWNER_PASSWORD=<the seeded password>.
test.skip(!process.env.MONA_LIVE || !process.env.E2E_BASE_URL, 'live stack not requested (MONA_LIVE=1 and E2E_BASE_URL)');
test.describe.configure({ timeout: 240_000 });

test('unlock through the UI, then a turn from the chat page carries the CSRF token and gets a reply', async ({ page }) => {
  await page.goto('/chat');
  await expect(page).toHaveURL(/\/unlock\?next=%2Fchat/);
  await page.getByLabel('Password').fill(process.env.MONA_OWNER_PASSWORD ?? '');
  await page.getByRole('button', { name: 'Unlock' }).click();
  await expect(page).toHaveURL(/\/chat$/);

  const posted = page.waitForResponse((r) => new URL(r.url()).pathname === '/api/chat' && r.request().method() === 'POST');
  await page.getByRole('textbox', { name: 'Write to Mona…' }).fill("What's due this month?");
  await page.getByRole('button', { name: 'Send' }).click();
  const res = await posted;
  expect(await res.request().headerValue('x-csrf-token')).toMatch(/\S/);
  expect(res.status()).toBe(200);

  await expect(page).toHaveURL(/\/chat\/cnv_/, { timeout: 120_000 });
  await expect(page.locator('[data-chat-status="ready"]')).toBeVisible({ timeout: 120_000 });
  await expect(page.getByTestId('chat-error')).toHaveCount(0);
  await expect(page.locator('[data-role="assistant"]').last().locator('[data-testid="mona-text"]').first()).not.toBeEmpty();
});
