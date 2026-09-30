import { Icon } from './icon';
import { ui } from './i18n';
import type { BadgeProps, TagProps } from './types';
import { cx } from './util';

export function Badge(props: BadgeProps) {
  const tone = props.tone || 'neutral';
  const max = props.max || 99;
  const content = props.count != null ? (props.count > max ? max + '+' : props.count) : props.children;
  return (
    <span className={cx('mona-badge', 'mona-badge--' + tone, props.count != null && 'mona-badge--count', props.className)} aria-label={props.label}>
      {content}
    </span>
  );
}

export function Tag(props: TagProps) {
  const lang = props.lang || 'en';
  const small = props.size === 'sm';
  const cls = cx('mona-tag', small && 'mona-tag--sm', props.selected && 'mona-tag--selected', props.className);
  const lead = props.icon ? (
    <Icon key="i" name={props.selected ? 'check' : props.icon} size={small ? 12 : 14} />
  ) : props.selected ? (
    <Icon key="i" name="check" size={small ? 12 : 14} strokeWidth={2.6} />
  ) : null;
  const inner = [
    lead,
    <span key="t" className="mona-tag__text">
      {props.children}
    </span>,
  ];
  const { onToggle, onRemove } = props;
  if (onToggle) {
    return (
      <button type="button" className={cx(cls, 'mona-tag--toggle')} aria-pressed={!!props.selected} onClick={() => onToggle(!props.selected)}>
        {inner}
      </button>
    );
  }
  return (
    <span className={cls}>
      {inner}
      {onRemove ? (
        <button
          type="button"
          className="mona-tag__remove"
          aria-label={ui(lang, 'remove') + ' ' + (typeof props.children === 'string' ? props.children : '')}
          onClick={(e) => {
            e.stopPropagation();
            onRemove();
          }}
        >
          <Icon name="x" size={12} strokeWidth={2.6} />
        </button>
      ) : null}
    </span>
  );
}
