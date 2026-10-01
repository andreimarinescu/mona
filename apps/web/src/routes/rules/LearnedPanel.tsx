import { MonaAvatar } from '@mona/ui';
import { Link } from '@tanstack/react-router';
import { useTranslation } from 'react-i18next';
import type { LearnedItem } from '../../data/dto';
import { useLang } from '../../shell/useLang';
import { learnedWhen } from './ruleView';

export function LearnedPanel({ items, now }: { items: LearnedItem[]; now: number }) {
  const { t } = useTranslation();
  const lang = useLang();
  return (
    <section aria-labelledby="learned-title" className="flex flex-col gap-4 rounded-lg border border-border bg-surface p-5 shadow-1" data-testid="learned-panel">
      <header className="flex items-center gap-3">
        <MonaAvatar size={28} />
        <h2 id="learned-title" className="m-0 text-text [font:var(--type-heading)]">
          {t('rules.learned.title')}
        </h2>
      </header>
      {items.length === 0 ? (
        <p className="m-0 text-text-muted">{t('rules.learned.empty')}</p>
      ) : (
        <ul className="m-0 flex flex-col p-0">
          {items.map((item) => (
            <li key={item.rule.id} className="flex list-none flex-col gap-1 border-t border-border py-3 first:border-t-0 first:pt-0" data-rule-id={item.rule.id}>
              <Link to="/rules/$ruleId" params={{ ruleId: item.rule.id }} className="text-text no-underline hover:underline [font:var(--type-voice)] text-[18px] leading-[25px]">
                {item.rule.name}
              </Link>
              <span className="font-ui text-[13px] leading-[18px] text-text-muted">
                {[t(`rules.learned.from.${item.rule.source === 'interview' ? 'interview' : 'correction'}`), learnedWhen(item.createdAt, now, lang, t), t('rules.learned.moved', { count: item.moved })].join(' · ')}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
