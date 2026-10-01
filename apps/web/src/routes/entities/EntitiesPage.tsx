import emptyInbox from '@design/mona-handoff/assets/illustrations/empty-inbox.svg';
import { EmptyState, Tabs } from '@mona/ui';
import { useNavigate, useParams } from '@tanstack/react-router';
import { useTranslation } from 'react-i18next';
import { LoadError, LoadingState } from '../../components/states';
import { useCategoryList, useEntityDetail, useEntityList, usePeople } from '../../data/registry';
import { useAppState } from '../../state/context';
import { CategoryEditor } from './CategoryEditor';
import { CategoryTree } from './CategoryTree';
import { EntityCard } from './EntityCard';
import { sortEntities } from './entityView';

function EntitiesTab() {
  const { t } = useTranslation();
  const { scope } = useAppState();
  const list = useEntityList();
  const people = usePeople();
  const visitorsId = list.data?.visitorsEntityId ?? null;
  const visitors = useEntityDetail(visitorsId);
  if (list.isPending) return <LoadingState label={t('states.loading.entities')} />;
  if (list.isError) return <LoadError onRetry={() => void list.refetch()} />;
  const items = sortEntities(list.data.items, visitorsId).filter((e) => scope === 'all' || e.id === scope);
  if (items.length === 0) {
    return (
      <EmptyState art={emptyInbox} title={t('entities.empty.title')}>
        {t('entities.empty.body')}
      </EmptyState>
    );
  }
  return (
    <div className="grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-3" data-testid="entity-grid">
      {items.map((entity) => (
        <EntityCard
          key={entity.id}
          entity={entity}
          documentCount={list.data.documentCounts[entity.id] ?? 0}
          people={people.data ?? []}
          visitors={entity.id === visitorsId ? { purgeAfterHours: visitors.data?.purgeAfterHours ?? null } : undefined}
        />
      ))}
    </div>
  );
}

function CategoriesTab({ categoryId }: { categoryId: string | undefined }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const categories = useCategoryList();
  const list = useEntityList();
  if (categories.isPending) return <LoadingState label={t('states.loading.categories')} />;
  if (categories.isError) return <LoadError onRetry={() => void categories.refetch()} />;
  const { items, documentCounts } = categories.data;
  if (items.length === 0) {
    return (
      <EmptyState art={emptyInbox} title={t('entities.categories.empty.title')}>
        {t('entities.categories.empty.body')}
      </EmptyState>
    );
  }
  const selected = items.find((c) => c.id === categoryId);
  const select = (id: string) => void navigate({ to: '/entities/categories/$categoryId', params: { categoryId: id } });
  return (
    <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-[320px_minmax(0,1fr)]">
      <div className="rounded-lg border border-border bg-surface shadow-1">
        <CategoryTree categories={items} counts={documentCounts} selectedId={selected?.id} onSelect={select} />
      </div>
      {selected ? (
        <CategoryEditor key={selected.id} category={selected} entities={list.data?.items ?? []} documentCount={documentCounts[selected.id] ?? 0} />
      ) : (
        <EmptyState art={emptyInbox} title={categoryId ? t('entities.categories.notFound') : t('entities.categories.pick')}>
          {t('entities.categories.pickBody')}
        </EmptyState>
      )}
    </div>
  );
}

export function EntitiesPage({ tab }: { tab: 'entities' | 'categories' }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const params: { categoryId?: string } = useParams({ strict: false });
  const list = useEntityList();
  const categories = useCategoryList();
  const entityCount = list.data?.items.length;
  const categoryCount = categories.data?.items.length;
  return (
    <div className="mx-auto flex max-w-[1280px] flex-col gap-6 p-6 lg:p-10">
      <header className="flex flex-col gap-2">
        <h1 className="m-0 text-text [font:var(--type-title)]">{t('nav.entities')}</h1>
        <p className="m-0 text-text-muted">{t('entities.subtitle')}</p>
      </header>
      <Tabs
        label={t('entities.tabs.label')}
        value={tab}
        onChange={(id) => {
          if (id === 'entities') void navigate({ to: '/entities' });
          else {
            const first = categories.data?.items[0]?.id;
            void navigate(first ? { to: '/entities/categories/$categoryId', params: { categoryId: first } } : { to: '/entities' });
          }
        }}
        tabs={[
          { id: 'entities', label: t('entities.tabs.entities'), count: entityCount, panelId: 'entities-tabpanel' },
          { id: 'categories', label: t('entities.tabs.categories'), count: categoryCount, panelId: 'entities-tabpanel' },
        ]}
      />
      <div role="tabpanel" id="entities-tabpanel" aria-labelledby={`tab-${tab}`} className="flex flex-col gap-6">
        {tab === 'entities' ? <EntitiesTab /> : <CategoriesTab categoryId={params.categoryId} />}
      </div>
    </div>
  );
}
