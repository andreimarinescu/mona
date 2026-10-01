import emptyInbox from '@design/mona-handoff/assets/illustrations/empty-inbox.svg';
import emptyNoResults from '@design/mona-handoff/assets/illustrations/empty-no-results.svg';
import { EmptyState, SearchField, format } from '@mona/ui';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { LoadError, LoadingState } from '../../components/states';
import { useLearned, usePatchRule, useRules } from '../../data/rules';
import { useLang } from '../../shell/useLang';
import { useAppState } from '../../state/context';
import { LearnedPanel } from './LearnedPanel';
import { RulesTable } from './RulesTable';
import { todayStart } from './ruleView';

const SEARCH_DELAY_MS = 250;

export function RulesPage() {
  const { t } = useTranslation();
  const lang = useLang();
  const { scope } = useAppState();
  const [text, setText] = useState('');
  const [q, setQ] = useState('');
  useEffect(() => {
    const id = setTimeout(() => setQ(text.trim()), SEARCH_DELAY_MS);
    return () => clearTimeout(id);
  }, [text]);
  const rules = useRules({ q: q || undefined, entityId: scope === 'all' ? undefined : scope });
  const learned = useLearned(todayStart());
  const patch = usePatchRule();
  const items = rules.data?.items ?? [];
  const total = rules.data?.total ?? 0;
  const on = items.filter((i) => i.rule.state === 'active').length;
  const now = rules.dataUpdatedAt || 0;
  const filtering = q !== '' || scope !== 'all';

  return (
    <div className="mx-auto flex max-w-[1280px] flex-col gap-6 p-6 lg:p-10">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex max-w-[720px] flex-col gap-2">
          <h1 className="m-0 text-text [font:var(--type-title)]">{t('nav.rules')}</h1>
          {rules.data ? <p className="m-0 text-text-muted">{t('rules.subtitle', { count: total, total: format.number(total, lang), on: format.number(on, lang) })}</p> : null}
        </div>
        <SearchField label={t('rules.search')} value={text} onChange={setText} lang={lang} className="w-full sm:w-[260px]" />
      </header>
      {rules.isPending ? <LoadingState label={t('states.loading.rules')} /> : null}
      {rules.isError ? <LoadError onRetry={() => void rules.refetch()} /> : null}
      {rules.data ? (
        <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
          {items.length === 0 ? (
            <EmptyState art={filtering ? emptyNoResults : emptyInbox} title={filtering ? t('rules.noMatch.title') : t('rules.empty.title')}>
              {filtering ? t('rules.noMatch.body') : t('rules.empty.body')}
            </EmptyState>
          ) : (
            <RulesTable items={items} now={now} busyId={patch.isPending ? patch.variables?.id : null} onToggle={(id, enabled) => patch.mutate({ id, body: { enabled } })} />
          )}
          <LearnedPanel items={learned.data ?? []} now={now} />
        </div>
      ) : null}
    </div>
  );
}
