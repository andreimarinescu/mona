import { Icon } from './icon';
import type { ButtonProps } from './types';
import { cx } from './util';

export function Button(props: ButtonProps) {
  const { variant: variantProp, size: sizeProp, icon, iconEnd, loading, iconOnly, children, className, ...rest } = props;
  const variant = variantProp || 'secondary';
  const size = sizeProp || 'md';
  const iconSize = size === 'sm' ? 16 : 18;
  return (
    <button
      type="button"
      {...rest}
      className={cx('mona-btn', 'mona-btn--' + variant, size === 'sm' && 'mona-btn--sm', iconOnly && 'mona-btn--icon', className)}
      aria-busy={loading ? true : undefined}
      disabled={props.disabled || loading}
    >
      {loading ? <Icon name="loader" size={iconSize} spin /> : icon ? <Icon name={icon} size={iconSize} /> : null}
      {iconOnly ? null : children}
      {iconEnd ? <Icon name={iconEnd} size={iconSize} /> : null}
    </button>
  );
}
