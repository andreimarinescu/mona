import emptyAllFiled from '@design/mona-handoff/assets/illustrations/empty-all-filed.svg';
import { Banner, Button, EmptyState, Skeleton, format } from '@mona/ui';
import { useNavigate, useParams } from '@tanstack/react-router';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { CorrectionRequest, DocumentDetail, DocumentSummary, FileOpResult, Reason } from '../../data/dto';
import { errorKey, errorValues } from '../../data/errors';
import { toastFailure, useUndoRunner } from '../../data/journal';
import { useEntityList } from '../../data/registry';
import { confirmDocument, correctDocument, useRefreshAfterWrite, useReviewList } from '../../data/review';
import { useLang } from '../../shell/useLang';
import { useAppState } from '../../state/context';
import { toasts } from '../../toast/store';
import { ReviewDetail } from './ReviewDetail';
import { ReviewList } from './ReviewList';
import { mergeQueue, neighbourAfter, omit, reasonCounts } from './queue';
import { useIsDesktop } from './useIsDesktop';

const TEXT_TARGET = 'input:not([type="checkbox"]):not([type="radio"]), textarea, select, [contenteditable="true"], [role="dialog"]';

export function ReviewPage() {
  const { t } = useTranslation();
  const lang = useLang();
  const navigate = useNavigate();
  const { documentId } = useParams({ strict: false }) as { documentId?: string };
  const { scope } = useAppState();
  const entityId = scope === 'all' ? undefined : scope;
  const desktop = useIsDesktop();
  const undo = useUndoRunner();
  const refresh = useRefreshAfterWrite();
  const entityList = useEntityList().data;
  const entities = entityList?.items ?? [];

  const [reason, setReason] = useState<Reason | 'all'>('all');
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [corrections, setCorrections] = useState<Record<string, DocumentSummary>>({});
  const [approving, setApproving] = useState(false);

  const all = useReviewList({ entityId });
  const filtered = useReviewList({ reason: reason === 'all' ? undefined : reason, entityId });
  const listQuery = reason === 'all' ? all : filtered;
  const items = mergeQueue(listQuery.data?.items ?? [], corrections);
  const counts = reasonCounts(all.data?.items ?? []);
  const total = all.data?.total ?? 0;

  const selectedId = documentId ?? (desktop ? items[0]?.id : undefined);
  const index = selectedId ? items.findIndex((d) => d.id === selectedId) : -1;
  const prevId = index > 0 ? items[index - 1]?.id : undefined;
  const nextId = index >= 0 ? items[index + 1]?.id : undefined;

  const go = (id: string | undefined) =>
    void (id ? navigate({ to: '/review/$documentId', params: { documentId: id } }) : navigate({ to: '/review' }));

  const latest = useRef({ prevId, nextId, go });
  useEffect(() => {
    latest.current = { prevId, nextId, go };
  });
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey) return;
      if (e.target instanceof Element && e.target.closest(TEXT_TARGET)) return;
      const key = e.key.toLowerCase();
      if (key !== 'j' && key !== 'k') return;
      const target = key === 'j' ? latest.current.nextId : latest.current.prevId;
      if (!target) return;
      e.preventDefault();
      latest.current.go(target);
    }
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, []);

  function pushFiled(result: FileOpResult) {
    const target = result.undo;
    toasts.push({ key: 'filed', message: 'toast.filed', undo: target ? () => void undo(target) : undefined });
  }

  async function confirm(doc: DocumentDetail): Promise<boolean> {
    try {
      const result = await confirmDocument(doc.id);
      pushFiled(result);
      const next = neighbourAfter(items, doc.id);
      void refresh();
      go(next);
      return true;
    } catch (err) {
      toastFailure(err);
      return false;
    }
  }

  async function correct(doc: DocumentDetail, body: CorrectionRequest): Promise<boolean> {
    try {
      const result = await correctDocument(doc.id, body);
      const now = result.document ?? doc;
      if (entityList?.visitorsEntityId && now.entityId === entityList.visitorsEntityId) go(neighbourAfter(items, doc.id));
      else setCorrections((c) => ({ ...c, [doc.id]: now }));
      const target = result.undo;
      toasts.push({
        key: `corrected-${doc.id}`,
        message: 'review.toast.moved',
        values: { title: doc.title, entity: entities.find((e) => e.id === now.entityId)?.displayName ?? '' },
        undo: target
          ? () => {
              setCorrections((c) => omit(c, doc.id));
              void undo(target);
            }
          : undefined,
      });
      void refresh();
      return true;
    } catch (err) {
      toastFailure(err);
      return false;
    }
  }

  function scopeDone(id: string) {
    const next = neighbourAfter(items, id);
    setCorrections((c) => omit(c, id));
    go(next);
  }

  async function approveChecked() {
    setApproving(true);
    const ids = [...checked];
    try {
      for (const id of ids) {
        try {
          pushFiled(await confirmDocument(id));
        } catch (err) {
          toastFailure(err);
        }
      }
    } finally {
      setChecked(new Set());
      setApproving(false);
      void refresh();
    }
    if (documentId && ids.includes(documentId)) go(items.find((d) => !ids.includes(d.id))?.id);
  }

  const visibleIds = new Set(items.map((d) => d.id));
  const liveChecked = new Set([...checked].filter((id) => visibleIds.has(id)));
  const oldest = items[0];

  return (
    <div className="mx-auto flex max-w-[1320px] flex-col gap-6 p-6 lg:p-10">
      <header className={`flex flex-col gap-2 ${documentId ? 'hidden lg:flex' : ''}`}>
        <h1 className="m-0 text-text [font:var(--type-title)]">{t('nav.review')}</h1>
        <p className="m-0 text-text-muted" data-testid="review-subtitle">
          {oldest
            ? t('review.subtitle', { count: items.length, n: format.number(items.length, lang), when: format.relative(oldest.arrivedAt, lang, new Date(all.dataUpdatedAt)) })
            : t('review.subtitleEmpty')}
        </p>
      </header>
      {listQuery.isError ? (
        <Banner tone="danger" actions={<Button variant="secondary" size="sm" onClick={() => void listQuery.refetch()}>{t('common.retry')}</Button>}>
          {t(errorKey(listQuery.error), errorValues(listQuery.error))}
        </Banner>
      ) : null}
      {listQuery.isPending ? <Skeleton lines={6} /> : null}
      {!listQuery.isPending && !listQuery.isError && items.length === 0 && !documentId ? (
        <EmptyState art={emptyAllFiled} title={t('review.empty.title')}>
          {t('review.empty.body')}
        </EmptyState>
      ) : null}
      {items.length > 0 || documentId ? (
        <div className="grid gap-6 lg:grid-cols-[minmax(340px,440px)_minmax(0,1fr)] lg:items-start">
          <div className={documentId ? 'hidden lg:block' : ''}>
            <ReviewList
              items={items}
              counts={counts}
              total={total}
              reason={reason}
              onReason={setReason}
              selectedId={selectedId}
              checked={liveChecked}
              corrected={new Set(Object.keys(corrections))}
              now={all.dataUpdatedAt}
              onCheck={(id, on) => setChecked((c) => new Set(on ? [...c, id] : [...c].filter((x) => x !== id)))}
              onCheckAll={(on) => setChecked(on ? new Set(items.filter((d) => !corrections[d.id]).map((d) => d.id)) : new Set())}
              onApprove={() => void approveChecked()}
              approving={approving}
            />
          </div>
          <div className={`min-w-0 ${documentId ? '' : 'hidden lg:block'}`}>
            {selectedId ? (
              <ReviewDetail
                documentId={selectedId}
                position={index >= 0 ? { index, total: items.length } : null}
                prevId={prevId}
                nextId={nextId}
                onMove={go}
                onBack={desktop ? undefined : () => go(undefined)}
                scopePending={!!corrections[selectedId]}
                onConfirm={confirm}
                onCorrect={correct}
                onScopeDone={() => scopeDone(selectedId)}
                onSkip={() => go(nextId ?? prevId)}
              />
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
