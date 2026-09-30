import assert from 'node:assert/strict';
import { mkdirSync, mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';
import { checkI18n } from './i18n-check.mjs';

const en = { a: { b: 'B' }, items_one: 'item', items_other: 'items' };
const fr = { a: { b: 'B' }, items_one: 'article', items_many: "d'articles", items_other: 'articles' };
const ro = { a: { b: 'B' }, items_one: 'articol', items_few: 'articole', items_other: 'de articole' };

function fixture({ en: e = en, fr: f = fr, ro: r = ro, source = '' }) {
  const dir = mkdtempSync(join(tmpdir(), 'i18n-'));
  mkdirSync(join(dir, 'i18n'));
  for (const [l, v] of Object.entries({ en: e, fr: f, ro: r })) writeFileSync(join(dir, 'i18n', `${l}.json`), JSON.stringify(v));
  writeFileSync(join(dir, 'App.tsx'), source);
  return { localesDir: join(dir, 'i18n'), srcDir: dir };
}

test('passes when locales agree and literal keys exist', () => {
  const src = `t('a.b'); t("items", { count: 2 }); <Trans i18nKey="a.b" />; t(\`dyn.\${x}\`)`;
  assert.deepEqual(checkI18n(fixture({ source: src })), []);
});

test('accepts each locale its own CLDR plural categories', () => {
  assert.deepEqual(checkI18n(fixture({})), []);
});

test('fails when fr or ro lacks an en key', () => {
  const problems = checkI18n(fixture({ fr: { ...fr, a: {} } }));
  assert.deepEqual(problems, ['fr.json is missing "a.b"']);
});

test('fails when a locale has a key en lacks', () => {
  const problems = checkI18n(fixture({ ro: { ...ro, extra: 'x' } }));
  assert.deepEqual(problems, ['ro.json has "extra", which en.json lacks']);
});

test('fails on unknown literal t() and i18nKey keys', () => {
  const problems = checkI18n(fixture({ source: `t('a.c'); <Trans i18nKey={"nope"} />` }));
  assert.deepEqual(problems, ['App.tsx uses "a.c", which en.json lacks', 'App.tsx uses "nope", which en.json lacks']);
});

test('fr requires _many and ro requires _few', () => {
  const { items_many: _m, ...frLess } = fr;
  const { items_few: _f, ...roLess } = ro;
  assert.deepEqual(checkI18n(fixture({ fr: frLess })), ['fr.json is missing "items_many"']);
  assert.deepEqual(checkI18n(fixture({ ro: roLess })), ['ro.json is missing "items_few"']);
});

test('rejects a plural category the locale does not use', () => {
  assert.deepEqual(checkI18n(fixture({ en: { ...en, items_many: 'x' } })), [
    'en.json has "items_many", which is not a plural category of en (one/other)',
  ]);
  assert.deepEqual(checkI18n(fixture({ fr: { ...fr, items_few: 'x' } })), [
    'fr.json has "items_few", which is not a plural category of fr (one/many/other)',
  ]);
  assert.deepEqual(checkI18n(fixture({ ro: { ...ro, items_many: 'x' } })), [
    'ro.json has "items_many", which is not a plural category of ro (one/few/other)',
  ]);
});

test('fails when a plural key exists in one locale only', () => {
  const { items_one: _o, items_many: _m, items_other: _t, ...frNone } = fr;
  assert.deepEqual(checkI18n(fixture({ fr: frNone })), ['fr.json is missing "items" plural forms']);
  assert.deepEqual(checkI18n(fixture({ fr: { ...fr, more_one: 'x', more_many: 'y', more_other: 'z' } })), [
    'fr.json has "more" plural forms, which en.json lacks',
  ]);
});

test('a literal plural base counts as known only when en defines its forms', () => {
  assert.deepEqual(checkI18n(fixture({ source: `t('items', { count })` })), []);
  assert.deepEqual(checkI18n(fixture({ source: `t('things', { count })` })), ['App.tsx uses "things", which en.json lacks']);
});
