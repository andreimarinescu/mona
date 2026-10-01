import { useChat } from '@ai-sdk/react';
import { MonaAvatar, type Lang } from '@mona/ui';
import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { useRefreshCards } from '../data/cards';
import { useHealth } from '../data/hooks';
import { planUpload, uploadIntake } from '../data/intake';
import { toastFailure } from '../data/journal';
import type { ChatOutbox } from '../state/context';
import { toasts } from '../toast/store';
import { ChatComposer, type PendingAttachment } from './ChatComposer';
import { ChatError } from './ChatError';
import { ChatCardContext } from './context';
import { LanguageDivider } from './LanguageDivider';
import { MonaMessage, UserMessage } from './Messages';
import { ReasoningClock, ReasoningClockContext } from './reasoningClock';
import { monaTransport } from './transport';
import type { MonaUIMessage, PageContext } from './types';

export interface ChatThreadProps {
  conversationId?: string;
  initial: MonaUIMessage[];
  pageContext: () => PageContext;
  onConversationId?: (id: string) => void;
  onTurnFinished?: () => void;
  variant: 'page' | 'panel';
  autoFocus?: boolean;
  outbox?: ChatOutbox | null;
  onOutboxSent?: (id: number) => void;
  empty?: ReactNode;
}

const STICK_PX = 96;
const visible = (m: MonaUIMessage) => m.parts.some((p) => p.type !== 'step-start');
const hasFiles = (e: DragEvent) => [...e.dataTransfer.types].includes('Files');

