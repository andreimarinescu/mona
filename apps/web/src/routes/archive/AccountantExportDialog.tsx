import { Banner, Button, Dialog, Icon, MonaAvatar, Select, Skeleton, Spinner, format } from '@mona/ui';
import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { ExportPack, ExportPreview } from '../../data/dto';
import { errorKey, errorValues } from '../../data/errors';
import { startExport, useExportPack, useExportPreview } from '../../data/exports';
import { useCategories, useEntityList } from '../../data/registry';
import { useLang } from '../../shell/useLang';
import { useAppState } from '../../state/context';

export interface AccountantExportDialogProps {
  open: boolean;
  onClose(): void;
}

export function AccountantExportDialog({ open, onClose }: AccountantExportDialogProps) {
  return open ? <ExportBody onClose={onClose} /> : null;
}

function Included({ preview }: { preview: ExportPreview }) {
  const { t } = useTranslation();
  const lang = useLang();
  const categories = useCategories().data ?? [];
  const n = (v: number) => format.number(v, lang);
  const byCategory = preview.categories.map((c) => `${categories.find((x) => x.id === c.id)?.labels[lang] ?? c.label} ${n(c.count)}`).join(' · ');
  return (
    <fieldset className="m-0 flex flex-col gap-3 border-0 p-0" data-testid="export-included">
      <legend className="mb-2 p-0 font-ui text-[14px] leading-5 font-semibold text-text">{t('export.included.title')}</legend>
      <ul className="m-0 flex list-none flex-col gap-3 p-0">
        <li className="flex items-start gap-3">
          <Icon name="circle-check" size={20} />
          <span className="flex flex-col">
            <span className="font-ui text-[15px] leading-[22px] text-text">{t('export.included.filed')}</span>
            <span className="font-ui text-[13px] leading-[18px] text-text-muted" data-testid="export-count">
              {t('export.included.filedHint', { count: preview.documentCount, n: n(preview.documentCount) })}
            </span>
            {byCategory ? <span className="font-ui text-[13px] leading-[18px] text-text-muted">{byCategory}</span> : null}
          </span>
        </li>
        <li className="flex items-start gap-3">
          <Icon name="circle-check" size={20} />
          <span className="flex flex-col">
            <span className="font-ui text-[15px] leading-[22px] text-text">{t('export.included.csv')}</span>
            <span className="font-ui text-[13px] leading-[18px] text-text-muted">{t('export.included.csvHint')}</span>
          </span>
        </li>
        {preview.inReview > 0 ? (
          <li className="flex items-start gap-3" data-testid="export-in-review">
            <Icon name="alert" size={20} />
            <span className="flex flex-col">
              <span className="font-ui text-[15px] leading-[22px] text-text">{t('export.included.review')}</span>
              <span className="font-ui text-[13px] leading-[18px] text-text-muted">{t('export.included.reviewHint', { count: preview.inReview, n: n(preview.inReview) })}</span>
            </span>
          </li>
        ) : null}
      </ul>
    </fieldset>
  );
}

