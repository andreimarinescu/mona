import { StatusPill } from '@mona/ui';
import { useTranslation } from 'react-i18next';
import type { DocumentSummary } from '../data/dto';
import { useLang } from '../shell/useLang';

/** A document's status; "Filed by Mona" shows only while the C7 §6 badge window is open (`badgeUntil`). */
export function DocStatusPill({ doc, size }: { doc: Pick<DocumentSummary, 'status' | 'badgeUntil'>; size?: 'md' | 'sm' }) {
  const { t } = useTranslation();
  const lang = useLang();
  const plainFiled = doc.status === 'filed' && doc.badgeUntil === null;
  return <StatusPill status={doc.status} size={size} lang={lang} label={plainFiled ? t('common.filed') : undefined} />;
}
