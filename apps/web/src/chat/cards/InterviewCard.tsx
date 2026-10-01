import { Badge, Button, MonaAvatar, Skeleton, format, type Lang } from '@mona/ui';
import { useMutation, useQueries, useQueryClient } from '@tanstack/react-query';
import { useId, type KeyboardEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { InternalLink } from '../../components/InternalLink';
import { answerQuestion, applyAll, interviewKey, rulePreviewKey, skipQuestion, storePreviews, storeQuestion, useInterview } from '../../data/cards';
import type { Evidence, Interview, InterviewOption, InterviewQuestion, RulePreview } from '../../data/dto';
import { errorKey, errorValues } from '../../data/errors';
import { get, retryTransient } from '../../data/http';
import { invalidateAfterWrite, useUndoRunner } from '../../data/journal';
import { useLang } from '../../shell/useLang';
import { toasts } from '../../toast/store';
import { useChatCard } from '../context';
import { CardShell, Overline } from './CardShell';
import { ChatRulePreview } from './ChatRulePreview';

/** Quotes are shown as printed; v1 takes the default filing language for them (C8 §3.3). */
const QUOTE_LANG: Lang = 'fr';
const KEYS = ['1', '2', '3'];

function evidenceHref(e: Evidence): string {
  const params = new URLSearchParams({ page: String(e.page) });
  if (e.findQuery) params.set('q', e.findQuery);
  return `/documents/${e.documentId}?${params.toString()}`;
}

function Marked({ quote, term }: { quote: string; term: string | null }) {
  const at = term ? quote.toLowerCase().indexOf(term.toLowerCase()) : -1;
  if (!term || at < 0) return <>{quote}</>;
  return (
    <>
      {quote.slice(0, at)}
      <mark className="rounded-xs bg-highlight px-0.5 text-text outline outline-1 outline-highlight-edge">{quote.slice(at, at + term.length)}</mark>
      {quote.slice(at + term.length)}
    </>
  );
}

/** HANDOFF `EvidenceSnippet`: file name, page and quote with its term marked; opens the viewer there (C2 §4.4). */
function EvidenceLink({ evidence }: { evidence: Evidence }) {
  const { t } = useTranslation();
  const lang = useLang();
  return (
    <InternalLink
      href={evidenceHref(evidence)}
      className="flex min-w-0 flex-1 basis-48 flex-col gap-2 rounded-md bg-surface-sunken p-3 text-text no-underline hover:bg-highlight"
      data-testid="evidence-snippet"
      title={t('interview.evidence', { title: evidence.documentTitle, page: evidence.page })}
    >
      <span className="truncate font-code text-[13px] leading-[18px] text-text-muted">
        {evidence.documentTitle} · {t('viewer.evidence.page', { n: format.number(evidence.page, lang) })}
      </span>
      <span lang={QUOTE_LANG !== lang ? QUOTE_LANG : undefined} className="font-ui text-[14px] leading-5">
        …<Marked quote={evidence.quote} term={evidence.findQuery} />…
      </span>
    </InternalLink>
  );
}

function OptionButton({ option, index, busy, picked, onPick }: { option: InterviewOption; index: number; busy: boolean; picked: boolean; onPick(): void }) {
  const { t } = useTranslation();
  const hint = useId();
  return (
    <span className="inline-flex flex-col items-center gap-1">
      <Button
        variant={option.suggested ? 'primary' : 'secondary'}
        icon={option.suggested ? 'check' : undefined}
        loading={picked}
        disabled={busy}
        data-option={option.id}
        aria-keyshortcuts={KEYS[index]}
        aria-describedby={option.suggested ? hint : undefined}
        onClick={onPick}
      >
        {option.label}
      </Button>
      {option.suggested ? (
        <span id={hint} className="font-ui text-[13px] leading-[18px] font-semibold text-accent-strong">
          {t('interview.suggested')}
        </span>
      ) : null}
    </span>
  );
}

function OpenQuestion({ interview, question }: { interview: Interview; question: InterviewQuestion }) {
  const { t } = useTranslation();
  const lang = useLang();
  const qc = useQueryClient();
  const card = useChatCard();
  const heading = useId();
  const answer = useMutation({
    mutationFn: (option: InterviewOption) => answerQuestion(interview.id, question.id, { optionId: option.id }, card.conversationId()),
    onSuccess: (result) => {
      storePreviews(qc, result.previews);
      storeQuestion(qc, interview.id, result.question, result.interviewStatus);
    },
    onError: (err) => {
      toasts.push({ key: 'answer-failed', message: errorKey(err), values: errorValues(err), tone: 'danger' });
      void qc.invalidateQueries({ queryKey: interviewKey(interview.id) });
    },
  });
  const skip = useMutation({
    mutationFn: () => skipQuestion(interview.id, question.id, card.conversationId()),
    onSuccess: (q) => {
      const open = interview.questions.filter((x) => x.status === 'open' && x.id !== q.id).length;
      storeQuestion(qc, interview.id, q, open === 0 ? 'done' : undefined);
    },
    onError: (err) => toasts.push({ key: 'skip-failed', message: errorKey(err), values: errorValues(err), tone: 'danger' }),
  });
  const busy = answer.isPending || skip.isPending;
  const options = question.options.slice(0, KEYS.length);

  function onKey(e: KeyboardEvent<HTMLDivElement>) {
    if (e.ctrlKey || e.metaKey || e.altKey || busy) return;
    const option = options[KEYS.indexOf(e.key)];
    if (!option) return;
    e.preventDefault();
    answer.mutate(option);
  }

  return (
    <div
      role="group"
      aria-labelledby={heading}
      tabIndex={0}
      onKeyDown={onKey}
      className="flex flex-col gap-4 rounded-md outline-offset-4"
      data-testid="open-question"
      data-question={question.id}
    >
      <p id={heading} className="m-0 text-text [font:var(--type-voice)]" lang={question.lang !== lang ? question.lang : undefined}>
        {question.question}
      </p>
      {question.evidence.length > 0 ? (
        <div className="flex flex-wrap gap-3">
          {question.evidence.slice(0, 3).map((e, i) => (
            <EvidenceLink key={`${e.documentId}-${i}`} evidence={e} />
          ))}
        </div>
      ) : null}
      <div className="flex flex-wrap items-start gap-3">
        {options.map((o, i) => (
          <OptionButton key={o.id} option={o} index={i} busy={busy} picked={answer.isPending && answer.variables?.id === o.id} onPick={() => answer.mutate(o)} />
        ))}
        <Button
          variant="secondary"
          icon="pencil"
          disabled={busy}
          onClick={() => card.prefill(t('interview.explain.prefill', { question: question.question }), `Interview ${interview.id}, question ${question.id} open`)}
        >
          {t('interview.explain.link')}
        </Button>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-ui text-[13px] leading-[18px] text-text-muted">{t('interview.keys')}</span>
        <Button variant="quiet" size="sm" disabled={busy} loading={skip.isPending} onClick={() => skip.mutate()}>
          {t('interview.skip')}
        </Button>
      </div>
    </div>
  );
}

function usePreviews(ruleIds: string[]) {
  return useQueries({
    queries: ruleIds.map((id) => ({
      queryKey: rulePreviewKey(id),
      staleTime: 30_000,
      retry: retryTransient,
      queryFn: ({ signal }: { signal: AbortSignal }) => get<RulePreview>(`/api/rules/${id}/preview`, { limit: 20 }, signal),
    })),
  });
}

function AnsweredQuestion({ interview, question }: { interview: Interview; question: InterviewQuestion }) {
  const { t } = useTranslation();
  const lang = useLang();
  const qc = useQueryClient();
  const card = useChatCard();
  const undo = useUndoRunner();
  const ruleIds = question.answer?.ruleIds ?? [];
  const previews = usePreviews(ruleIds).map((q) => q.data);
  const option = question.options.find((o) => o.id === question.answer?.optionId);
  const drafts = previews.filter((p) => p?.rule.state === 'draft').length;
  const allApplied = ruleIds.length >= 2 && previews.every((p) => p?.applied);
  const apply = useMutation({
    mutationFn: () => applyAll(interview.id, question.id, card.conversationId()),
    onSuccess: ({ results }) => {
      storePreviews(qc, results.map((r) => r.preview));
      const groups = results.map((r) => r.groupId).filter((g): g is string => g !== null);
      const moved = results.reduce((sum, r) => sum + r.moved, 0);
      if (groups.length > 0) {
        toasts.push({
          key: `apply-all-${question.id}`,
          message: 'interview.toast.appliedAll',
          count: moved,
          undo: () => void Promise.all(groups.map((groupId) => undo({ groupId }, 'undo', card.conversationId()))),
        });
      }
      void invalidateAfterWrite(qc);
    },
    onError: (err) => toasts.push({ key: 'apply-failed', message: errorKey(err), values: errorValues(err), tone: 'danger' }),
  });
  const answerLine = question.status === 'skipped'
    ? t('interview.skipped')
    : option
      ? t('interview.answered', { answer: option.label })
      : question.answer?.freeText
        ? t('interview.answeredText', { text: question.answer.freeText })
        : null;
  const ruleNote = question.status === 'answered' && ruleIds.length === 0 ? t('interview.noRule') : option?.ruleDraft?.kind === 'ask' ? t('interview.askRule') : null;
  return (
    <section className="flex flex-col gap-3" data-testid="answered-question" data-question={question.id} aria-label={question.question}>
      <p className="m-0 font-ui text-[15px] leading-[22px] text-text" lang={question.lang !== lang ? question.lang : undefined}>
        {question.question}
      </p>
      {answerLine ? <p className="m-0 font-ui text-[15px] leading-[22px] font-semibold text-text">{answerLine}</p> : null}
      {ruleNote ? <p className="m-0 font-ui text-[14px] leading-5 text-text-muted">{ruleNote}</p> : null}
      {option?.ruleDraft?.kind !== 'ask'
        ? ruleIds.map((id) => <ChatRulePreview key={id} ruleId={id} embedded />)
        : null}
      {ruleIds.length >= 2 && option?.ruleDraft?.kind !== 'ask' ? (
        <div className="flex flex-wrap items-center gap-3 border-t border-border pt-4">
          {allApplied ? (
            <span role="status" className="font-ui text-[14px] leading-5 font-semibold text-success">
              {t('interview.appliedAll', { count: ruleIds.length })}
            </span>
          ) : (
            <Button variant="primary" icon="check" loading={apply.isPending} disabled={drafts === 0} onClick={() => apply.mutate()} data-testid="apply-all">
              {t('interview.applyAll', { count: ruleIds.length })}
            </Button>
          )}
        </div>
      ) : null}
    </section>
  );
}

export function InterviewCard({ interview: snapshot }: { interview: Interview }) {
  const { t } = useTranslation();
  const interview = useInterview(snapshot).data;
  const current = interview.questions.find((q) => q.status === 'open');
  const settled = interview.questions.filter((q) => q.status !== 'open');
  const total = interview.questions.length;
  const generating = interview.status === 'generating';
  return (
    <CardShell kind="interview" id={interview.id} className="border-border-strong shadow-2" label={t('interview.eyebrow')}>
      <div className="flex flex-wrap items-center gap-3" data-status={interview.status}>
        <MonaAvatar size={28} state={generating ? 'thinking' : 'idle'} />
        <Overline>{t('interview.eyebrow')}</Overline>
        {current && total > 1 ? (
          <span className="font-ui text-[13px] leading-[18px] text-text-muted">{t('interview.progress', { n: current.ordinal, total })}</span>
        ) : null}
        <span className="flex-1" />
        {current ? <Badge tone="info">{t('interview.affects', { count: current.affectsCount })}</Badge> : null}
      </div>
      {generating ? (
        <div className="flex flex-col gap-3" role="status">
          <p className="m-0 font-ui text-[15px] leading-[22px] text-text-muted">{t('interview.generating')}</p>
          <Skeleton lines={3} />
        </div>
      ) : null}
      {interview.status === 'failed' ? (
        <p className="m-0 font-ui text-[15px] leading-[22px] text-text-muted">{interview.error === 'no_questions' ? t('interview.error.no_questions') : t('interview.error.failed')}</p>
      ) : null}
      {interview.status === 'cancelled' ? <p className="m-0 font-ui text-[15px] leading-[22px] text-text-muted">{t('interview.cancelled')}</p> : null}
      {settled.map((q) => (
        <AnsweredQuestion key={q.id} interview={interview} question={q} />
      ))}
      {current && interview.status !== 'cancelled' ? (
        <div className={settled.length > 0 ? 'border-t border-border pt-4' : undefined}>
          <OpenQuestion key={current.id} interview={interview} question={current} />
        </div>
      ) : null}
      {interview.status === 'done' ? <p className="m-0 font-voice text-[18px] leading-[26px] text-text">{t('interview.done')}</p> : null}
    </CardShell>
  );
}
