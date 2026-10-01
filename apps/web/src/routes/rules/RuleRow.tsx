import { Icon, format } from '@mona/ui';
import { Link } from '@tanstack/react-router';
import { useTranslation } from 'react-i18next';
import type { RuleListItem } from '../../data/dto';
import { useLang } from '../../shell/useLang';
import { destinationText, lastFiredLabel, needsCheck } from './ruleView';

const SOURCE_ICON = { seed: 'file', interview: 'help', correction: 'pencil' } as const;

export function SourceChip({ source }: { source: RuleListItem['rule']['source'] }) {
  const { t } = useTranslation();
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-surface-sunken px-2.5 py-0.5 font-ui text-[13px] leading-[18px] text-text">
      <Icon name={SOURCE_ICON[source]} size={13} />
      {t(`rules.chip.${source}`)}
    </span>
  );
}

export function RuleSwitch({ on, label, disabled, onChange }: { on: boolean; label: string; disabled?: boolean; onChange: (on: boolean) => void }) {
  return (
    <span className={`mona-switch ${disabled ? 'mona-check--disabled' : ''}`}>
      <button type="button" role="switch" aria-checked={on} aria-label={label} disabled={disabled} className="mona-switch__track" onClick={() => onChange(!on)}>
        <span className="mona-switch__thumb">{on ? <Icon name="check" size={12} strokeWidth={3} /> : null}</span>
      </button>
    </span>
  );
}

export interface RuleRowProps {
  item: RuleListItem;
  now: number;
  busy?: boolean;
  onToggle(ruleId: string, enabled: boolean): void;
}

export function RuleRow({ item, now, busy, onToggle }: RuleRowProps) {
  const { t } = useTranslation();
  const lang = useLang();
  const { rule } = item;
  const n = (v: number) => format.number(v, lang);
  return (
    <tr data-rule-id={rule.id} data-state={rule.state} data-testid="rule-row">
      <td className="w-full max-w-0">
        <div className="flex min-w-0 flex-col gap-0.5">
          <span className="flex flex-wrap items-center gap-2">
            <Link to="/rules/$ruleId" params={{ ruleId: rule.id }} className="font-ui text-[15px] leading-[22px] font-semibold text-text no-underline hover:underline">
              {rule.name}
            </Link>
            {rule.state === 'draft' ? <span className="rounded-full bg-warning-soft px-2 py-0.5 font-ui text-[12px] leading-4 font-semibold text-warning">{t('rules.state.draft')}</span> : null}
            {!item.valid ? <span className="rounded-full bg-danger-soft px-2 py-0.5 font-ui text-[12px] leading-4 font-semibold text-danger">{t('rules.state.invalid')}</span> : null}
          </span>
          <span className="truncate font-ui text-[13px] leading-[18px] text-text-muted" title={destinationText(rule)}>
            {destinationText(rule)}
          </span>
        </div>
      </td>
      <td className="whitespace-nowrap">
        <SourceChip source={rule.source} />
      </td>
      <td data-numeric="">{n(rule.firedCount)}</td>
      <td className="whitespace-nowrap">{lastFiredLabel(rule.lastFiredAt, now, lang, t)}</td>
      <td data-numeric="" data-check={needsCheck(rule) ? '' : undefined}>
        {needsCheck(rule) ? <strong className="text-warning">{t('rules.row.check', { n: n(rule.correctionsSince) })}</strong> : n(rule.correctionsSince)}
      </td>
      <td>
        <RuleSwitch on={rule.state === 'active'} label={t('rules.row.switch', { name: rule.name })} disabled={busy} onChange={(on) => onToggle(rule.id, on)} />
      </td>
    </tr>
  );
}
