#!/usr/bin/env node
import { readFileSync, readdirSync } from 'node:fs';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const LOCALES = ['en', 'fr', 'ro'];
const PLURAL_SUFFIXES = ['_zero', '_one', '_two', '_few', '_many', '_other'];
const KEY_PATTERNS = [/\bt\(\s*(['"])([^'"\n]+)\1/g, /\bi18nKey=\{?\s*(['"])([^'"\n]+)\1/g];

function flatten(obj, prefix = '', out = new Set()) {
  for (const [k, v] of Object.entries(obj)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === 'object') flatten(v, key, out);
    else out.add(key);
  }
  return out;
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
  for (const locale of LOCALES.filter((l) => l !== 'en')) {
    for (const k of keys.en) if (!keys[locale].has(k)) problems.push(`${locale}.json is missing "${k}"`);
  }
  for (const locale of LOCALES) {
    for (const k of keys[locale]) if (!keys.en.has(k)) problems.push(`${locale}.json has "${k}", which en.json lacks`);
  }
  const known = (k) => keys.en.has(k) || PLURAL_SUFFIXES.some((s) => keys.en.has(k + s));
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