export function ChatThread({ conversationId, initial, pageContext, onConversationId, onTurnFinished, variant, autoFocus, outbox, onOutboxSent, empty }: ChatThreadProps) {
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const refreshCards = useRefreshCards();
  const offline = useHealth().data?.status === 'offline';
  const [pinned, setPinned] = useState<Lang | undefined>();
  const [mona] = useState(() => monaTransport({ conversationId, pageContext, locale: () => i18n.language }));
  const keepLanguage = (lang: Lang) => {
    mona.setReplyLanguage(lang);
    setPinned(lang);
  };
  const [clock] = useState(() => new ReasoningClock());
  const [draft, setDraft] = useState('');
  const [attachments, setAttachments] = useState<PendingAttachment[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const input = useRef<HTMLTextAreaElement>(null);
  const viewport = useRef<HTMLDivElement>(null);
  const stick = useRef(true);

  const chat = useChat<MonaUIMessage>({
    id: conversationId,
    messages: initial,
    transport: mona.transport,
    onFinish: () => {
      void refreshCards();
      void qc.invalidateQueries({ queryKey: ['conversations'] });
      onTurnFinished?.();
    },
  });
  const { messages, status, sendMessage, stop, regenerate, error } = chat;

  const latestId = messages.findLast((m) => m.role === 'assistant')?.metadata?.conversationId;
  useEffect(() => {
    if (latestId && latestId !== mona.conversationId()) {
      mona.setConversationId(latestId);
      onConversationId?.(latestId);
    }
  }, [latestId, mona, onConversationId]);

  const sent = useRef(0);
  useEffect(() => {
    if (!outbox || sent.current === outbox.id) return;
    const timer = setTimeout(() => {
      sent.current = outbox.id;
      mona.overrideNext(outbox.pageContext);
      stick.current = true;
      void sendMessage({ text: outbox.message });
      onOutboxSent?.(outbox.id);
    }, 0);
    return () => clearTimeout(timer);
  }, [outbox, sendMessage, onOutboxSent, mona]);

  useEffect(() => {
    const el = viewport.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [messages, status, error]);

  const prefill = useCallback(
    (text: string, summary?: string) => {
      setDraft(text);
      if (summary) mona.overrideNext({ route: pageContext().route, summary });
      requestAnimationFrame(() => {
        const el = input.current;
        if (!el) return;
        el.focus();
        el.setSelectionRange(text.length, text.length);
      });
    },
    [mona, pageContext],
  );
  const cardContext = useMemo(() => ({ conversationId: () => mona.conversationId(), prefill }), [mona, prefill]);

  async function addFiles(files: File[]) {
    const { send, overLimit } = planUpload(files);
    if (overLimit.length > 0) toasts.push({ key: 'over-limit', message: 'intake.overLimit', count: overLimit.length, tone: 'warning' });
    if (send.length === 0) return;
    const batch = `${Date.now()}`;
    const pending = send.map((f, i): PendingAttachment => ({ key: `${batch}-${i}`, name: f.name, type: f.type, sizeBytes: f.size, outcome: null, documentId: null, uploading: true }));
    setAttachments((a) => [...a, ...pending]);
    try {
      const result = await uploadIntake(send, { visitor: false });
      setAttachments((a) => a.map((x) => {
        const i = pending.findIndex((p) => p.key === x.key);
        const item = i >= 0 ? result.items[i] : undefined;
        return i < 0 ? x : { ...x, uploading: false, outcome: item?.outcome ?? null, documentId: item?.documentId ?? null };
      }));
      void Promise.all(['batch', 'batches', 'shell-counts'].map((key) => qc.invalidateQueries({ queryKey: [key] })));
    } catch (err) {
      setAttachments((a) => a.map((x) => (pending.some((p) => p.key === x.key) ? { ...x, uploading: false } : x)));
      toastFailure(err);
    }
  }

  function send() {
    const text = draft.trim();
    const done = attachments.filter((a) => !a.uploading).map(({ name, type, sizeBytes, outcome, documentId }) => ({ name, type, sizeBytes, outcome, documentId }));
    stick.current = true;
    void sendMessage({ text, metadata: done.length > 0 ? { attachments: done } : undefined });
    setDraft('');
    setAttachments([]);
  }

  const sending = status === 'submitted' || status === 'streaming';
  const lastAssistant = messages.findLastIndex((m) => m.role === 'assistant');
  const waiting = sending && (messages.at(-1)?.role === 'user' || (lastAssistant === messages.length - 1 && !visible(messages[lastAssistant]!)));
  let previousReply: Lang | undefined;
  const rows: ReactNode[] = [];
  messages.forEach((m, i) => {
    if (m.role === 'user') {
      rows.push(<UserMessage key={m.id} message={m} />);
      return;
    }
    if (m.role !== 'assistant' || !visible(m)) return;
    const reply = m.metadata?.replyLanguage;
    if (reply && previousReply && reply !== previousReply) {
      rows.push(<LanguageDivider key={`${m.id}-divider`} to={reply} from={previousReply} pinned={pinned} onKeep={keepLanguage} />);
    }
    if (reply) previousReply = reply;
    rows.push(<MonaMessage key={m.id} message={m} streaming={sending && i === messages.length - 1} newest={i === lastAssistant} />);
  });

  const page = variant === 'page';
  return (
    <ReasoningClockContext.Provider value={clock}>
      <ChatCardContext.Provider value={cardContext}>
        <div
          className="flex h-full min-h-0 flex-col gap-3"
          data-chat-status={status}
          onDragEnter={(e) => {
            if (!hasFiles(e) || offline) return;
            e.preventDefault();
            setDragOver(true);
          }}
          onDragOver={(e) => {
            if (!hasFiles(e) || offline) return;
            e.preventDefault();
          }}
          onDragLeave={(e) => {
            if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragOver(false);
          }}
          onDrop={(e) => {
            if (!hasFiles(e) || offline) return;
            e.preventDefault();
            setDragOver(false);
            void addFiles([...e.dataTransfer.files]);
          }}
        >
          <div
            ref={viewport}
            onScroll={(e) => {
              const el = e.currentTarget;
              stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < STICK_PX;
            }}
            className="min-h-0 flex-1 overflow-y-auto"
            data-testid="chat-thread"
          >
            <div className={`box-border flex min-h-full flex-col justify-end gap-5 ${page ? 'mx-auto max-w-[880px] px-4 py-6 lg:px-8' : 'py-2'}`}>
              {rows.length === 0 && !waiting ? empty : null}
              {rows}
              {waiting ? (
                <div className="flex items-center gap-3" data-testid="chat-waiting" role="status">
                  <MonaAvatar size={32} state="thinking" />
                  <span className="rounded-md border border-dashed border-info px-4 py-2 font-ui text-[14px] leading-5 font-semibold text-info">{t('chat.thinking.live')}</span>
                </div>
              ) : null}
              {error && status === 'error' ? <ChatError error={error} onRetry={() => void regenerate()} /> : null}
            </div>
          </div>
          <div className={page ? 'mx-auto box-border w-full max-w-[880px] px-4 pb-4 lg:px-8' : ''}>
            <ChatComposer
              value={draft}
              onChange={setDraft}
              onSend={send}
              onStop={() => void stop()}
              onFiles={(files) => void addFiles(files)}
              attachments={attachments}
              sending={sending}
              offline={offline}
              dragOver={dragOver}
              hint={page ? t('chat.composer.hintPage') : t('chat.composer.hintPanel')}
              size={page ? 'lg' : 'md'}
              inputRef={input}
              autoFocus={autoFocus}
            />
          </div>
        </div>
      </ChatCardContext.Provider>
    </ReasoningClockContext.Provider>
  );
}
