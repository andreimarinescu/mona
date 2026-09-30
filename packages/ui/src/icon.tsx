import { createElement } from 'react';
import { CATEGORY } from './i18n';
import { ICON_PARTS, type IconPart } from './icon-data';
import type { CategoryIconProps, IconProps } from './types';
import { cx, pick } from './util';

const PARTS: Record<string, readonly IconPart[] | undefined> = ICON_PARTS;

export function Icon(props: IconProps) {
  const size = props.size || 16;
  const sw = props.strokeWidth || 2;
  const label = props.label;
  const parts = PARTS[props.name] ?? ICON_PARTS.file;
  return (
    <svg
      className={cx('mona-icon', props.spin && 'mona-spin', props.className)}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={sw}
      strokeLinecap="round"
      strokeLinejoin="round"
      role={label ? 'img' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      focusable="false"
    >
      {parts.map((p, i) => createElement(p[0], { key: i, ...p[1] }))}
    </svg>
  );
}

export function CategoryIcon(props: CategoryIconProps) {
  const size = props.size || 40;
  const label = props.label || pick(CATEGORY, props.lang)[props.category];
  return (
    <span className="mona-cat" style={{ width: size, height: size }} role="img" aria-label={label} title={props.showTitle ? label : undefined}>
      <Icon name={props.category} size={props.iconSize || Math.round(size / 2)} strokeWidth={1.9} />
    </span>
  );
}
