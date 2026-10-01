import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { MonaLogo, type LogoStroke } from './MonaLogo';

const STROKES: LogoStroke[] = [3, 4, 5, 6];

describe('MonaLogo', () => {
  it.each(STROKES)('stroke %i: whole-pixel box, and a symbol drawn on whole and half pixels', (stroke) => {
    const { container } = render(<MonaLogo stroke={stroke} label="Mona" />);
    const svg = container.querySelector('svg')!;
    expect(Number.isInteger(Number(svg.getAttribute('width')))).toBe(true);
    expect(Number.isInteger(Number(svg.getAttribute('height')))).toBe(true);
    expect(svg.getAttribute('viewBox')).toBe(`0 0 ${svg.getAttribute('width')} ${svg.getAttribute('height')}`);
    expect(svg).toHaveAttribute('role', 'img');
    expect(svg).toHaveAttribute('aria-label', 'Mona');
    const symbol = svg.querySelector('path[fill="none"]')!;
    expect(symbol.getAttribute('stroke-width')).toBe(String(stroke));
    const numbers = (symbol.getAttribute('d') ?? '').match(/-?\d+(?:\.\d+)?/g)!.map(Number);
    expect(numbers.every((n) => Number.isInteger(n * 2))).toBe(true);
  });

  it('is decorative without a label', () => {
    const { container } = render(<MonaLogo stroke={3} />);
    expect(container.querySelector('svg')).toHaveAttribute('aria-hidden', 'true');
    expect(container.querySelector('svg')).not.toHaveAttribute('role');
  });
});
