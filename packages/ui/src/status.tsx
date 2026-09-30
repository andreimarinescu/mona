import { Icon } from './icon';
import { format } from './format';
import { CONFIDENCE, REASON, STATUS } from './i18n';
import { Tooltip } from './overlay';
import type { ConfidenceMeterProps, DocStatus, IconName, ReasonChipProps, ReasonKind, StatusPillProps } from './types';
import { cx, pick } from './util';

const STATUS_ICON: Record<DocStatus, IconName> = { filed: 'check', review: 'help', processing: 'loader', unreadable: 'file-x' };

export function StatusPill(props: StatusPillProps) {
  const status = props.status || 'processing';
  const label = props.label || pick(STATUS, props.lang)[status];
  const sm = props.size === 'sm';
  const icon = <Icon name={STATUS_ICON[status]} size={sm ? 12 : 14} strokeWidth={status === 'filed' ? 2.8 : 2.4} spin={status === 'processing'} />;
  const cls = cx('mona-pill', 'mona-pill--' + status, sm && 'mona-pill--sm', props.compact && 'mona-pill--compact', props.className);
  if (props.compact) {
    return (
      <Tooltip content={label}>
        <span className={cls} role="img" aria-label={label} tabIndex={0}>
          {icon}
        </span>
      </Tooltip>
    );
  }
  return (
    <span className={cls} role={status === 'processing' ? 'status' : undefined}>
      {icon}
      <span>{label}</span>
    </span>
  );
}

function fraction(n: number): number {
  return n > 1 ? n / 100 : n;
}

export function ConfidenceMeter(props: ConfidenceMeterProps) {
  const v = props.value > 1 ? props.value / 100 : props.value || 0;
  const high = fraction(props.thresholds?.high ?? 0.85);
  const medium = fraction(props.thresholds?.medium ?? 0.6);
  const level = v >= high ? 'high' : v >= medium ? 'mid' : 'low';
  const on = v > 0 ? Math.max(1, Math.round(v * 5)) : 0;
  const t = pick(CONFIDENCE, props.lang);
  const pct = format.percent(v, props.lang);
  const text = t.label + ' ' + pct + ', ' + t[level];
  return (
    <span
      className={cx('mona-meter', 'mona-meter--' + level, props.className)}
      role="meter"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(v * 100)}
      aria-valuetext={text}
      aria-label={t.label}
    >
      {props.hideLabel ? null : <span>{t.label}</span>}
      <span className="mona-meter__segs" aria-hidden>
        {[0, 1, 2, 3, 4].map((i) => (
          <span key={i} className="mona-meter__seg" data-on={i < on ? '' : undefined} />
        ))}
      </span>
      <span className="mona-meter__value">{pct}</span>
      {props.hideWord ? null : <span>{t[level]}</span>}
    </span>
  );
}

const REASON_ICON: Record<ReasonKind, IconName> = { low: 'help', entity: 'search', conflict: 'alert', unreadable: 'file-x' };

export function ReasonChip(props: ReasonChipProps) {
  const label = props.label || pick(REASON, props.lang)[props.reason];
  return (
    <span className={cx('mona-reason', 'mona-reason--' + props.reason, props.className)}>
      <Icon name={REASON_ICON[props.reason]} size={14} />
      <span>{label}</span>
    </span>
  );
}
