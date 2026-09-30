import assert from 'node:assert/strict';
import { mkdirSync, mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';
import { checkI18n } from './i18n-check.mjs';

function fixture({ en, fr = en, ro = en, source = '' }) {
  const dir = mkdtempSync(join(tmpdir(), 'i18n-'));
  mkdirSync(join(dir, 'i18n'));
  for (const [l, v] of Object.entries({ en, fr, ro })) writeFileSync(join(dir, 'i18n', `${l}.json`), JSON.stringify(v));
  writeFileSync(join(dir, 'App.tsx'), source);
  return { localesDir: join(dir, 'i18n'), srcDir: dir };
}

const en = { a: { b: 'B' }, items_one: 'item', items_other: 'items' };

test('passes when locales agree and literal keys exist', () => {
  const src = `t('a.b'); t("items", { count: 2 }); <Trans i18nKey="a.b" />; t(\`dyn.\${x}\`)`;
  assert.deepEqual(checkI18n(fixture({ en, source: src })), []);
});

test('fails when fr or ro lacks an en key', () => {
  const problems = checkI18n(fixture({ en, fr: { a: {}, items_one: 'x', items_other: 'y' } }));
  assert.deepEqual(problems, ['fr.json is missing "a.b"']);
});

test('fails when a locale has a key en lacks', () => {
  const problems = checkI18n(fixture({ en, ro: { ...en, extra: 'x' } }));
  assert.deepEqual(problems, ['ro.json has "extra", which en.json lacks']);
});

test('fails on unknown literal t() and i18nKey keys', () => {
  const problems = checkI18n(fixture({ en, source: `t('a.c'); <Trans i18nKey={"nope"} />` }));
  assert.deepEqual(problems, ['App.tsx uses "a.c", which en.json lacks', 'App.tsx uses "nope", which en.json lacks']);
});
