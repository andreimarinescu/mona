import { describe, expect, it } from 'vitest';
import { format } from '../src';

const NB = ' ';
const D = new Date('2026-03-14T14:02:00');

describe('format (formatting.md)', () => {
  it('money', () => {
    expect(format.money(1284.6, 'EUR', 'en')).toBe('€1,284.60');
    expect(format.money(1284.6, 'EUR', 'fr')).toBe(`1${NB}284,60${NB}€`);
    expect(format.money(1284.6, 'EUR', 'ro')).toBe(`1.284,60${NB}€`);
    expect(format.money(4812, 'RON', 'en')).toBe(`4,812.00${NB}lei`);
    expect(format.money(4812, 'RON', 'fr')).toBe(`4${NB}812,00${NB}lei`);
    expect(format.money(4812, 'RON', 'ro')).toBe(`4.812,00${NB}lei`);
  });

  it('percent takes a space in French only', () => {
    expect(format.percent(0.62, 'en')).toBe('62%');
    expect(format.percent(0.62, 'fr')).toBe(`62${NB}%`);
    expect(format.percent(0.62, 'ro')).toBe('62%');
    expect(format.percent(0.625, 'en', 1)).toBe('62.5%');
  });

  it('number', () => {
    expect(format.number(1284, 'en')).toBe('1,284');
    expect(format.number(1284, 'fr')).toBe(`1${NB}284`);
    expect(format.number(1284, 'ro')).toBe('1.284');
  });

  it('date', () => {
    expect(format.date(D, 'en')).toBe('14 March 2026');
    expect(format.date(D, 'fr')).toBe('14 mars 2026');
    expect(format.date(D, 'ro')).toBe('14 martie 2026');
    expect(format.date(D, 'en', 'medium')).toBe('14 Mar 2026');
    expect(format.date(D, 'fr', 'medium')).toBe('14 mars 2026');
    expect(format.date(D, 'ro', 'medium')).toBe('14 mar. 2026');
    expect(format.date(D, 'en', 'short')).toBe('14/03/2026');
    expect(format.date(D, 'fr', 'short')).toBe('14/03/2026');
    expect(format.date(D, 'ro', 'short')).toBe('14.03.2026');
    expect(format.date(D, 'en', 'dayMonth')).toBe('14 March');
  });

  it('time', () => {
    for (const lang of ['en', 'fr', 'ro'] as const) expect(format.time(D, lang)).toBe('14:02');
  });

  it('relative', () => {
    const now = new Date('2026-03-14T14:02:00');
    const ago = (s: number) => new Date(now.getTime() - s * 1000);
    expect(format.relative(ago(120), 'en', now)).toBe('2 minutes ago');
    expect(format.relative(ago(120), 'fr', now)).toBe('il y a 2 minutes');
    expect(format.relative(ago(120), 'ro', now)).toBe('acum 2 minute');
    expect(format.relative(ago(86400), 'en', now)).toBe('yesterday');
    expect(format.relative(ago(86400), 'fr', now)).toBe('hier');
    expect(format.relative(ago(86400), 'ro', now)).toBe('ieri');
    expect(format.relative(ago(7 * 86400), 'en', now)).toBe('7 Mar 2026');
  });

  it('fileSize', () => {
    expect(format.fileSize(234567, 'en')).toBe(`229.1${NB}KB`);
    expect(format.fileSize(234567, 'fr')).toBe(`229,1${NB}Ko`);
    expect(format.fileSize(234567, 'ro')).toBe(`229,1${NB}KB`);
    expect(format.fileSize(512, 'en')).toBe(`512${NB}B`);
  });

  it('never emits U+202F', () => {
    const all = [format.money(1284.6, 'EUR', 'fr'), format.number(1234567, 'fr'), format.percent(0.5, 'fr'), format.date(D, 'fr', 'short'), format.fileSize(5e6, 'fr')];
    for (const s of all) expect(s).not.toContain(' ');
  });
});
