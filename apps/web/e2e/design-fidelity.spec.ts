import { expect, test, type Page } from '@playwright/test';

const PDF = (text: string) => Buffer.from(`%PDF-1.4\n${text}\n%%EOF`);
const dir = process.env.SHOTS_DIR;

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('mona.msw', '1');
    localStorage.setItem('mona.msw.step', '600000');
  });
});

async function startBatch(page: Page, names = ['invoice_a.pdf', 'invoice_b.pdf', 'scan_c.pdf']) {
  await page.goto('/intake');
  await page.getByTestId('file-input').setInputFiles(names.map((name) => ({ name, mimeType: 'application/pdf', buffer: PDF(name) })));
  await page.getByTestId('batch-progress').waitFor();
  await page.locator('[data-step-dot="classifying"]').first().waitFor();
}

const box = async (loc: ReturnType<Page['locator']>) => (await loc.boundingBox())!;

const LAYOUTS = [
  { name: 'desktop EN', width: 1440, height: 900, locale: 'en' },
  { name: 'laptop FR', width: 1024, height: 768, locale: 'fr' },
  { name: 'mobile RO', width: 390, height: 844, locale: 'ro' },
  { name: 'mobile FR', width: 390, height: 844, locale: 'fr' },
  { name: 'tablet EN', width: 768, height: 1024, locale: 'en' },
  { name: 'wide RO', width: 1600, height: 900, locale: 'ro' },
];

test.describe('intake stepper labels (walkthrough 1 #5)', () => {
  for (const { name, width, height, locale } of LAYOUTS) {
    test(`each header label is centred over its dot and none overlap: ${name}`, async ({ page }) => {
      await page.addInitScript((l) => localStorage.setItem('mona.msw.locale', l), locale);
      await page.setViewportSize({ width, height });
      await startBatch(page);
      const labels = page.getByTestId('step-header').locator('li');
      await expect(labels).toHaveCount(5);
      const dots = page.locator('tbody tr').first().locator('[data-step-dot]');
      const rects: { left: number; right: number }[] = [];
      for (let i = 0; i < 5; i++) {
        const label = await box(labels.nth(i));
        const text = labels.nth(i).locator('xpath=.');
        const range = await text.evaluate((el) => {
          const r = document.createRange();
          r.selectNodeContents(el);
          const b = r.getBoundingClientRect();
          return { left: b.left, right: b.right };
        });
        const dot = await box(dots.nth(i));
        expect(Math.abs(label.x + label.width / 2 - (dot.x + dot.width / 2)), `${i}`).toBeLessThan(1);
        rects.push(range);
      }
      for (let i = 1; i < 5; i++) expect(rects[i]!.left, `label ${i} clear of the one before`).toBeGreaterThanOrEqual(rects[i - 1]!.right);
    });
  }

  test('a dot shows its step name on hover, on Intake and on the Document page', async ({ page }) => {
    await startBatch(page);
    await page.locator('tbody tr').first().locator('[data-step-dot="classifying"]').hover();
    await expect(page.getByRole('tooltip')).toHaveText('Classifying');
    await page.mouse.move(0, 0);
    await expect(page.getByRole('tooltip')).toHaveCount(0);

    const id = await page.evaluate(() => {
      const world = (window as unknown as { __mock: { docs: Map<string, { summary: { id: string; originalName: string } }> } }).__mock;
      return [...world.docs.values()].find((d) => d.summary.originalName === 'invoice_a.pdf')!.summary.id;
    });
    await page.evaluate((target) => {
      history.pushState({}, '', `/documents/${target}`);
      dispatchEvent(new PopStateEvent('popstate'));
    }, id);
    const viewer = page.getByTestId('viewer-processing');
    await expect(viewer).toBeVisible();
    await viewer.locator('[data-step-dot="ocr"]').hover();
    await expect(page.getByRole('tooltip')).toHaveText('OCR');
  });
});

test.describe('unlock layout (walkthrough 1 #7)', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem('mona.msw.locked', '1'));
  });

  for (const [width, height] of [[1440, 900], [2000, 1050]] as const) {
    test(`keeps p1's proportions at ${width} px`, async ({ page }) => {
      await page.setViewportSize({ width, height });
      await page.goto('/unlock');
      await page.getByLabel('Password').waitFor();
      const u = width / 1500;
      const headline = page.getByTestId('unlock-headline');
      const fontSize = await headline.evaluate((el) => parseFloat(getComputedStyle(el).fontSize));
      expect(fontSize).toBeCloseTo(64 * u, 0);
      expect((await box(page.getByTestId('unlock-form'))).width).toBeCloseTo(544 * u, 0);
      expect((await box(headline)).x).toBeCloseTo(75 * u, 0);
      const arches = page.getByTestId('unlock-arches').locator('> span');
      await expect(arches).toHaveCount(5);
      expect((await box(arches.first())).width).toBeCloseTo(110 * u, 0);
      expect((await box(page.getByTestId('unlock-dot'))).width).toBeCloseTo(27 * u, 0);
      await expect(page.getByTestId('unlock-footer')).toHaveText('Mona runs on this computer. Unlocking doesn’t use the internet.');
      const scroll = await page.evaluate(() => ({ h: document.documentElement.scrollHeight, w: document.documentElement.scrollWidth }));
      expect(scroll).toEqual({ h: height, w: width });
    });
  }

  test('the card, headline and footer stay readable and unclipped on a phone', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/unlock');
    await page.getByLabel('Password').waitFor();
    await expect(page.getByTestId('unlock-footer')).toBeVisible();
    const form = await box(page.getByTestId('unlock-form'));
    expect(form.x).toBeGreaterThanOrEqual(0);
    expect(form.x + form.width).toBeLessThanOrEqual(390);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
  });
});

