import { MonaAvatar, Avatar, ReasonChip, StatusPill, format } from '@mona/ui';
import { Link } from '@tanstack/react-router';
import { useTranslation } from 'react-i18next';
import type { ActivityItem, Deadline, DocRefs, DocumentSummary, HomeView, JournalEntry } from '../../data/dto';
import { EntryUndo } from '../../journal/EntryUndo';
import { badgeLive, entryTitle, placeLabel } from '../../journal/entryView';
import { useEntryActions } from '../../journal/useEntryActions';
import { useLang } from '../../shell/useLang';
import { ActionCard } from './ActionCard';
import { DateTile } from './DateTile';
import { Sparkline } from './Sparkline';
import { whenPhrase } from './brief';
import { ingestionFigures } from './ingestion';

const ROW = 'flex list-none items-start gap-3 border-t border-border py-3 first:border-t-0 first:pt-0';
const MUTED = 'font-ui text-[13px] leading-[18px] text-text-muted';

function Empty({ children }: { children: string }) {
  return <p className="m-0 text-text-muted">{children}</p>;
}

export function ReviewQueueCard({ review, now }: { review: HomeView['review']; now: number }) {
  const { t } = useTranslation();
  const lang = useLang();
  const more = review.total - review.items.length;
  return (
    <ActionCard id="home-review" title={t('nav.review')} count={review.total > 0 ? review.total : undefined} seeAll={{ label: t('home.review.all'), href: '/review' }}>
      {review.items.length === 0 ? (
        <Empty>{t('home.review.empty')}</Empty>
      ) : (
        <ul className="m-0 flex flex-col p-0">
          {review.items.map((doc: DocumentSummary) => (
            <li key={doc.id} className={ROW}>
              <div className="flex min-w-0 flex-1 flex-col gap-1">
                <Link to="/review/$documentId" params={{ documentId: doc.id }} className="truncate font-ui text-[15px] leading-[22px] font-semibold text-text no-underline hover:underline">
                  {doc.title}
                </Link>
                <span className={MUTED}>{t('review.list.arrived', { when: format.relative(doc.arrivedAt, lang, new Date(now)), source: t(`review.source.${doc.source}`) })}</span>
              </div>
              {doc.reasons[0] ? <ReasonChip reason={doc.reasons[0]} lang={lang} /> : null}
            </li>
          ))}
        </ul>
      )}
      {more > 0 ? <p className={`m-0 ${MUTED}`}>{t('home.review.more', { count: more })}</p> : null}
    </ActionCard>
  );
}

function DueRow({ deadline }: { deadline: Deadline }) {
  const { t } = useTranslation();
  const lang = useLang();
  const when = deadline.daysLeft < 0 ? t('home.due.overdue', { count: -deadline.daysLeft }) : whenPhrase(deadline.daysLeft, t);
  const title = deadline.documentId ? (
    <Link to="/documents/$documentId" params={{ documentId: deadline.documentId }} className="font-ui text-[15px] leading-[22px] font-semibold text-text no-underline hover:underline">
      {deadline.label}
    </Link>
  ) : (
    <span className="font-ui text-[15px] leading-[22px] font-semibold text-text">{deadline.label}</span>
  );
  return (
    <li className={`${ROW} items-center`} data-days-left={deadline.daysLeft}>
      <DateTile date={deadline.dueDate} daysLeft={deadline.daysLeft} />
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        {title}
        <span className={MUTED}>{[deadline.entityName, when].filter(Boolean).join(' · ')}</span>
      </div>
      {deadline.amount ? <span className="font-ui text-[15px] leading-[22px] font-semibold text-text tabular-nums">{format.money(deadline.amount.value, deadline.amount.currency, lang)}</span> : null}
    </li>
  );
}

export function DueCard({ due }: { due: HomeView['due'] }) {
  const { t } = useTranslation();
  return (
    <ActionCard id="home-due" title={t('home.due.title')}>
      {due.items.length === 0 ? (
        <Empty>{t('home.due.empty')}</Empty>
      ) : (
        <ul className="m-0 flex flex-col p-0">
          {due.items.map((d) => (
            <DueRow key={d.id} deadline={d} />
          ))}
        </ul>
      )}
    </ActionCard>
  );
}

