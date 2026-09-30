import emptyInbox from '@design/mona-handoff/assets/illustrations/empty-inbox.svg';
import { EmptyState } from '@mona/ui';
import { useParams } from '@tanstack/react-router';
import { useTranslation } from 'react-i18next';
import { useEntities } from '../data/hooks';
import { useAppState } from '../state/context';

export function Placeholder({ title }: { title: string }) {
  const { t } = useTranslation();
  const { scope } = useAppState();
  const entities = useEntities().data ?? [];
  const params: Record<string, string | undefined> = useParams({ strict: false });
  const reference = params.conversationId ?? params.documentId ?? params.ruleId ?? params.categoryId;
  const scopeName = scope === 'all' ? t('shell.scope.all') : (entities.find((e) => e.id === scope)?.displayName ?? scope);
  return (
    <div className="mx-auto flex max-w-[880px] flex-col gap-6 p-6 lg:p-10">
      <h1 className="m-0 text-text [font:var(--type-title)]">{t(title)}</h1>
      <p className="m-0 text-text-muted" data-testid="scope-line">
        {t('placeholder.scope', { scope: scopeName })}
      </p>
      <EmptyState art={emptyInbox} title={t('placeholder.title')}>
        {t('placeholder.body')}
      </EmptyState>
      {reference ? (
        <p className="m-0 text-text-muted [font:var(--type-filename)]" data-testid="reference">
          {t('placeholder.reference', { id: reference })}
        </p>
      ) : null}
    </div>
  );
}