async function stemEdges(page: Page, selector: string): Promise<{ partial: number; ink: number }> {
  const png = (await page.locator(selector).first().screenshot()).toString('base64');
  return page.evaluate(async (data) => {
    const img = new Image();
    img.src = `data:image/png;base64,${data}`;
    await img.decode();
    const canvas = document.createElement('canvas');
    canvas.width = img.width;
    canvas.height = img.height;
    const ctx = canvas.getContext('2d')!;
    ctx.drawImage(img, 0, 0);
    const y = Math.floor(img.height * 0.8);
    const row = ctx.getImageData(0, y, Math.floor(img.width * 0.28), 1).data;
    const px = (i: number) => `${row[i * 4]},${row[i * 4 + 1]},${row[i * 4 + 2]}`;
    const bg = '251,247,240';
    let ink = 0;
    let partial = 0;
    for (let i = 0; i < row.length / 4; i++) {
      if (px(i) === bg) continue;
      if (px(i) === '169,79,51') ink++;
      else partial++;
    }
    return { partial, ink };
  }, png);
}

test.describe('logo crispness (walkthrough 1 #6)', () => {
  for (const dpr of [1, 2]) {
    test(`the symbol's stems land on whole device pixels at DPR ${dpr}, on Unlock and in the Sidebar`, async ({ browser }) => {
      const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: dpr });
      const page = await ctx.newPage();
      await page.addInitScript(() => {
        localStorage.setItem('mona.msw', '1');
        localStorage.setItem('mona.msw.locked', '1');
      });
      await page.goto('/unlock');
      await page.getByLabel('Password').waitFor();
      const onUnlock = await stemEdges(page, 'main svg[data-logo-stroke]');
      expect(onUnlock.partial).toBe(0);
      expect(onUnlock.ink).toBe(12 * dpr);
      await page.getByLabel('Password').fill('correct horse');
      await page.getByRole('button', { name: 'Unlock' }).click();
      await page.locator('aside svg[data-logo-stroke]').waitFor();
      const inSidebar = await stemEdges(page, 'aside svg[data-logo-stroke]');
      expect(inSidebar.partial).toBe(0);
      expect(inSidebar.ink).toBe(9 * dpr);
      await ctx.close();
    });
  }
});

test.describe('chat mock', () => {
  test('the debrief card says "Affects 3 documents" for the 3 letters it names', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('mona.msw.step', '150');
      localStorage.setItem('mona.msw.chatDelay', '10');
    });
    await startBatch(page, ['scan_per_1.pdf', 'scan_vie_1.pdf', 'scan_per_2.pdf', 'invoice_x.pdf']);
    await page.getByRole('button', { name: 'Answer now' }).click({ timeout: 20_000 });
    const card = page.locator('[role="complementary"][aria-label="Mona"] [data-card="interview"]');
    await card.waitFor();
    await expect(card.getByTestId('open-question')).toContainText('I found 3 letters');
    await expect(card).toContainText('Affects 3 documents');
    const family = await card.getByTestId('open-question').locator('p').first().evaluate((el) => getComputedStyle(el).fontFamily);
    expect(family).toContain('Fraunces');
  });
});

test.describe('screenshots next to the design pages', () => {
  test.skip(!dir, 'set SHOTS_DIR to write the screenshots');
  for (const [width, height] of [[1440, 900], [2000, 1050]] as const) {
    test(`unlock and intake at ${width}`, async ({ page }) => {
      await page.setViewportSize({ width, height });
      await page.addInitScript(() => localStorage.setItem('mona.msw.locked', '1'));
      await page.goto('/unlock');
      await page.getByLabel('Password').waitFor();
      await page.waitForTimeout(500);
      await page.screenshot({ path: `${dir}/unlock-${width}.png` });
      await page.getByLabel('Password').fill('correct horse');
      await page.getByRole('button', { name: 'Unlock' }).click();
      await page.getByTestId('mona-brief').waitFor();
      await page.evaluate(() => localStorage.setItem('mona.msw.step', '700'));
      await page.getByRole('navigation').getByRole('link', { name: 'Intake' }).click();
      await page.getByTestId('file-input').setInputFiles(['invoice_a.pdf', 'invoice_b.pdf', 'scan_c.pdf', 'blurry_d.pdf', 'invoice_e.pdf', 'invoice_f.pdf'].map((n) => ({ name: n, mimeType: 'application/pdf', buffer: PDF(n) })));
      await page.getByTestId('batch-progress').waitFor();
      await page.waitForTimeout(2600);
      await page.screenshot({ path: `${dir}/intake-${width}.png` });
    });
  }
});
