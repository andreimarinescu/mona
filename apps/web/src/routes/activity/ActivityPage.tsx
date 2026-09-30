import emptyAllFiled from '@design/mona-handoff/assets/illustrations/empty-all-filed.svg';
import { Banner, Button, EmptyState, Skeleton, format } from '@mona/ui';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSettings } from '../../data/hooks';
import { useActivity, type ActivityFilters as Filters } from '../../data/journal';
import { useThresholds } from '../../data/registry';
import type { JournalEntry } from '../../data/dto';
import { useEntryActions } from '../../journal/useEntryActions';
import { useLang } from '../../shell/useLang';
import { useAppState } from '../../state/context';
import { ActivityBatch } from './ActivityBatch';
import { ActivityEntry } from './ActivityEntry';
import { ActivityFilters } from './ActivityFilters';
import type { ActivityContext } from './context';
import { dayRelation, groupByDay } from './days';

export function ActivityPage() {
  const { t } = useTranslation();
  const lang = useLang();
  const { scope } = useAppState();
  const [filters, setFilters] = useState<Filters>({});
  const query = { ...filters, entityId: filters.entityId ?? (scope === 'all' ? undefined : scope) };
  const activity = useActivity(query);
  const profileName = useSettings().data?.profileName ?? '';
  const { badgeHours } = useThresholds();
  const actions = useEntryActions();
  const now = activity.dataUpdatedAt || 0;

  const entriesById = useMemo(() => {
    const map = new Map<number, JournalEntry>();
    for (const item of activity.items) {
      if (item.kind === 'entry') map.set(item.entry.id, item.entry);
      else for (const e of item.preview) map.set(e.id, e);
    }
    return map;
  }, [activity.items]);
  const ctx: ActivityContext = { documents: activity.documents, rules: activity.rules, profileName, badgeHours, now, entriesById, actions };

  const days = useMemo(() => groupByDay(activity.items, (item) => (item.kind === 'group' ? item.group.at : item.entry.at)), [activity.items]);
  const today = new Date(now);

  return (
    <div className="mx-auto flex max-w-[1080px] flex-col gap-6 p-6 lg:p-10">
      <header className="flex flex-col gap-2">
        <h1 className="m-0 text-text [font:var(--type-title)]">{t('nav.activity')}</h1>
        <p className="m-0 text-text-muted">{t('activity.subtitle')}</p>
      </header>
      <ActivityFilters value={filters} onChange={setFilters} />
      {activity.isError ? (
        <Banner tone="danger" actions={<Button variant="secondary" size="sm" onClick={() => void activity.refetch()}>{t('common.retry')}</Button>}>
          {t('activity.loadFailed')}
        </Banner>
      ) : null}
      {activity.isPending ? <Skeleton lines={5} /> : null}
      {!activity.isPending && activity.items.length === 0 && !activity.isError ? (
        <EmptyState art={emptyAllFiled} title={t('activity.empty.title')}>
          {t('activity.empty.body')}
        </EmptyState>
      ) : null}
      {days.map((day) => {
        const relation = dayRelation(day.date, today);
        const date = format.date(day.date, lang, 'dayMonth');
        return (
          <section key={day.key} aria-label={date} className="flex flex-col gap-2">
            <h2 className="m-0 font-ui text-[14px] leading-5 font-medium text-text-muted">
              {relation === 'other' ? date : t(`activity.day.${relation}`, { date })}
            </h2>
            <ul className="m-0 flex list-none flex-col divide-y divide-border rounded-lg border border-border bg-surface px-4 py-0">
              {day.items.map((item) =>
                item.kind === 'group' ? (
                  <ActivityBatch key={item.group.id} item={item} ctx={ctx} />
                ) : (
                  <ActivityEntry key={item.entry.id} entry={item.entry} ctx={ctx} />
                ),
              )}
            </ul>
          </section>
        );
      })}
      {activity.hasNextPage ? (
        <div>
          <Button variant="secondary" loading={activity.isFetchingNextPage} onClick={() => void activity.fetchNextPage()}>
            {t('activity.loadMore')}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
