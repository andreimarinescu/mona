import emptyNoResults from '@design/mona-handoff/assets/illustrations/empty-no-results.svg';
import { Banner, Button, EmptyState, Pagination, SearchField, Select, Skeleton, format } from '@mona/ui';
import { useNavigate, useSearch } from '@tanstack/react-router';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ARCHIVE_PAGE_SIZE, archiveSearchParams, filtersToQuery, parseArchiveSearch, useArchiveSearch, type ArchiveFilters } from '../../data/archive';
import type { DocumentSort } from '../../data/dto';
import { errorKey, errorValues } from '../../data/errors';
import { usePageContext } from '../../shell/usePageContext';
import { usePublishPageFacts } from '../../shell/usePageFacts';
import { useLang } from '../../shell/useLang';
import { useAppState } from '../../state/context';
import { useIsDesktop } from '../review/useIsDesktop';
import { ActiveFilters } from './ActiveFilters';
import { ArchiveHeader } from './ArchiveHeader';
import { FacetPanel } from './FacetPanel';
import { ResultsTable } from './ResultsTable';

const SORTS: DocumentSort[] = ['relevance', 'date_desc', 'date_asc', 'arrived_desc', 'amount_desc'];

export function ArchivePage() {
  const { t } = useTranslation();
  const lang = useLang();
  const navigate = useNavigate();
  const desktop = useIsDesktop();
  const { scope, openChat } = useAppState();
  const context = usePageContext();
  const filters = parseArchiveSearch(useSearch({ strict: false }) as Record<string, unknown>);
  const scopeEntity = scope === 'all' ? undefined : scope;
  const search = useArchiveSearch(filtersToQuery(filters, scopeEntity));
  const result = search.data;
  const [draft, setDraft] = useState(filters.q ?? '');
  const [syncedQ, setSyncedQ] = useState(filters.q);
  if (syncedQ !== filters.q) {
    setSyncedQ(filters.q);
    setDraft(filters.q ?? '');
  }

  usePublishPageFacts(result ? { archive: { query: filters.q ?? null, results: result.total } } : null);

  const apply = (next: ArchiveFilters) => void navigate({ to: '/archive', search: archiveSearchParams(next) });
  const change = (patch: Partial<ArchiveFilters>) => apply({ ...filters, page: undefined, ...patch });
  const n = (v: number) => format.number(v, lang);
  const sort: DocumentSort = filters.sort ?? (filters.q ? 'relevance' : 'date_desc');
  const total = result?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / ARCHIVE_PAGE_SIZE));

  const facets = result ? <FacetPanel facets={result.facets} filters={filters} scoped={!!scopeEntity} onChange={change} /> : <Skeleton lines={8} />;

  return (
    <div className="mx-auto flex max-w-[1180px] flex-col gap-6 p-6 lg:p-10">
      <ArchiveHeader view="list" />
      <div className="flex flex-wrap items-center gap-3">
        <SearchField
          className="min-w-[260px] max-w-[440px] flex-1"
          lang={lang}
          label={t('archive.search.label')}
          placeholder={t('archive.search.placeholder')}
          value={draft}
          onChange={(v) => {
            setDraft(v);
            if (v === '' && filters.q) change({ q: undefined });
          }}
          onSearch={(v) => change({ q: v.trim() || undefined })}
        />
        <Button variant="ghost" icon="help" onClick={() => openChat(draft.trim() ? { send: { message: draft.trim(), pageContext: context } } : undefined)}>
          {t('archive.search.askMona')}
        </Button>
      </div>
      <div className="grid gap-8 lg:grid-cols-[260px_minmax(0,1fr)]">
        {desktop ? (
          <section aria-label={t('archive.facets.label')}>{facets}</section>
        ) : (
          <details className="rounded-lg border border-border bg-surface p-4">
            <summary className="cursor-pointer font-ui text-[15px] leading-[22px] font-semibold text-text">{t('archive.facets.label')}</summary>
            <div className="pt-4">{facets}</div>
          </details>
        )}
        <section aria-label={t('archive.results.label')} className="flex min-w-0 flex-col gap-4">
          {search.isError ? (
            <Banner tone="danger" actions={<Button variant="secondary" size="sm" onClick={() => void search.refetch()}>{t('common.retry')}</Button>}>
              {t(errorKey(search.error), errorValues(search.error))}
            </Banner>
          ) : null}
          <div className="flex flex-wrap items-end gap-x-4 gap-y-2">
            <p className="m-0 flex-1 font-ui text-[15px] leading-[22px] text-text-muted" role="status" data-testid="results-count">
              {result ? (
                <>
                  <strong className="font-semibold text-text">{t('archive.results.count', { count: total, n: n(total) })}</strong>
                  {filters.q ? ` ${t('archive.results.forQuery', { q: filters.q })}` : ''}
                </>
              ) : (
                t('archive.results.loading')
              )}
            </p>
            <Select
              label={t('archive.sort.label')}
              value={sort}
              onChange={(e) => change({ sort: e.target.value as DocumentSort })}
              options={SORTS.filter((s) => s !== 'relevance' || filters.q).map((s) => ({ value: s, label: t(`archive.sort.${s}`) }))}
            />
          </div>
          <ActiveFilters facets={result?.facets} filters={filters} scoped={!!scopeEntity} onChange={change} onClear={() => apply({ q: filters.q })} />
          {search.isPending ? <Skeleton lines={6} /> : null}
          {result && result.items.length > 0 ? <ResultsTable rows={result.items} q={filters.q} busy={search.isPlaceholderData} /> : null}
          {result && result.items.length === 0 ? (
            <EmptyState art={emptyNoResults} title={t('archive.empty.title')} action={<Button variant="secondary" onClick={() => apply({})}>{t('archive.empty.clear')}</Button>}>
              {t('archive.empty.body')}
            </EmptyState>
          ) : null}
          {result && total > 0 ? (
            <Pagination variant="compact" lang={lang} page={filters.page ?? 1} pageCount={pageCount} total={total} pageSize={ARCHIVE_PAGE_SIZE} onChange={(page) => apply({ ...filters, page })} />
          ) : null}
        </section>
      </div>
    </div>
  );
}