function ExportBody({ onClose }: { onClose(): void }) {
  const { t } = useTranslation();
  const lang = useLang();
  const qc = useQueryClient();
  const { scope } = useAppState();
  const entityList = useEntityList().data;
  const entities = (entityList?.items ?? []).filter((e) => e.visibility === 'practice' && e.id !== entityList?.visitorsEntityId);
  const [entityChoice, setEntityChoice] = useState<string | undefined>(scope === 'all' ? undefined : scope);
  const entityId = entities.find((e) => e.id === entityChoice)?.id ?? entities[0]?.id;
  const [yearChoice, setYearChoice] = useState<number | undefined>();
  const guess = new Date().getFullYear();

  const base = useExportPreview(entityId, guess);
  const years = base.data?.fiscalYears ?? [];
  const defaultYear = years.length === 0 || years.includes(guess) ? guess : years[0]!;
  const fiscalYear = yearChoice !== undefined && years.includes(yearChoice) ? yearChoice : defaultYear;
  const preview = useExportPreview(entityId, base.data ? fiscalYear : undefined);

  const [packId, setPackId] = useState<string | undefined>();
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<unknown>(null);
  const polled = useExportPack(packId);
  const pack: ExportPack | undefined = polled.data;

  async function build() {
    if (!entityId || starting) return;
    setStarting(true);
    setStartError(null);
    try {
      const started = await startExport(entityId, fiscalYear);
      qc.setQueryData(['export', started.id], started);
      setPackId(started.id);
    } catch (err) {
      setStartError(err);
    } finally {
      setStarting(false);
    }
  }

  const n = (v: number) => format.number(v, lang);
  const entity = entities.find((e) => e.id === entityId);
  const building = packId !== undefined && (!pack || pack.status === 'building');
  const ready = pack?.status === 'ready';
  const failed = pack?.status === 'failed' || (packId !== undefined && polled.isError);
  const count = preview.data?.documentCount ?? 0;

  const footer = ready ? (
    <Button variant="primary" onClick={onClose}>
      {t('common.close')}
    </Button>
  ) : (
    <>
      <Button variant="secondary" onClick={onClose}>
        {t('common.cancel')}
      </Button>
      {failed ? (
        <Button variant="primary" onClick={() => setPackId(undefined)}>
          {t('common.retry')}
        </Button>
      ) : (
        <Button variant="primary" icon="download" loading={starting || building} disabled={!entityId || !preview.data || count === 0 || building} onClick={() => void build()}>
          {preview.data ? t('export.build', { count, n: n(count) }) : t('export.buildPlain')}
        </Button>
      )}
    </>
  );

  return (
    <Dialog open onClose={onClose} title={t('export.title')} lang={lang} size="wide" footer={footer}>
      <div className="flex flex-col gap-5" data-testid="export-dialog">
        <p className="m-0 flex items-start gap-3 text-text [font:var(--type-voice-italic)]">
          <MonaAvatar size={28} />
          <span>{t('export.intro')}</span>
        </p>
        {ready && pack ? (
          <div className="flex flex-col gap-4" data-testid="export-ready">
            <Banner tone="success" title={t('export.ready.title')}>
              {t('export.ready.body', { count: pack.documentCount ?? 0, n: n(pack.documentCount ?? 0), entity: pack.entityName, year: format.number(pack.fiscalYear, lang, { useGrouping: false }) })}
            </Banner>
            <div className="flex flex-wrap gap-3">
              {pack.zipUrl ? (
                <a className="mona-btn mona-btn--primary" href={pack.zipUrl} download>
                  <Icon name="download" size={18} />
                  {t('export.ready.zip')}
                </a>
              ) : null}
              {pack.csvUrl ? (
                <a className="mona-btn mona-btn--secondary" href={pack.csvUrl} download>
                  <Icon name="download" size={18} />
                  {t('export.ready.csv')}
                </a>
              ) : null}
            </div>
            <p className="m-0 font-ui text-[13px] leading-[18px] text-text-muted">{t('export.ready.hint')}</p>
          </div>
        ) : (
          <>
            {entities.length === 0 && entityList ? <Banner tone="info">{t('export.noEntities')}</Banner> : null}
            <div className="grid gap-4 sm:grid-cols-2">
              <Select
                label={t('export.entity')}
                value={entityId ?? ''}
                disabled={building}
                onChange={(e) => {
                  setEntityChoice(e.target.value);
                  setYearChoice(undefined);
                }}
                options={entities.map((e) => ({ value: e.id, label: e.displayName }))}
              />
              <Select
                label={t('export.fiscalYear')}
                value={String(fiscalYear)}
                disabled={building || years.length === 0}
                onChange={(e) => setYearChoice(Number(e.target.value))}
                options={(years.length > 0 ? years : [guess]).map((y) => ({ value: String(y), label: format.number(y, lang, { useGrouping: false }) }))}
                hint={entity ? t('export.fiscalYearHint', { end: fiscalYearEndLabel(entity.fiscalYearEnd, lang) }) : undefined}
              />
            </div>
            {base.isPending || (base.data && preview.isPending) ? <Skeleton lines={4} /> : null}
            {base.isError || preview.isError ? <Banner tone="danger">{t(errorKey(base.error ?? preview.error), errorValues(base.error ?? preview.error))}</Banner> : null}
            {preview.data && preview.data.documentCount === 0 && preview.data.inReview === 0 ? <Banner tone="info">{t('export.nothing')}</Banner> : null}
            {preview.data ? <Included preview={preview.data} /> : null}
            {startError ? <Banner tone="danger">{t(errorKey(startError), errorValues(startError))}</Banner> : null}
            {building ? (
              <div className="flex items-center gap-3" role="status" data-testid="export-building">
                <Spinner size={20} />
                <span className="font-ui text-[15px] leading-[22px] text-text">{t('export.building')}</span>
              </div>
            ) : null}
            {failed ? (
              <Banner tone="danger" title={t('export.failed.title')}>
                {t('export.failed.body')}
              </Banner>
            ) : null}
            <div className="flex flex-col gap-2 rounded-md bg-surface-sunken px-4 py-3 font-ui text-[13px] leading-[18px] text-text">
              <span className="flex items-start gap-2">
                <Icon name="download" size={16} />
                <span>{t('export.destination')}</span>
              </span>
              <span className="flex items-start gap-2">
                <Icon name="lock" size={16} />
                <span>{t('export.privacy')}</span>
              </span>
            </div>
          </>
        )}
      </div>
    </Dialog>
  );
}

function fiscalYearEndLabel(mmdd: string, lang: ReturnType<typeof useLang>): string {
  const [m, d] = mmdd.split('-').map(Number);
  return format.date(new Date(2001, (m ?? 12) - 1, d ?? 31), lang, 'dayMonth');
}
