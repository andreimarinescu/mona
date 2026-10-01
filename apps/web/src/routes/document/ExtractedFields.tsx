import { Button, type Lang } from '@mona/ui';
import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { EvidenceSnippet } from '../../components/EvidenceSnippet';
import type { ExtractedField, FieldKey } from '../../data/dto';
import { useLang } from '../../shell/useLang';
import { formatFieldValue } from './search';

export interface ExtractedFieldsProps {
  fields: ExtractedField[];
  activeKey: FieldKey | null;
  focusKey?: FieldKey;
  quoteLang: Lang | null;
  onShow(field: ExtractedField): void;
}

export function ExtractedFields({ fields, activeKey, focusKey, quoteLang, onShow }: ExtractedFieldsProps) {
  const { t } = useTranslation();
  const lang = useLang();
  const focused = useRef<HTMLLIElement | null>(null);
  useEffect(() => {
    focused.current?.scrollIntoView?.({ block: 'nearest' });
    focused.current?.focus({ preventScroll: true });
  }, [focusKey]);

  if (fields.length === 0) return <p className="m-0 text-text-muted">{t('viewer.fields.none')}</p>;
  return (
    <ul className="m-0 flex list-none flex-col gap-4 p-0" aria-label={t('viewer.fields.label')}>
      {fields.map((field) => {
        const label = t(`review.field.${field.key}`);
        const active = activeKey === field.key;
        return (
          <li
            key={field.key}
            ref={field.key === focusKey ? focused : undefined}
            tabIndex={field.key === focusKey ? -1 : undefined}
            className="flex flex-col gap-2 outline-none"
            data-field={field.key}
            data-active={active ? 'true' : undefined}
          >
            <div className="flex items-baseline gap-3">
              <span className="w-[76px] shrink-0 font-ui text-[14px] leading-5 text-text-muted">{label}</span>
              <span className="min-w-0 flex-1 break-words font-ui text-[15px] leading-[22px] font-medium text-text">{formatFieldValue(field, lang)}</span>
              <Button variant="ghost" size="sm" aria-label={t('viewer.fields.showOn', { field: label })} aria-pressed={active} onClick={() => onShow(field)}>
                {active ? t('viewer.fields.showing') : t('viewer.fields.show')}
              </Button>
            </div>
            <EvidenceSnippet evidence={field.evidence} quoteLang={quoteLang} active={active} />
          </li>
        );
      })}
    </ul>
  );
}
