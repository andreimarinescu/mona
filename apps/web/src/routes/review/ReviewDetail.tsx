import { Banner, Button, Icon, Input, Select, Skeleton, format } from '@mona/ui';
import { DocStatusPill } from '../../components/DocStatusPill';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { InternalLink } from '../../components/InternalLink';
import type { CorrectionRequest, DocumentDetail } from '../../data/dto';
import { errorKey, errorValues } from '../../data/errors';
import { useDocument } from '../../data/review';
import { useCategories, useEntityDetail, useEntityList } from '../../data/registry';
import { JournalTimeline } from '../../journal/JournalTimeline';
import { useLang } from '../../shell/useLang';
import { CorrectionScopePrompt } from './CorrectionScopePrompt';
import { SuggestionPanel } from './SuggestionPanel';

const INTERACTIVE = 'button, a, input, textarea, select, summary, [role="radio"], [role="menuitem"], [contenteditable="true"]';

export interface ReviewDetailProps {
  documentId: string;
  position: { index: number; total: number } | null;
  prevId?: string;
  nextId?: string;
  onMove(id: string): void;
  onBack?: () => void;
  scopePending: boolean;
  onConfirm(doc: DocumentDetail): Promise<boolean>;
  onCorrect(doc: DocumentDetail, body: CorrectionRequest): Promise<boolean>;
  onScopeDone(): void;
  onSkip(): void;
}

export function ReviewDetail(props: ReviewDetailProps) {
  const { t } = useTranslation();
  const query = useDocument(props.documentId);
  if (query.isPending) return <Skeleton lines={8} />;
  if (query.isError || !query.data) {
    return (
      <Banner tone="danger" actions={<Button variant="secondary" size="sm" onClick={() => void query.refetch()}>{t('common.retry')}</Button>}>
        {t(errorKey(query.error), errorValues(query.error))}
      </Banner>
    );
  }
  return <DetailBody key={props.documentId} doc={query.data} {...props} />;
}

