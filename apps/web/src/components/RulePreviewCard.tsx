import { Badge, Button, Card, format } from '@mona/ui';
import { useTranslation } from 'react-i18next';
import type { RulePreview } from '../data/dto';
import { useLang } from '../shell/useLang';
import { InternalLink } from './InternalLink';
import { PathDiff } from './PathDiff';

export interface RulePreviewCardProps {
  preview: RulePreview;
  applying?: boolean;
  onApply?: () => void;
  /** Inside another card (the scope prompt): no card chrome of its own. */
  embedded?: boolean;
  /** A line next to the actions. */
  hint?: string;
}

export function RulePreviewCard({ preview, applying, onApply, embedded, hint }: RulePreviewCardProps) {
  const { t } = useTranslation();
  const lang = useLang();
  const { rule } = preview;
  const n = (v: number) => format.number(v, lang);
  const footer = (
        <div className="flex flex-wrap items-center gap-3">
          {preview.applied ? (
            <span className="font-ui text-[14px] leading-5 font-semibold text-success" role="status">
              {t('rules.preview.applied', { count: preview.movesTotal, n: n(preview.movesTotal) })}
            </span>
          ) : (
            <Button variant="primary" loading={applying} onClick={onApply}>
              {t('rules.preview.apply')}
            </Button>
          )}
          <InternalLink href={`/rules/${rule.id}`} className="mona-btn mona-btn--ghost no-underline">
            {t('rules.preview.adjust')}
          </InternalLink>
          {hint ? <span className="font-ui text-[13px] leading-[18px] text-text-muted">{hint}</span> : null}
        </div>
  );
  const body = (
      <div className="flex flex-col gap-3" data-testid="rule-preview">
        <p className="m-0 font-ui text-[14px] leading-5 text-text-muted">{rule.condition}</p>
        <p className="m-0 font-ui text-[15px] leading-[22px] font-semibold text-text">
          {t('rules.preview.counts', { moves: n(preview.movesTotal), stays: n(preview.staysTotal) })}
        </p>
        {preview.movesTotal === 0 ? <p className="m-0 text-text-muted">{t('rules.preview.noMoves')}</p> : null}
        <ul className="m-0 flex list-none flex-col divide-y divide-border p-0">
          {preview.moves.map((move) => (
            <li key={move.documentId} className="flex flex-col gap-2 py-3 md:flex-row md:items-start md:gap-6">
              <span className="min-w-0 flex-1 truncate font-ui text-[14px] leading-5 text-text" title={move.title}>
                {move.title}
              </span>
              <div className="flex-[2]">
                <PathDiff from={move.from} to={move.to} fromFileName={move.fromFileName} toFileName={move.toFileName} />
              </div>
            </li>
          ))}
        </ul>
        {preview.moves.length < preview.movesTotal ? (
          <p className="m-0 text-text-muted">{t('rules.preview.more', { count: preview.movesTotal - preview.moves.length, n: n(preview.movesTotal - preview.moves.length) })}</p>
        ) : null}
      </div>
  );
  if (embedded) {
    return (
      <section aria-label={t('rules.preview.eyebrow')} className="flex flex-col gap-3 border-t border-border pt-4">
        <div className="flex flex-wrap items-center gap-3">
          <span className="font-ui text-[12px] leading-4 font-semibold tracking-[0.12em] text-text-muted uppercase">{t('rules.preview.eyebrow')}</span>
          <Badge tone="neutral">{t(`rules.source.${rule.source}`)}</Badge>
        </div>
        <h3 className="m-0 text-text [font:var(--type-heading)]">{rule.name}</h3>
        {body}
        {footer}
      </section>
    );
  }
  return (
    <Card from="mona" lang={lang} eyebrow={t('rules.preview.eyebrow')} title={rule.name} meta={<Badge tone="neutral">{t(`rules.source.${rule.source}`)}</Badge>} footer={footer}>
      {body}
    </Card>
  );
}
