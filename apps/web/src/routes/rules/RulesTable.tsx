import { useTranslation } from 'react-i18next';
import type { RuleListItem } from '../../data/dto';
import { RuleRow } from './RuleRow';

export interface RulesTableProps {
  items: RuleListItem[];
  now: number;
  busyId?: string | null;
  onToggle(ruleId: string, enabled: boolean): void;
}

export function RulesTable({ items, now, busyId, onToggle }: RulesTableProps) {
  const { t } = useTranslation();
  return (
    <div className="mona-table-wrap" data-testid="rules-table">
      <table className="mona-table">
        <caption className="mona-sr">{t('rules.table.caption')}</caption>
        <thead>
          <tr>
            <th scope="col">{t('rules.table.rule')}</th>
            <th scope="col">{t('rules.table.source')}</th>
            <th scope="col" data-numeric="">
              {t('rules.table.fired')}
            </th>
            <th scope="col">{t('rules.table.lastFired')}</th>
            <th scope="col" data-numeric="">
              {t('rules.table.corrections')}
            </th>
            <th scope="col">{t('rules.table.on')}</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <RuleRow key={item.rule.id} item={item} now={now} busy={busyId === item.rule.id} onToggle={onToggle} />
          ))}
        </tbody>
      </table>
    </div>
  );
}
