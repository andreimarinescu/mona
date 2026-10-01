import { Icon, Table } from '@mona/ui';
import { Link } from '@tanstack/react-router';
import { useTranslation } from 'react-i18next';
import { DocStatusPill } from '../../components/DocStatusPill';
import type { DocumentSummary } from '../../data/dto';
import { useLang } from '../../shell/useLang';
import { amountLabel, dateLabel } from './labels';

export function DocumentLink({ doc, q }: { doc: Pick<DocumentSummary, 'id' | 'title'>; q?: string }) {
  return (
    <Link to="/documents/$documentId" params={{ documentId: doc.id }} search={q ? { q } : {}} className="font-ui text-[15px] leading-[22px] font-semibold text-text no-underline hover:underline">
      {doc.title}
    </Link>
  );
}

export interface ResultsTableProps {
  rows: DocumentSummary[];
  /** The search text, carried to the viewer so pdf.js finds it on open (C2 §4.4). */
  q?: string;
  busy?: boolean;
}

export function ResultsTable({ rows, q, busy }: ResultsTableProps) {
  const { t } = useTranslation();
  const lang = useLang();
  return (
    <div aria-busy={busy || undefined} className={busy ? 'opacity-60' : undefined} data-testid="results-table">
      <Table
        rowKey="id"
        rows={rows}
        columns={[
          {
            key: 'title',
            label: t('archive.table.document'),
            render: (d: DocumentSummary) => (
              <span className="flex items-center gap-3">
                <span aria-hidden className="inline-flex size-9 shrink-0 items-center justify-center rounded-sm bg-surface-sunken text-text-muted">
                  <Icon name="file" size={18} />
                </span>
                <span className="flex min-w-0 flex-col">
                  <DocumentLink doc={d} q={q} />
                  <span className="break-all text-text-muted [font:var(--type-filename)]">{d.fileName}</span>
                </span>
              </span>
            ),
          },
          { key: 'entity', label: t('archive.table.entity'), render: (d: DocumentSummary) => d.entityName ?? '—' },
          { key: 'date', label: t('archive.table.date'), render: (d: DocumentSummary) => <span className="whitespace-nowrap">{dateLabel(d.date, lang)}</span> },
          { key: 'amount', label: t('archive.table.amount'), numeric: true, align: 'end', render: (d: DocumentSummary) => amountLabel(d, lang) },
          { key: 'status', label: t('archive.table.status'), render: (d: DocumentSummary) => <DocStatusPill doc={d} size="sm" /> },
        ]}
      />
    </div>
  );
}
