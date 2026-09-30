import { Banner, Button, Card, RadioGroup, Skeleton } from '@mona/ui';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { RulePreviewCard } from '../../components/RulePreviewCard';
import type { RulePreview } from '../../data/dto';
import { errorKey, errorValues } from '../../data/errors';
import { ApiError } from '../../data/http';
import { invalidateAfterWrite, useUndoRunner } from '../../data/journal';
import { applyRule, likeThis } from '../../data/review';
import { useLang } from '../../shell/useLang';
import { toasts } from '../../toast/store';

export interface CorrectionScopePromptProps {
  documentId: string;
  onDone(): void;
}

export function CorrectionScopePrompt({ documentId, onDone }: CorrectionScopePromptProps) {
  const { t } = useTranslation();
  const lang = useLang();
  const qc = useQueryClient();
  const undo = useUndoRunner();
  const [scope, setScope] = useState<'one' | 'all' | undefined>();
  const [preview, setPreview] = useState<RulePreview | null>(null);

  const propose = useMutation({
    mutationFn: () => likeThis(documentId),
    onSuccess: (r) => setPreview(r.preview),
  });
  const apply = useMutation({
    mutationFn: (ruleId: string) => applyRule(ruleId),
    onSuccess: (result) => {
      setPreview(result.preview);
      if (result.groupId) {
        const groupId = result.groupId;
        toasts.push({ key: `rule-applied-${groupId}`, message: 'review.toast.ruleApplied', count: result.moved, undo: () => void undo({ groupId }) });
      }
      void invalidateAfterWrite(qc);
      onDone();
    },
    onError: (err) => toasts.push({ key: 'apply-failed', message: errorKey(err), values: errorValues(err), tone: 'danger' }),
  });

  function choose(value: string) {
    const next = value as 'one' | 'all';
    setScope(next);
    if (next === 'all' && !preview && !propose.isPending) propose.mutate();
  }

  const noCounterparty = propose.error instanceof ApiError && propose.error.code === 'invalid_value';

  return (
    <div className="mt-4" data-testid="scope-prompt">
      <Card from="mona" lang={lang} voice={t('review.scopePrompt.voice')} variant="flat">
        <div className="flex flex-col gap-4">
          <RadioGroup
            legend={t('review.scopePrompt.legend')}
            variant="cards"
            orientation="horizontal"
            value={scope}
            onChange={choose}
            options={[
              { value: 'one', label: t('review.scopePrompt.justThisOne'), description: t('review.scopePrompt.justThisOneHint') },
              {
                value: 'all',
                label: t('review.scopePrompt.everyDocument'),
                description: t('review.scopePrompt.everyDocumentHint'),
                meta: t('review.scopePrompt.pastFuture'),
              },
            ]}
          />
          {scope === 'one' ? (
            <div>
              <Button variant="primary" onClick={onDone}>{t('review.scopePrompt.done')}</Button>
            </div>
          ) : null}
          {scope === 'all' && propose.isPending ? <Skeleton lines={3} /> : null}
          {scope === 'all' && propose.isError ? (
            <Banner
              tone="warning"
              actions={
                noCounterparty ? undefined : (
                  <Button variant="secondary" size="sm" onClick={() => propose.mutate()}>
                    {t('common.retry')}
                  </Button>
                )
              }
            >
              {noCounterparty ? t('review.scopePrompt.noCounterparty') : t(errorKey(propose.error), errorValues(propose.error))}
            </Banner>
          ) : null}
          {scope === 'all' && preview ? <RulePreviewCard embedded preview={preview} applying={apply.isPending} onApply={() => apply.mutate(preview.rule.id)} /> : null}
        </div>
      </Card>
    </div>
  );
}
