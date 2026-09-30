import { ConfidenceMeter, MonaAvatar } from '@mona/ui';
import { useTranslation } from 'react-i18next';
import { InternalLink } from '../../components/InternalLink';
import type { Suggestion } from '../../data/dto';
import { useThresholds } from '../../data/registry';
import { useLang } from '../../shell/useLang';
import type { Lang } from '@mona/ui';

export interface SuggestionPanelProps {
  suggestion: Suggestion;
  showMeter: boolean;
  quoteLang: Lang | null;
}

export function SuggestionPanel({ suggestion, showMeter, quoteLang }: SuggestionPanelProps) {
  const { t } = useTranslation();
  const lang = useLang();
  const { confidenceHigh, confidenceLow } = useThresholds();
  return (
    <section aria-label={t('review.suggestion.region')} className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <MonaAvatar size={32} />
        <span className="font-ui text-[12px] leading-4 font-semibold tracking-[0.12em] text-text-muted uppercase">{t('review.suggestion.eyebrow')}</span>
        {showMeter ? (
          <ConfidenceMeter value={suggestion.confidence} lang={lang} thresholds={{ high: confidenceHigh / 100, medium: confidenceLow / 100 }} className="ml-auto" />
        ) : null}
      </div>
      <p className="m-0 text-text [font:var(--type-voice)]" data-testid="suggestion-sentence">
        {suggestion.sentence}
      </p>
      {suggestion.evidence.length > 0 ? (
        <ol className="m-0 flex list-none flex-col gap-3 p-0" aria-label={t('review.suggestion.evidence')}>
          {suggestion.evidence.map((ev, i) => {
            const href = `/documents/${ev.documentId}?page=${ev.page}${ev.findQuery ? `&q=${encodeURIComponent(ev.findQuery)}` : ''}${ev.field ? `&field=${ev.field}` : ''}`;
            return (
              <li key={`${ev.documentId}-${i}`} className="flex items-start gap-3">
                <span aria-hidden className="inline-flex size-6 shrink-0 items-center justify-center rounded-full bg-warning font-ui text-[13px] leading-none font-semibold text-on-accent">
                  {i + 1}
                </span>
                <span className="flex min-w-0 flex-col gap-0.5">
                  <q lang={quoteLang ?? undefined} className="font-ui text-[15px] leading-[22px] text-text">
                    {ev.quote}
                  </q>
                  <span className="font-ui text-[13px] leading-[18px] text-text-muted">
                    {ev.field ? `${t(`review.field.${ev.field}`)} · ` : ''}
                    <InternalLink href={href} className="text-info underline">
                      {t('review.suggestion.page', { n: ev.page })}
                    </InternalLink>
                    {ev.verified ? '' : ` · ${t('review.suggestion.unverified')}`}
                  </span>
                </span>
              </li>
            );
          })}
        </ol>
      ) : null}
    </section>
  );
}