function DetailBody({ doc, ...props }: ReviewDetailProps & { doc: DocumentDetail }) {
  const { t } = useTranslation();
  const lang = useLang();
  const entityList = useEntityList().data;
  const categories = useCategories().data ?? [];
  const suggestion = doc.suggestion;
  const visitorsId = entityList?.visitorsEntityId ?? null;
  const visitor = !!visitorsId && (doc.entityId === visitorsId || suggestion?.entityId === visitorsId);
  const purgeHours = useEntityDetail(visitor ? visitorsId : null).data?.purgeAfterHours ?? null;
  const initial = {
    entityId: suggestion?.entityId ?? doc.entityId ?? '',
    categoryId: suggestion?.categoryId ?? doc.categoryId ?? '',
    subcategoryKey: suggestion?.subcategoryKey ?? doc.subcategoryKey ?? '',
  };
  const [entityId, setEntityId] = useState(initial.entityId);
  const [categoryId, setCategoryId] = useState(initial.categoryId);
  const [subcategoryKey, setSubcategoryKey] = useState(initial.subcategoryKey);
  const [busy, setBusy] = useState(false);

  const reviewable = doc.status === 'review' || doc.status === 'unreadable';
  const locked = props.scopePending || !reviewable;
  const dirty = entityId !== initial.entityId || categoryId !== initial.categoryId || subcategoryKey !== initial.subcategoryKey;
  const canConfirm = doc.status === 'review' && !!suggestion?.entityId && !!suggestion.fileName;
  const canCorrect = dirty && !!entityId && !!categoryId;
  const category = categories.find((c) => c.id === categoryId);
  const entity = entityList?.items.find((e) => e.id === (props.scopePending ? (doc.entityId ?? entityId) : entityId));
  const quoteLang = entityList?.items.find((e) => e.id === suggestion?.entityId)?.filingLanguage ?? null;

  async function primary() {
    if (busy || locked) return;
    setBusy(true);
    try {
      if (dirty) {
        if (!canCorrect) return;
        const body: CorrectionRequest = {};
        if (entityId !== initial.entityId) body.entityId = entityId;
        if (categoryId !== initial.categoryId) body.categoryId = categoryId;
        if (categoryId !== initial.categoryId || subcategoryKey !== initial.subcategoryKey) body.subcategoryKey = subcategoryKey || null;
        await props.onCorrect(doc, body);
      } else if (canConfirm) await props.onConfirm(doc);
    } finally {
      setBusy(false);
    }
  }

  const latest = useRef(primary);
  useEffect(() => {
    latest.current = primary;
  });
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key !== 'Enter' || e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey || e.shiftKey) return;
      if (e.target instanceof Element && e.target.closest(`${INTERACTIVE}, [role="dialog"]`)) return;
      e.preventDefault();
      void latest.current();
    }
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, []);

  const pages = doc.pageCount ?? 1;
  return (
    <article className="flex min-w-0 flex-col overflow-hidden rounded-xl border border-border bg-surface shadow-1" aria-labelledby="review-detail-title" data-testid="review-detail" data-document-id={doc.id}>
      <header className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-border px-5 py-4">
        {props.onBack ? (
          <Button variant="quiet" size="sm" icon="chevron-left" onClick={props.onBack}>
            {t('review.detail.back')}
          </Button>
        ) : null}
        <div className="flex min-w-[200px] flex-1 flex-col gap-0.5">
          <h2 id="review-detail-title" className="m-0 text-text [font:var(--type-heading)]">
            {doc.title}
          </h2>
          <span className="text-text-muted [font:var(--type-filename)]">
            {doc.fileName} · {t('review.detail.pages', { count: pages, n: format.number(pages, lang) })}
          </span>
        </div>
        <DocStatusPill doc={doc} />
        {props.position ? (
          <div className="flex items-center gap-1">
            <span className="font-ui text-[14px] leading-5 text-text-muted" data-testid="review-position">
              {t('review.detail.position', { index: format.number(props.position.index + 1, lang), total: format.number(props.position.total, lang) })}
            </span>
            <Button variant="quiet" iconOnly icon="chevron-left" aria-label={t('review.detail.prev')} aria-keyshortcuts="K" disabled={!props.prevId} onClick={() => props.prevId && props.onMove(props.prevId)} />
            <Button variant="quiet" iconOnly icon="chevron-right" aria-label={t('review.detail.next')} aria-keyshortcuts="J" disabled={!props.nextId} onClick={() => props.nextId && props.onMove(props.nextId)} />
          </div>
        ) : null}
      </header>
      <div className={`grid gap-0 ${props.scopePending ? '' : 'lg:grid-cols-[minmax(240px,1fr)_minmax(320px,1fr)]'}`}>
        <div className={`order-last items-start justify-center bg-surface-sunken p-5 lg:order-first ${props.scopePending ? 'hidden' : 'flex'}`}>
          {doc.thumbnailUrl ? (
            <img src={doc.thumbnailUrl} alt={t('review.thumbnail.alt', { title: doc.title })} className="max-h-[480px] w-full max-w-[360px] rounded-sm border border-border bg-paper object-contain shadow-2" />
          ) : (
            <div className="flex aspect-[3/4] w-full max-w-[280px] flex-col items-center justify-center gap-2 rounded-sm border border-border bg-paper p-4 text-center text-paper-muted">
              <Icon name="file" size={32} />
              <span className="font-ui text-[13px] leading-[18px]">{t('review.thumbnail.none')}</span>
            </div>
          )}
        </div>
        <div className="flex min-w-0 flex-col gap-5 p-5">
          {suggestion && !props.scopePending ? <SuggestionPanel suggestion={suggestion} showMeter={doc.status === 'review'} quoteLang={quoteLang} /> : null}
          {!reviewable && !props.scopePending ? (
            <Banner tone="success">
              {t('review.detail.filed')}{' '}
              <InternalLink href={`/documents/${doc.id}`} className="text-info underline">
                {t('review.detail.open')}
              </InternalLink>
            </Banner>
          ) : null}
          <div className="grid gap-3">
            {visitor ? (
              <Input
                label={t('review.picker.entity')}
                value={entityList?.items.find((e) => e.id === visitorsId)?.displayName ?? ''}
                readOnly
                hint={purgeHours ? t('review.picker.visitorsNote', { count: purgeHours }) : t('review.picker.visitorsNoteNoHours')}
                data-testid="visitors-entity"
              />
            ) : (
              <Select
                label={t('review.picker.entity')}
                value={entityId}
                disabled={locked}
                placeholder={t('review.picker.chooseEntity')}
                onChange={(e) => setEntityId(e.target.value)}
                options={(entityList?.items ?? []).filter((e) => e.id !== visitorsId).map((e) => ({ value: e.id, label: e.displayName }))}
              />
            )}
            <Select
              label={t('review.picker.category')}
              value={categoryId}
              disabled={locked}
              placeholder={t('review.picker.chooseCategory')}
              onChange={(e) => {
                setCategoryId(e.target.value);
                setSubcategoryKey('');
              }}
              options={categories.map((c) => ({ value: c.id, label: c.labels[lang] }))}
            />
            {category && category.subcategories.length > 0 ? (
              <Select
                label={t('review.picker.subcategory')}
                value={subcategoryKey}
                disabled={locked}
                onChange={(e) => setSubcategoryKey(e.target.value)}
                options={[{ value: '', label: t('review.picker.noSubcategory') }, ...category.subcategories.map((s) => ({ value: s.key, label: s.labels[lang] }))]}
              />
            ) : null}
          </div>
          {props.scopePending && entity ? <p className="m-0 font-ui text-[13px] leading-[18px] text-text-muted">{t('review.picker.changed', { entity: entity.displayName })}</p> : null}
          {reviewable && !props.scopePending ? (
            <>
              {suggestion?.fileName && !dirty ? (
                <div className="flex flex-col gap-1">
                  <span className="font-ui text-[14px] leading-5 font-semibold text-text">{t('review.detail.newFileName')}</span>
                  <span className="rounded-sm bg-surface-sunken px-3 py-2 break-all text-text [font:var(--type-filename)]" data-testid="new-file-name">
                    {suggestion.fileName}
                  </span>
                  <span className="font-ui text-[13px] leading-[18px] text-text-muted">{t('review.detail.willBeFiled', { path: suggestion.path.join(' / ') })}</span>
                </div>
              ) : dirty ? (
                <p className="m-0 font-ui text-[13px] leading-[18px] text-text-muted">{t('review.detail.updatesOnSave')}</p>
              ) : null}
              <div className="flex flex-wrap items-center gap-3">
                {dirty ? (
                  <Button variant="primary" icon="check" loading={busy} disabled={!canCorrect} onClick={() => void primary()}>
                    {t('review.detail.correct')}
                  </Button>
                ) : (
                  <Button variant="primary" icon="check" loading={busy} disabled={!canConfirm} onClick={() => void primary()}>
                    {t('review.detail.confirm')}
                  </Button>
                )}
                <Button variant="secondary" onClick={props.onSkip}>
                  {t('review.detail.skip')}
                </Button>
                <Button variant="quiet" icon="file-x" disabled>
                  {t('review.detail.markUnreadable')}
                </Button>
              </div>
              <span className="font-ui text-[13px] leading-[18px] text-text-muted">{t('review.detail.keys')}</span>
            </>
          ) : null}
        </div>
      </div>
      {props.scopePending ? (
        <div className="px-5 pb-5">
          <CorrectionScopePrompt documentId={doc.id} onDone={props.onScopeDone} />
        </div>
      ) : null}
      {doc.journal.length > 0 ? (
        <details className="border-t border-border px-5 py-4">
          <summary className="cursor-pointer font-ui text-[14px] leading-5 font-semibold text-text">{t('review.detail.history')}</summary>
          <div className="pt-3">
            <JournalTimeline entries={doc.journal} documents={{ [doc.id]: { title: doc.title, fileName: doc.fileName, deleted: false } }} />
          </div>
        </details>
      ) : null}
    </article>
  );
}
