import { Button, MonaAvatar, format } from '@mona/ui';
import { useNavigate } from '@tanstack/react-router';
import { useTranslation } from 'react-i18next';
import { InternalLink } from '../../components/InternalLink';
import type { BriefFacts } from '../../data/dto';
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

  const questions = () =>
    openChat({ send: { message: t('chat.banner.debrief'), pageContext: { route: '/', summary: `Home, ${facts.pendingInterview?.openQuestions ?? 0} questions` } } });

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
      <button type="button" className={`cursor-pointer border-0 bg-transparent p-0 text-left font-[inherit] ${LINK}`} data-brief-link={s.id} onClick={questions}>
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
