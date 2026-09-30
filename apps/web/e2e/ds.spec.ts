import { expect, test } from '@playwright/test';

test('/dev/ds renders every family without console errors or warnings', async ({ page }) => {
  const problems: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error' || msg.type() === 'warning') problems.push(`${msg.type()}: ${msg.text()}`);
  });
  page.on('pageerror', (err) => problems.push(`pageerror: ${err.message}`));

  await page.goto('/dev/ds');
  const families = [
    'Button', 'Input', 'Select', 'StatusPill', 'ConfidenceMeter', 'Card', 'Dialog', 'Toast', 'MonaAvatar',
    'Citation', 'Icon', 'HandoffIcons', 'ReasonChip', 'CategoryIcon', 'Banner', 'Progress', 'Badge', 'Tag', 'Table', 'Menu',
  ];
  for (const name of families) {
    await expect(page.locator(`section[data-family="${name}"] > div > *`).first()).toBeVisible();
  }

  await page.getByRole('button', { name: 'Open dialog' }).click();
  await expect(page.getByRole('alertdialog')).toBeVisible();
  await page.getByRole('alertdialog').getByRole('button', { name: 'Delete' }).click();
  await page.getByRole('button', { name: 'Actions' }).click();
  await expect(page.getByRole('menuitem', { name: 'Copy name' })).toBeVisible();

  expect(problems).toEqual([]);
});
