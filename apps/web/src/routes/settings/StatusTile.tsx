import { Icon } from '@mona/ui';

export type StatusTone = 'ok' | 'warn' | 'bad' | 'unknown';

const TONE: Record<StatusTone, { icon: 'circle-check' | 'alert' | 'help'; color: string }> = {
  ok: { icon: 'circle-check', color: 'text-success' },
  warn: { icon: 'alert', color: 'text-warning' },
  bad: { icon: 'alert', color: 'text-danger' },
  unknown: { icon: 'help', color: 'text-text-muted' },
};

export interface StatusTileProps {
  label: string;
  value: string;
  /** The word that says how it is, next to its icon: status is never colour alone. */
  status: string;
  tone: StatusTone;
  detail?: string;
}

export function StatusTile({ label, value, status, tone, detail }: StatusTileProps) {
  const { icon, color } = TONE[tone];
  return (
    <div className="flex min-w-0 flex-col gap-1 rounded-md bg-surface-sunken p-4" data-testid="status-tile" data-tone={tone}>
      <span className="font-ui text-[13px] leading-[18px] text-text-muted">{label}</span>
      <span className="break-words font-ui text-[15px] leading-[22px] font-semibold text-text">{value}</span>
      {detail ? <span className="font-ui text-[13px] leading-[18px] text-text-muted">{detail}</span> : null}
      <span className={`inline-flex items-center gap-1.5 font-ui text-[13px] leading-[18px] ${color}`}>
        <Icon name={icon} size={14} />
        {status}
      </span>
    </div>
  );
}
