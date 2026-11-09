import { Button, Table, format, type Lang } from '@mona/ui';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { fetchFile } from '../../data/cards';
import type { TableColumnKey, TableFileFormat, TableView } from '../../data/dto';
import { makeTableFile, useExportTable } from '../../data/exports';
import { ApiError } from '../../data/http';
import { toastFailure } from '../../data/journal';
import { dateLabel } from '../../routes/archive/labels';
import { useLang } from '../../shell/useLang';
import { useChatCard } from '../context';
import { CardShell } from './CardShell';
import { saveBlob } from './saveBlob';

type Row = TableView['rows'][number];
const FORMATS: TableFileFormat[] = ['csv', 'xlsx', 'docx'];
const DATES = new Set<TableColumnKey>(['doc_date', 'due_date']);

function cell(row: Row, key: TableColumnKey, lang: Lang): string {
  const v = row[key];
  if (v === null || v === undefined || v === '') return '—';
  if (key === 'amount' && typeof v === 'number') return row.currency ? format.money(v, String(row.currency), lang) : format.number(v, lang, { minimumFractionDigits: 2 });
  if (DATES.has(key) && typeof v === 'string') return dateLabel(v, lang);
  return String(v);
}

/** A36: the table Mona built from typed rows, with Download as CSV, Excel or Word. */
export function TableCard({ table: snapshot }: { table: TableView }) {
  const { t } = useTranslation();
  const lang = useLang();
  const card = useChatCard();
  const query = useExportTable(snapshot);
  const table = query.data;
  const [making, setMaking] = useState<TableFileFormat | null>(null);
  const emptied = query.error instanceof ApiError && query.error.status === 409;
  const more = table.rowsTotal > table.rows.length || table.truncated;
  const labels = new Map(table.columns.map((c) => [c.key, c.label]));

  async function download(fmt: TableFileFormat) {
    setMaking(fmt);
    try {
      const pack = await makeTableFile(table.id, fmt, card.conversationId());
      const { blob, name } = await fetchFile(pack.fileUrl ?? `/api/exports/${pack.id}/${fmt}`, pack.fileName ?? `${table.title}.${fmt}`);
      saveBlob(blob, name);
    } catch (err) {
      toastFailure(err);
    } finally {
      setMaking(null);
    }
  }

  return (
    <CardShell kind="table" id={table.id} label={table.title}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex min-w-0 flex-col gap-1">
          <h3 className="m-0 font-ui text-[18px] leading-[26px] font-semibold text-text">{table.title}</h3>
          <p className="m-0 font-ui text-[14px] leading-5 text-text-muted" data-testid="table-meta">
            {more
              ? t('chat.table.showing', { shown: format.number(table.rows.length, lang), total: format.number(table.rowsTotal, lang) })
              : t('chat.table.count', { count: table.rowsTotal, n: format.number(table.rowsTotal, lang) })}
          </p>
        </div>
        <Button variant="quiet" size="sm" loading={query.isFetching} onClick={() => void query.refetch()}>
          {t('chat.table.refresh')}
        </Button>
      </div>
      {emptied ? (
        <p className="m-0 font-ui text-[15px] leading-[22px] text-text-muted" role="status">
          {t('chat.table.emptied')}
        </p>
      ) : (
        <>
          <div
            role="region"
            aria-label={table.title}
            tabIndex={0}
            lang={table.lang !== lang ? table.lang : undefined}
            className="max-h-[420px] overflow-auto rounded-md [&>.mona-table-wrap]:overflow-visible!"
            data-testid="table-rows"
          >
            <Table
              caption={<span className="mona-sr">{table.title}</span>}
              rows={table.rows}
              columns={table.columns.map((c) => ({
                key: c.key,
                label: c.label,
                numeric: c.key === 'amount',
                align: c.key === 'amount' ? ('end' as const) : undefined,
                render: (r: Row) => <span className={DATES.has(c.key) || c.key === 'amount' ? 'whitespace-nowrap' : undefined}>{cell(r, c.key, table.lang)}</span>,
              }))}
            />
          </div>
          {table.truncated ? <p className="m-0 font-ui text-[14px] leading-5 text-text">{t('chat.table.truncated')}</p> : null}
          {table.emptyColumns.length > 0 ? (
            <p className="m-0 font-ui text-[14px] leading-5 text-text-muted" data-testid="table-empty-columns">
              {t('chat.table.emptyColumns', { columns: table.emptyColumns.map((k) => labels.get(k) ?? k).join(', ') })}
            </p>
          ) : null}
          <div className="flex flex-wrap items-center gap-3" role="group" aria-labelledby={`${table.id}-download`}>
            <span id={`${table.id}-download`} className="font-ui text-[14px] leading-5 text-text-muted">
              {t('chat.table.downloadAs')}
            </span>
            {FORMATS.map((fmt) => (
              <Button key={fmt} variant="secondary" size="sm" icon="download" loading={making === fmt} disabled={making !== null && making !== fmt} onClick={() => void download(fmt)}>
                {t(`export.table.format.${fmt}`)}
              </Button>
            ))}
          </div>
        </>
      )}
    </CardShell>
  );
}
