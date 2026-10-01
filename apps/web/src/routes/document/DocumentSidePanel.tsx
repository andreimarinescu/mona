import { ConfidenceMeter, type Lang } from '@mona/ui';
import { useTranslation } from 'react-i18next';
import type { DocumentDetail, ExtractedField, FieldKey } from '../../data/dto';
import { useThresholds } from '../../data/registry';
import { JournalTimeline } from '../../journal/JournalTimeline';
import { useSettings } from '../../data/hooks';
import { useLang } from '../../shell/useLang';
import { ExtractedFields } from './ExtractedFields';
import { FiledSection } from './FiledSection';
import { ReminderControl } from './ReminderControl';

export interface DocumentSidePanelProps {
  doc: DocumentDetail;
  activeField: FieldKey | null;
  focusField?: FieldKey;
  quoteLang: Lang | null;
  onShow(field: ExtractedField): void;
}

export function DocumentSidePanel({ doc, activeField, focusField, quoteLang, onShow }: DocumentSidePanelProps) {
  const { t } = useTranslation();
  const lang = useLang();
  const { confidenceHigh, confidenceLow } = useThresholds();
  const profileName = useSettings().data?.profileName ?? '';
  return (
    <div className="flex flex-col gap-6 p-5" data-testid="side-panel">
      <section aria-labelledby="read-heading" className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <h2 id="read-heading" className="m-0 flex-1 text-text [font:var(--type-heading)]">
            {t('viewer.read.title')}
          </h2>
          {doc.confidence !== null ? (
            <ConfidenceMeter value={doc.confidence} lang={lang} thresholds={{ high: confidenceHigh / 100, medium: confidenceLow / 100 }} />
          ) : null}
        </div>
        <ExtractedFields fields={doc.fields} activeKey={activeField} focusKey={focusField} quoteLang={quoteLang} onShow={onShow} />
        {doc.fields.length > 0 ? <p className="m-0 font-ui text-[13px] leading-[18px] text-text-muted">{t('viewer.read.hint')}</p> : null}
      </section>
      <hr className="m-0 border-0 border-t border-border" />
      <FiledSection doc={doc} />
      <hr className="m-0 border-0 border-t border-border" />
      <ReminderControl doc={doc} />
      <hr className="m-0 border-0 border-t border-border" />
      <section aria-labelledby="history-heading" className="flex flex-col gap-3">
        <h3 id="history-heading" className="m-0 text-text [font:var(--type-heading)]">
          {t('viewer.history.title')}
        </h3>
        <JournalTimeline entries={doc.journal} documents={{ [doc.id]: { title: doc.title, fileName: doc.fileName, deleted: false } }} profileName={profileName} />
      </section>
    </div>
  );
}