function ActivityRow({ item, documents, rules, profileName, badgeHours, now }: { item: ActivityItem; documents: DocRefs; rules: Record<string, { name: string }>; profileName: string; badgeHours: number; now: number }) {
  const { t } = useTranslation();
  const lang = useLang();
  const actions = useEntryActions();
  const actor = item.kind === 'group' ? item.group.actor : item.entry.actor;
  const at = item.kind === 'group' ? item.group.at : item.entry.at;
  const avatar = actor === 'mona' ? <MonaAvatar size={28} /> : <Avatar name={profileName || t('activity.you')} size={28} />;
  if (item.kind === 'group') {
    const { group } = item;
    const rule = group.ruleId ? rules[group.ruleId]?.name : undefined;
    const title = t(`activity.group.${group.kind}`, { n: format.number(item.entriesTotal, lang), rule: rule ?? t('activity.unknownRule'), context: group.actor });
    return (
      <li className={ROW} data-group-id={group.id}>
        {avatar}
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="font-ui text-[15px] leading-[22px] text-text">{title}</span>
          <span className={MUTED}>{`${format.time(at, lang)} · ${t('activity.changesCount', { count: item.entriesTotal, n: format.number(item.entriesTotal, lang) })}`}</span>
        </div>
      </li>
    );
  }
  const entry: JournalEntry = item.entry;
  const place = placeLabel(entry.after, t);
  return (
    <li className={ROW} data-journal-id={entry.id}>
      {avatar}
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className={`font-ui text-[15px] leading-[22px] text-text ${entry.undoState === 'undone' ? 'line-through' : ''}`}>{entryTitle(entry, documents, rules, t)}</span>
        <span className={MUTED}>
          {[format.time(at, lang), place].filter(Boolean).join(' · ')}
        </span>
      </div>
      {badgeLive(entry, badgeHours, now) ? <StatusPill status="filed" size="sm" lang={lang} /> : null}
      <EntryUndo entry={entry} busy={actions.busy} onUndo={actions.undo} onRedo={actions.redo} />
    </li>
  );
}

export function ActivityCard({ activity, profileName, badgeHours, now }: { activity: HomeView['activity']; profileName: string; badgeHours: number; now: number }) {
  const { t } = useTranslation();
  return (
    <ActionCard id="home-activity" title={t('home.activity.title')} seeAll={{ label: t('home.activity.all'), href: '/activity' }}>
      {activity.items.length === 0 ? (
        <Empty>{t('home.activity.empty')}</Empty>
      ) : (
        <ul className="m-0 flex flex-col p-0">
          {activity.items.map((item) => (
            <ActivityRow key={item.kind === 'group' ? item.group.id : item.entry.id} item={item} documents={activity.documents} rules={activity.rules} profileName={profileName} badgeHours={badgeHours} now={now} />
          ))}
        </ul>
      )}
    </ActionCard>
  );
}

export function IngestionCard({ ingestion }: { ingestion: HomeView['ingestion'] }) {
  const { t } = useTranslation();
  const lang = useLang();
  const figures = ingestionFigures(ingestion.days);
  const peakDay = figures.peakDate ? format.date(figures.peakDate, lang, 'dayMonth') : '';
  const caption = t('home.ingestion.chart', { peak: format.number(figures.peak, lang), day: peakDay, today: format.number(figures.today, lang) });
  return (
    <ActionCard id="home-ingestion" title={t('home.ingestion.title')} seeAll={{ label: t('home.ingestion.link'), href: '/activity' }}>
      <div className="flex flex-wrap items-end gap-x-6 gap-y-3">
        <div className="flex flex-col">
          <span className="font-ui text-[32px] leading-10 font-semibold text-text tabular-nums" data-testid="ingestion-week">
            {format.number(figures.week, lang)}
          </span>
          <span className={MUTED}>{t('home.ingestion.week', { count: figures.week })}</span>
        </div>
        <Sparkline values={ingestion.days.map((d) => d.count)} label={caption} />
      </div>
      <p className={`m-0 ${MUTED}`}>{caption}</p>
    </ActionCard>
  );
}
