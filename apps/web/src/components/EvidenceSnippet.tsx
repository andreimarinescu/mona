import { Icon, format, type Lang } from '@mona/ui';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import type { Evidence } from '../data/dto';
import { useLang } from '../shell/useLang';

export interface EvidenceSnippetProps {
  evidence: Evidence;
  /** Language of the printed quote; the `lang` attribute is set only when it differs from the interface language. */
  quoteLang?: Lang | null;
  active?: boolean;
  action?: ReactNode;
}

/** A verbatim quote with its page and whether it was found there (C1 §11.2). */
export function EvidenceSnippet({ evidence, quoteLang, active, action }: EvidenceSnippetProps) {
  const { t } = useTranslation();
  const lang = useLang();
  return (
    <div
      className={`flex flex-col gap-1 rounded-sm px-3 py-2 ${active ? 'bg-highlight outline outline-1 outline-highlight-edge' : 'bg-surface-sunken'}`}
      data-testid="evidence-snippet"
      data-verified={evidence.verified ? 'true' : 'false'}
    >
      <q lang={quoteLang && quoteLang !== lang ? quoteLang : undefined} className="font-ui text-[14px] leading-5 text-text">
        {evidence.quote}
      </q>
      <span className="flex flex-wrap items-center gap-x-3 gap-y-1 font-ui text-[13px] leading-[18px] text-text-muted">
        <span>{t('viewer.evidence.page', { n: format.number(evidence.page, lang) })}</span>
        <span className="inline-flex items-center gap-1">
          <Icon name={evidence.verified ? 'circle-check' : 'alert'} size={14} />
          {evidence.verified ? t('viewer.evidence.verified') : t('viewer.evidence.unverified')}
        </span>
        {action}
      </span>
    </div>
  );
}
