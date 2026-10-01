import { Button, MonaAvatar, format } from '@mona/ui';
import { useNavigate } from '@tanstack/react-router';
import { useTranslation } from 'react-i18next';
import { InternalLink } from '../../components/InternalLink';
import type { BriefFacts, Interview } from '../../data/dto';
import { get } from '../../data/http';
import { useLang } from '../../shell/useLang';
import { useAppState } from '../../state/context';
import { briefSentences, mostUrgent, type BriefLink, type BriefSentence } from './brief';

const LINK = 'rounded-xs text-info underline decoration-1 underline-offset-4 hover:text-accent-strong';

function hrefOf(link: BriefLink): string | null {
  switch (link.kind) {
    case 'review':
      return '/review';
    case 'activity':
      return '/activity';
    case 'document':
      return `/documents/${link.documentId}`;
    case 'questions':
      return null;
  }
}

/** The ids `start_interview` needs to show this interview again instead of starting another. */
async function pendingSummary(pending: { interviewId: string; openQuestions: number }): Promise<string> {
  const { interviewId: id, openQuestions: n } = pending;
  const interview = await get<Interview>(`/api/interviews/${id}`).catch(() => null);
  if (interview?.scope.type === 'batch') return `Home, batch ${interview.scope.batchId} debrief ${id}, ${n} questions`;
  if (interview?.scope.type === 'queue') return `Home, review queue debrief ${id}, ${n} questions`;
  return `Home, interview ${id}, ${n} questions`;
}

export interface MonaBriefProps {
  facts: BriefFacts;
  journalEntryCount: number;
  name: string;
  anonymous: boolean;
  /** The browser's clock, injected so a test fixes the time of day. */
  now?: Date;
}

export function MonaBrief({ facts, journalEntryCount, name, anonymous, now = new Date() }: MonaBriefProps) {
  const { t } = useTranslation();
  const lang = useLang();
  const navigate = useNavigate();
  const { openChat } = useAppState();
  const sentences = briefSentences(facts, { t, lang, hour: now.getHours(), name, anonymous });
  const urgent = mostUrgent(facts.dueSoon);

  async function questions(opener: HTMLElement) {
    if (!facts.pendingInterview) return;
    const summary = await pendingSummary(facts.pendingInterview);
    openChat({ opener, send: { message: t('chat.banner.debrief'), pageContext: { route: '/', summary } } });
  }

  function render(s: BriefSentence) {
    if (!s.link) return s.text;
    const href = hrefOf(s.link);
    if (href) {
      return (
        <InternalLink href={href} className={LINK} data-brief-link={s.id}>
          {s.text}
        </InternalLink>
      );
    }
    return (
      <button type="button" className={`cursor-pointer border-0 bg-transparent p-0 text-left font-[inherit] ${LINK}`} data-brief-link={s.id} onClick={(e) => void questions(e.currentTarget)}>
        {s.text}
      </button>
    );
  }

  return (
    <section aria-label={t('home.brief.label')} className="flex flex-col gap-4" data-testid="mona-brief">
      <div className="flex items-start gap-4">
        <span className="hidden shrink-0 sm:inline-flex">
          <MonaAvatar size={56} />
        </span>
        <h1 className="brief-heading text-text">
          {sentences.map((s, i) => (
            <span key={s.id} data-sentence={s.id}>
              {i > 0 ? ' ' : ''}
              {render(s)}
            </span>
          ))}
        </h1>
      </div>
      <div className="flex flex-wrap items-center gap-3 sm:pl-[72px]">
        {facts.needsReview.count > 0 ? (
          <Button variant="primary" iconEnd="arrow-right" onClick={() => void navigate({ to: '/review' })}>
            {t('home.brief.reviewAction', { count: facts.needsReview.count })}
          </Button>
        ) : null}
        {urgent?.documentId ? (
          <Button variant="secondary" icon="file" onClick={() => void navigate({ to: '/documents/$documentId', params: { documentId: urgent.documentId! } })}>
            {t('home.brief.openDue', { label: urgent.label })}
          </Button>
        ) : null}
        <span className="font-ui text-[13px] leading-[18px] text-text-muted" data-testid="brief-caption">
          {t('home.brief.caption', { time: format.time(facts.generatedAt, lang), count: journalEntryCount })}
        </span>
      </div>
    </section>
  );
}
