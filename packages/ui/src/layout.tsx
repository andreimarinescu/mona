import { createElement, type ElementType } from 'react';
import type { ContainerProps, GridProps, InlineProps, StackProps } from './types';
import { cx } from './util';

type Align = NonNullable<StackProps['align']>;

const ALIGN: Record<Align, string> = {
  start: 'flex-start',
  center: 'center',
  end: 'flex-end',
  stretch: 'stretch',
  baseline: 'baseline',
  between: 'space-between',
};

function sp(n?: number | string): string | undefined {
  return n == null ? undefined : typeof n === 'number' ? 'var(--space-' + n + ')' : n;
}

function align(a?: Align): string | undefined {
  return a ? ALIGN[a] : undefined;
}

function tag(as?: string): ElementType {
  return (as || 'div') as ElementType;
}

export function Stack(props: StackProps) {
  const { as, gap, align: a, justify, className, style, children, ...rest } = props;
  return createElement(
    tag(as),
    { ...rest, className: cx('mona-stack', className), style: { gap: sp(gap != null ? gap : 4), alignItems: align(a), justifyContent: align(justify), ...style } },
    children,
  );
}

export function Inline(props: InlineProps) {
  const { as, gap, align: a, justify, wrap, className, style, children, ...rest } = props;
  return createElement(
    tag(as),
    {
      ...rest,
      className: cx('mona-inline', className),
      style: { gap: sp(gap != null ? gap : 2), alignItems: align(a || 'center'), justifyContent: align(justify), flexWrap: wrap === false ? 'nowrap' : 'wrap', ...style },
    },
    children,
  );
}

export function Grid(props: GridProps) {
  const { as, gap, align: a, justify: _justify, columns, minItemWidth, className, style, children, ...rest } = props;
  const cols = minItemWidth
    ? 'repeat(auto-fill, minmax(min(' + (typeof minItemWidth === 'number' ? minItemWidth + 'px' : minItemWidth) + ', 100%), 1fr))'
    : 'repeat(' + (columns || 2) + ', minmax(0, 1fr))';
  return createElement(
    tag(as),
    { ...rest, className: cx('mona-grid', className), style: { gap: sp(gap != null ? gap : 4), gridTemplateColumns: cols, alignItems: align(a), ...style } },
    children,
  );
}

export function Container(props: ContainerProps) {
  const { as, size, padded, className, style, children, ...rest } = props;
  return createElement(
    tag(as),
    { ...rest, className: cx('mona-container', 'mona-container--' + (size || 'lg'), padded === false && 'mona-container--flush', className), style },
    children,
  );
}
