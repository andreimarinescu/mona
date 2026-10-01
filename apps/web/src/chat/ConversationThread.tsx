import { Button, Spinner } from '@mona/ui';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useTranscript } from '../data/conversations';
import { ChatThread, type ChatThreadProps } from './ChatThread';

export type ConversationThreadProps = Omit<ChatThreadProps, 'initial'>;

/** Loads the transcript (C3 §7.2) first; the id is read once, so a new conversation's id doesn't remount the thread. */
export function ConversationThread(props: ConversationThreadProps) {
  const { t } = useTranslation();
  const [conversationId] = useState(props.conversationId);
  const transcript = useTranscript(conversationId);
  if (conversationId && transcript.isPending) {
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner label={t('chat.loading')} />
      </div>
    );
  }
  if (conversationId && transcript.isError) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3" role="alert">
        <p className="m-0 font-ui text-[15px] leading-[22px] text-text-muted">{t('chat.transcriptError')}</p>
        <Button variant="secondary" size="sm" onClick={() => void transcript.refetch()}>
          {t('common.retry')}
        </Button>
      </div>
    );
  }
  return <ChatThread {...props} conversationId={conversationId} initial={transcript.data ?? []} />;
}
