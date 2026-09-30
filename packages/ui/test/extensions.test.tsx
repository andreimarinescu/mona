import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ConfidenceMeter, Icon, ReasonChip, i18n, type ExtraIconName, type ReasonKind } from '../src';

const ICON_DIR = join(import.meta.dirname, '../../../design/mona-handoff/assets/icons');
const CSS = readFileSync(join(import.meta.dirname, '../src/reason-chip.css'), 'utf8');

function svgParts(svg: string): string[] {
  return [...svg.matchAll(/<(path|circle|rect|line|polyline)\b([^>]*?)\/>/g)].map((m) => {
    const attrs = [...(m[2] ?? '').matchAll(/([\w-]+)="([^"]*)"/g)].map((a) => `${a[1]}=${a[2]}`).sort();
    return `${m[1]} ${attrs.join(' ')}`;
  });
}

describe('ConfidenceMeter thresholds', () => {
  const level = (c: HTMLElement) => /mona-meter--(high|mid|low)/.exec(c.querySelector('.mona-meter')?.className ?? '')?.[1];

  it('defaults to 85 and 60', () => {
    expect(level(render(<ConfidenceMeter value={0.85} />).container)).toBe('high');
    expect(level(render(<ConfidenceMeter value={0.84} />).container)).toBe('mid');
    expect(level(render(<ConfidenceMeter value={0.6} />).container)).toBe('mid');
    expect(level(render(<ConfidenceMeter value={0.59} />).container)).toBe('low');
  });

  it('custom thresholds move the band', () => {
    const t = { high: 0.95, medium: 0.7 };
    expect(level(render(<ConfidenceMeter value={0.9} thresholds={t} />).container)).toBe('mid');
    expect(level(render(<ConfidenceMeter value={0.65} thresholds={t} />).container)).toBe('low');
    expect(level(render(<ConfidenceMeter value={0.96} thresholds={t} />).container)).toBe('high');
    expect(level(render(<ConfidenceMeter value={0.65} thresholds={{ medium: 0.5 }} />).container)).toBe('mid');
  });

  it('accepts percentages and a 0-100 value', () => {
    expect(level(render(<ConfidenceMeter value={90} thresholds={{ high: 95, medium: 70 }} />).container)).toBe('mid');
  });
});

describe('Icon gains the 16 handoff icons', () => {
  const files = readdirSync(ICON_DIR).filter((f) => f.endsWith('.svg'));

  it('finds all sixteen source files', () => {
    expect(files).toHaveLength(16);
  });

  it.each(files)('%s renders the same shapes as the source svg', (file) => {
    const name = file.replace('.svg', '') as ExtraIconName;
    const { container } = render(<Icon name={name} />);
    const svg = container.querySelector('svg') as SVGElement;
    const rendered = [...svg.children].map((el) => `${el.tagName.toLowerCase()} ${[...el.attributes].map((a) => `${a.name}=${a.value}`).sort().join(' ')}`);
    expect(rendered).toEqual(svgParts(readFileSync(join(ICON_DIR, file), 'utf8')));
  });

  it('keeps the file fallback for unknown names', () => {
    const a = render(<Icon name={'nope' as never} />).container.innerHTML;
    const b = render(<Icon name="file" />).container.innerHTML;
    expect(a).toBe(b);
  });
});

describe('ReasonChip', () => {
  const reasons: ReasonKind[] = ['low', 'entity', 'conflict', 'unreadable'];

  it.each(reasons)('%s carries an icon, a word and its pattern class in every language', (reason) => {
    for (const lang of ['en', 'fr', 'ro'] as const) {
      const { container, unmount } = render(<ReasonChip reason={reason} lang={lang} />);
      const chip = container.firstElementChild as HTMLElement;
      expect(chip).toHaveClass('mona-reason', `mona-reason--${reason}`);
      expect(chip.querySelector('svg.mona-icon')).not.toBeNull();
      expect(chip.textContent).toBe(i18n.REASON[lang][reason]);
      unmount();
    }
  });

  it('uses the expected words', () => {
    render(
      <>
        <ReasonChip reason="low" />
        <ReasonChip reason="entity" lang="fr" />
        <ReasonChip reason="conflict" lang="ro" />
        <ReasonChip reason="unreadable" label="Custom" className="extra" />
      </>,
    );
    expect(screen.getByText('Low confidence')).toBeInTheDocument();
    expect(screen.getByText('Entité inconnue')).toBeInTheDocument();
    expect(screen.getByText('Regulă în conflict')).toBeInTheDocument();
    expect(screen.getByText('Custom').parentElement).toHaveClass('extra');
  });

  it('has a distinct outline pattern per reason and styles only with tokens', () => {
    expect(CSS).toMatch(/--low\s*{[^}]*border: 1px solid/);
    expect(CSS).toMatch(/--entity\s*{[^}]*border: 1px dashed/);
    expect(CSS).toMatch(/--conflict\s*{[^}]*box-shadow: inset/);
    expect(CSS).toMatch(/--unreadable\s*{[^}]*repeating-linear-gradient/);
    expect(CSS).not.toMatch(/#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(/);
  });
});
