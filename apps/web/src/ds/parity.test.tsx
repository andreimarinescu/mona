import * as Port from '@mona/ui';
import { describe, expect, it } from 'vitest';
import './index';
import { core } from './parity/cases-core';
import { forms } from './parity/cases-forms';
import { overlay } from './parity/cases-overlay';
import { run, type Case, type Mona } from './parity/harness';

const shim = window.Mona as unknown as Mona;
const port = Port as unknown as Mona;

const FAMILIES: Record<string, Case[]> = { ...core, ...forms, ...overlay };
const SHIM_COMPONENTS = Object.keys(shim).filter((k) => k !== 'format' && k !== 'i18n');

describe('component parity: shim (bundle) vs @mona/ui', () => {
  it('has cases for every component the bundle exports, and each is exported by the port', () => {
    expect(Object.keys(FAMILIES).sort()).toEqual([...SHIM_COMPONENTS].sort());
    for (const name of SHIM_COMPONENTS) expect(typeof port[name], name).toBe('function');
  });

  it('reports the matrix size', () => {
    const cases = Object.values(FAMILIES).flat().length;
    console.log(`PARITY_MATRIX components=${Object.keys(FAMILIES).length} cases=${cases} formatCalls=${FORMAT_CALLS.length}`);
    expect(cases).toBeGreaterThan(500);
  });

  for (const [family, cases] of Object.entries(FAMILIES)) {
    describe(family, () => {
      for (const c of cases) {
        it(c.name || '(defaults)', async () => {
          const expected = await run(c, shim);
          const actual = await run(c, port);
          expect(actual.snapshots).toEqual(expected.snapshots);
          expect(actual.log).toEqual(expected.log);
          expect(actual.warnings).toEqual(expected.warnings);
          expect(expected.snapshots[0]?.length).toBeGreaterThan(2);
        });
      }
    });
  }
});

const LANGS = ['en', 'fr', 'ro'] as const;
const NOW = new Date('2026-03-14T14:02:00Z');
const DATES = [new Date('2026-03-14T14:02:00Z'), '2025-12-31T23:59:00Z', new Date('2026-01-05T08:00:00Z').getTime(), new Date('2024-02-29T12:00:00Z'), '2026-08-01', new Date('2026-09-30T00:00:00Z'), '2026-11-09T09:05:00Z'];
const OFFSETS_S = [0, 10, -10, 44, 46, -60, 600, -2699, 2701, 3600, -7200, 71999, 72001, -86400, 172800, -518399, 518401, 4000000];

const FORMAT_CALLS: Array<[string, () => unknown[]]> = [];
for (const lang of LANGS) {
  for (const n of [0, 1, -1, 12.5, 1284, 1284.6, 4812, 1234567.891, 0.005]) {
    FORMAT_CALLS.push([`number ${n} ${lang}`, () => [(f: Mona['format']) => f.number(n, lang)]]);
    FORMAT_CALLS.push([`number digits ${n} ${lang}`, () => [(f: Mona['format']) => f.number(n, lang, { maximumFractionDigits: 1 })]]);
    for (const cur of ['EUR', 'RON', 'USD', undefined]) FORMAT_CALLS.push([`money ${n} ${cur} ${lang}`, () => [(f: Mona['format']) => f.money(n, cur, lang)]]);
    FORMAT_CALLS.push([`fileSize ${n * 1000} ${lang}`, () => [(f: Mona['format']) => f.fileSize(Math.abs(n) * 1000, lang)]]);
  }
  for (const v of [0, 0.004, 0.62, 0.855, 1, 1.5]) {
    FORMAT_CALLS.push([`percent ${v} ${lang}`, () => [(f: Mona['format']) => f.percent(v, lang)]]);
    FORMAT_CALLS.push([`percent digits ${v} ${lang}`, () => [(f: Mona['format']) => f.percent(v, lang, 1)]]);
  }
  for (const d of DATES) {
    for (const style of ['long', 'medium', 'short', 'dayMonth', undefined]) FORMAT_CALLS.push([`date ${String(d)} ${style} ${lang}`, () => [(f: Mona['format']) => f.date(d, lang, style)]]);
    FORMAT_CALLS.push([`time ${String(d)} ${lang}`, () => [(f: Mona['format']) => f.time(d, lang)]]);
  }
  for (const s of OFFSETS_S) FORMAT_CALLS.push([`relative ${s} ${lang}`, () => [(f: Mona['format']) => f.relative(new Date(NOW.getTime() + s * 1000), lang, NOW)]]);
}
FORMAT_CALLS.push(['money without lang', () => [(f: Mona['format']) => f.money(1284.6)]]);
FORMAT_CALLS.push(['number without lang', () => [(f: Mona['format']) => f.number(1284.6)]]);
FORMAT_CALLS.push(['percent without lang', () => [(f: Mona['format']) => f.percent(0.62)]]);

describe('format and i18n parity', () => {
  it('matches the bundle on every call', () => {
    const mismatches: string[] = [];
    for (const [name, call] of FORMAT_CALLS) {
      const [fn] = call() as [(f: Mona['format']) => unknown];
      const a = fn(shim.format);
      const b = fn(port.format);
      if (a !== b) mismatches.push(`${name}: bundle=${JSON.stringify(a)} port=${JSON.stringify(b)}`);
    }
    expect(mismatches).toEqual([]);
    expect(FORMAT_CALLS.length).toBeGreaterThan(400);
  });

  it('carries the bundle i18n tables unchanged (the port adds REASON)', () => {
    for (const key of Object.keys(shim.i18n)) expect(port.i18n[key], key).toEqual(shim.i18n[key]);
    expect(Object.keys(port.i18n).sort()).toEqual([...Object.keys(shim.i18n), 'REASON'].sort());
  });
});
