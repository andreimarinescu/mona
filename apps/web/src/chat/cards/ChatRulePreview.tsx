import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { RulePreviewCard } from '../../components/RulePreviewCard';
import { rulePreviewKey, useRulePreview } from '../../data/cards';
import type { RulePreview } from '../../data/dto';
import { errorKey, errorValues } from '../../data/errors';
import { invalidateAfterWrite, useUndoRunner } from '../../data/journal';
import { applyRule } from '../../data/review';
import { toasts } from '../../toast/store';
import { useChatCard } from '../context';

/** A `RulePreviewCard` for one rule, kept current through `GET /api/rules/{id}/preview`; Apply writes the C2 §14 note. */
export function ChatRulePreview({ ruleId, snapshot, embedded }: { ruleId: string; snapshot?: RulePreview; embedded?: boolean }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const card = useChatCard();
  const undo = useUndoRunner();
  const preview = useRulePreview(ruleId, snapshot).data;
  const apply = useMutation({
    mutationFn: () => applyRule(ruleId, card.conversationId()),
    onSuccess: (result) => {
      qc.setQueryData(rulePreviewKey(ruleId), result.preview);
      if (result.groupId) {
        const groupId = result.groupId;
        toasts.push({ key: `rule-applied-${groupId}`, message: 'review.toast.ruleApplied', count: result.moved, undo: () => void undo({ groupId }, 'undo', card.conversationId()) });
      }
      void invalidateAfterWrite(qc);
    },
    onError: (err) => toasts.push({ key: 'apply-failed', message: errorKey(err), values: errorValues(err), tone: 'danger' }),
  });
  if (!preview) return null;
  return (
    <div data-card="rulePreview" data-id={ruleId} data-applied={preview.applied} data-state={preview.rule.state}>
      <RulePreviewCard embedded={embedded} preview={preview} applying={apply.isPending} onApply={() => apply.mutate()} hint={preview.applied ? undefined : t('rules.preview.journalHint')} />
    </div>
  );
}
