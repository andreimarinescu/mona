#!/usr/bin/env node
import { readFileSync, readdirSync } from 'node:fs';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const LOCALES = ['en', 'fr', 'ro'];
const PLURAL_CATEGORIES = { en: ['one', 'other'], fr: ['one', 'many', 'other'], ro: ['one', 'few', 'other'] };
const PLURAL_KEY = /^(.+)_(zero|one|two|few|many|other)$/;
const KEY_PATTERNS = [/\bt\(\s*(['"])([^'"\n]+)\1/g, /\bi18nKey=\{?\s*(['"])([^'"\n]+)\1/g];

function flatten(obj, prefix = '', out = new Set()) {
  for (const [k, v] of Object.entries(obj)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === 'object') flatten(v, key, out);
    else out.add(key);
  }
  return out;
}

function splitKeys(keys) {
  const plain = new Set();
  const plural = new Map();
  for (const k of keys) {
    const m = PLURAL_KEY.exec(k);
    if (!m) plain.add(k);
    else plural.set(m[1], (plural.get(m[1]) ?? new Set()).add(m[2]));
  }
  return { plain, plural };
}

function* sourceFiles(dir) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) yield* sourceFiles(path);
    else if (/\.(tsx?|jsx?)$/.test(entry.name) && !/\.gen\.ts$/.test(entry.name)) yield path;
  }
}

export function checkI18n({ localesDir, srcDir }) {
  const keys = Object.fromEntries(
    LOCALES.map((l) => [l, flatten(JSON.parse(readFileSync(join(localesDir, `${l}.json`), 'utf8')))]),
  );
  const problems = [];
  const split = Object.fromEntries(LOCALES.map((l) => [l, splitKeys(keys[l])]));
  for (const locale of LOCALES.filter((l) => l !== 'en')) {
    for (const k of split.en.plain) if (!split[locale].plain.has(k)) problems.push(`${locale}.json is missing "${k}"`);
    for (const base of split.en.plural.keys()) {
      if (!split[locale].plural.has(base)) problems.push(`${locale}.json is missing "${base}" plural forms`);
    }
  }
  for (const locale of LOCALES) {
    for (const k of split[locale].plain) if (!split.en.plain.has(k)) problems.push(`${locale}.json has "${k}", which en.json lacks`);
    for (const [base, found] of split[locale].plural) {
      if (!split.en.plural.has(base)) problems.push(`${locale}.json has "${base}" plural forms, which en.json lacks`);
      const wanted = PLURAL_CATEGORIES[locale];
      for (const c of wanted) if (!found.has(c)) problems.push(`${locale}.json is missing "${base}_${c}"`);
      for (const c of found) {
        if (!wanted.includes(c)) problems.push(`${locale}.json has "${base}_${c}", which is not a plural category of ${locale} (${wanted.join('/')})`);
      }
    }
  }
  const known = (k) => keys.en.has(k) || split.en.plural.has(k);
  for (const file of sourceFiles(srcDir)) {
    const text = readFileSync(file, 'utf8');
    for (const pattern of KEY_PATTERNS) {
      for (const m of text.matchAll(pattern)) {
        if (!known(m[2])) problems.push(`${relative(srcDir, file)} uses "${m[2]}", which en.json lacks`);
      }
    }
  }
  return problems;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const web = fileURLToPath(new URL('../apps/web/src', import.meta.url));
  const problems = checkI18n({ localesDir: join(web, 'i18n'), srcDir: web });
  for (const p of problems) console.error(`i18n: ${p}`);
  if (problems.length) process.exit(1);
  console.log('i18n: en, fr and ro agree; every literal key exists');
}
