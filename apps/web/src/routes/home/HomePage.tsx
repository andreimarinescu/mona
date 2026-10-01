import { Button, SearchField, format } from '@mona/ui';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from '@tanstack/react-router';
import { useTranslation } from 'react-i18next';
import { LoadError, LoadingState, OfflineState } from '../../components/states';
import { useSettings, useShellCounts } from '../../data/hooks';
import { useHome } from '../../data/home';
import { useEntityList, useThresholds } from '../../data/registry';
import { useSystemStatus, patchSettings } from '../../data/settings';
import { useLang } from '../../shell/useLang';
import { useAppState } from '../../state/context';
import { ChatEntry } from './ChatEntry';
import { FirstRunChecklist } from './FirstRunChecklist';
import { MonaBrief } from './MonaBrief';
import { ActivityCard, DueCard, IngestionCard, ReviewQueueCard } from './cards';

function HomeHeader({ now }: { now: number }) {
  const { t } = useTranslation();
  const lang = useLang();
  const navigate = useNavigate();
  const day = new Intl.DateTimeFormat(lang === 'fr' ? 'fr-FR' : lang === 'ro' ? 'ro-RO' : 'en-GB', { weekday: 'long' }).format(now);
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <span className="font-ui text-[14px] leading-5 font-semibold text-text-muted" data-testid="home-date">
        {day} {format.date(now, lang)}
      </span>
      <div className="flex flex-wrap items-center gap-3">
        <SearchField label={t('home.search')} lang={lang} className="w-[240px]" onSearch={(q) => void navigate({ to: '/archive', search: q.trim() ? { q: q.trim() } : {} })} />
        <Button variant="secondary" icon="file" onClick={() => void navigate({ to: '/intake' })}>
          {t('home.add')}
        </Button>
      </div>
    </div>
  );
}

export function HomePage() {
  const { t } = useTranslation();
  const { scope } = useAppState();
  const home = useHome(scope === 'all' ? undefined : scope);
  const settings = useSettings().data;
  const entities = useEntityList().data;
  const empty = !!entities && Object.values(entities.documentCounts).reduce((a, b) => a + b, 0) === 0;
  const status = useSystemStatus(empty).data;
  const offline = useShellCounts().data?.mona === 'offline';
  const { badgeHours } = useThresholds();
  const qc = useQueryClient();
  const language = useMutation({ mutationFn: patchSettings, onSuccess: (view) => qc.setQueryData(['settings'], view) });

  if (home.isPending) {
    return (
      <div className="mx-auto flex max-w-[1180px] flex-col gap-6 p-6 lg:p-10">
        <h1 className="mona-sr">{t('nav.home')}</h1>
        <LoadingState label={t('states.loading.home')} />
      </div>
    );
  }
  if (home.isError) {
    return (
      <div className="mx-auto flex max-w-[1180px] flex-col gap-6 p-6 lg:p-10">
        <h1 className="m-0 text-text [font:var(--type-title)]">{t('nav.home')}</h1>
        <LoadError onRetry={() => void home.refetch()} />
      </div>
    );
  }

  const view = home.data;
  const documentTotal = entities ? Object.values(entities.documentCounts).reduce((a, b) => a + b, 0) : null;
  const firstRun = documentTotal === 0 && view.activity.items.length === 0;
  const name = settings?.profileName ?? '';
  const anonymous = !name || name === settings?.practiceName;
  const now = home.dataUpdatedAt;

  return (
    <div className="mx-auto flex max-w-[1180px] flex-col gap-8 p-6 pb-4 lg:p-10 lg:pb-6">
      <HomeHeader now={now} />
      {offline ? <OfflineState compact /> : null}
      <MonaBrief facts={view.facts} journalEntryCount={view.journalEntryCount} name={name} anonymous={anonymous} />
      {firstRun ? (
        <FirstRunChecklist
          state={{ locale: settings?.locale ?? 'en', entities: entities?.items.filter((e) => e.id !== entities.visitorsEntityId).length ?? 0, documents: documentTotal ?? 0, telegram: status?.privacy.telegram ?? null }}
          onLanguage={(locale) => language.mutate({ locale })}
        />
      ) : (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <ReviewQueueCard review={view.review} now={now} />
          <DueCard due={view.due} />
          <ActivityCard activity={view.activity} profileName={name} badgeHours={badgeHours} now={now} />
          <IngestionCard ingestion={view.ingestion} />
        </div>
      )}
      <ChatEntry disabled={offline} />
    </div>
  );
}
