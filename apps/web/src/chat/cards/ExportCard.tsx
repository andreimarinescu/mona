import { Icon, Spinner, format } from '@mona/ui';
import { useTranslation } from 'react-i18next';
import type { ExportPack } from '../../data/dto';
import { useExportPack } from '../../data/exports';
import { useLang } from '../../shell/useLang';
import { CardShell } from './CardShell';

export function ExportCard({ pack: snapshot }: { pack: ExportPack }) {
  const { t } = useTranslation();
  const lang = useLang();
  const pack = useExportPack(snapshot.id, snapshot).data ?? snapshot;
  const n = pack.documentCount ?? 0;
  if (pack.format) return <TableExport pack={pack} />;
  return (
    <CardShell kind="export" id={pack.id} label={t('export.card.title')}>
      <div className="flex flex-col gap-1">
        <h3 className="m-0 font-ui text-[18px] leading-[26px] font-semibold text-text">{t('export.card.title')}</h3>
        <p className="m-0 font-ui text-[14px] leading-5 text-text-muted">{t('export.card.meta', { entity: pack.entityName, year: pack.fiscalYear })}</p>
      </div>
      {pack.status === 'building' ? <Spinner size={20} label={t('export.building')} /> : null}
      {pack.status === 'failed' ? (
        <div className="flex flex-col gap-1" role="status">
          <strong className="font-ui text-[15px] leading-[22px] text-text">{t('export.failed.title')}</strong>
          <span className="font-ui text-[14px] leading-5 text-text-muted">{t('export.failed.body')}</span>
        </div>
      ) : null}
      {pack.status === 'ready' ? (
        <div className="flex flex-col gap-3">
          <p className="m-0 font-ui text-[15px] leading-[22px] text-text">
            {t('export.ready.body', { count: n, n: format.number(n, lang), entity: pack.entityName, year: pack.fiscalYear })}
          </p>
          <div className="flex flex-wrap gap-3">
            {pack.zipUrl ? (
              <a href={pack.zipUrl} download className="mona-btn mona-btn--secondary no-underline">
                <Icon name="download" size={18} />
                {t('export.ready.zip')}
              </a>
            ) : null}
            {pack.csvUrl ? (
              <a href={pack.csvUrl} download className="mona-btn mona-btn--secondary no-underline">
                <Icon name="download" size={18} />
                {t('export.ready.csv')}
              </a>
            ) : null}
          </div>
          <p className="m-0 font-ui text-[13px] leading-[18px] text-text-muted">{t('export.ready.hint')}</p>
        </div>
      ) : null}
    </CardShell>
  );
}

function TableExport({ pack }: { pack: ExportPack }) {
  const { t } = useTranslation();
  const lang = useLang();
  const n = pack.documentCount ?? 0;
  const kind = t(`export.table.format.${pack.format}`);
  return (
    <CardShell kind="export" id={pack.id} label={t('export.table.title')}>
      <div className="flex flex-col gap-1">
        <h3 className="m-0 font-ui text-[18px] leading-[26px] font-semibold text-text">{pack.title ?? t('export.table.title')}</h3>
        <p className="m-0 font-ui text-[14px] leading-5 text-text-muted" data-testid="export-table-meta">
          {t('export.table.meta', { count: n, n: format.number(n, lang), format: kind })}
        </p>
      </div>
      {pack.truncated ? <p className="m-0 font-ui text-[14px] leading-5 text-text">{t('export.table.truncated')}</p> : null}
      {pack.status === 'failed' ? (
        <div className="flex flex-col gap-1" role="status">
          <strong className="font-ui text-[15px] leading-[22px] text-text">{t('export.failed.title')}</strong>
          <span className="font-ui text-[14px] leading-5 text-text-muted">{t('export.failed.body')}</span>
        </div>
      ) : null}
      {pack.status === 'ready' && pack.fileUrl ? (
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap gap-3">
            <a href={pack.fileUrl} download={pack.fileName ?? true} className="mona-btn mona-btn--secondary no-underline">
              <Icon name="download" size={18} />
              {t('export.table.download', { format: kind })}
            </a>
          </div>
          <p className="m-0 font-ui text-[13px] leading-[18px] text-text-muted">{t('export.ready.hint')}</p>
        </div>
      ) : null}
    </CardShell>
  );
}
