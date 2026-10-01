import emptyOffline from '@design/mona-handoff/assets/illustrations/empty-offline.svg';
import { Banner, Button, EmptyState, MonaAvatar, Skeleton } from '@mona/ui';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

/** A skeleton in the shape of the page, with Mona thinking and a sentence saying what she is doing. */
export function LoadingState({ label, lines = 4 }: { label: string; lines?: number }) {
  return (
    <div role="status" aria-busy="true" className="flex flex-col gap-4" data-testid="loading-state">
      <div className="flex items-center gap-3">
        <MonaAvatar size={32} state="thinking" />
        <span className="font-ui text-[15px] leading-[22px] text-text-muted">{label}</span>
      </div>
      <Skeleton lines={lines} />
    </div>
  );
}

/** Mona's brain (Hermes) is not answering: the app still reads and files, the chat waits. */
export function OfflineState({ onRetry, compact = false }: { onRetry?: () => void; compact?: boolean }) {
  const { t } = useTranslation();
  const retry = onRetry ? (
    <Button variant="secondary" size="sm" onClick={onRetry}>
      {t('common.retry')}
    </Button>
  ) : undefined;
  if (compact) {
    return (
      <Banner tone="info" icon="alert" title={t('states.offline.title')} actions={retry}>
        {t('states.offline.body')}
      </Banner>
    );
  }
  return (
    <EmptyState art={emptyOffline} title={t('states.offline.title')} action={retry}>
      {t('states.offline.body')}
    </EmptyState>
  );
}

export function LoadError({ onRetry, children }: { onRetry: () => void; children?: ReactNode }) {
  const { t } = useTranslation();
  return (
    <Banner
      tone="danger"
      actions={
        <Button variant="secondary" size="sm" onClick={onRetry}>
          {t('common.retry')}
        </Button>
      }
    >
      {children ?? t('states.loadFailed')}
    </Banner>
  );
}
