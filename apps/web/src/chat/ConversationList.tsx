import { Button, Icon, SearchField, Skeleton, format } from '@mona/ui';
import { Link } from '@tanstack/react-router';
import { useEffect, useId, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useConversations } from '../data/conversations';
import { useLang } from '../shell/useLang';

const SEARCH_DEBOUNCE_MS = 250;

export function ConversationList({ activeId, onPick }: { activeId: string | undefined; onPick?: () => void }) {
  const { t } = useTranslation();
  const lang = useLang();
  const heading = useId();
  const [text, setText] = useState('');
  const [q, setQ] = useState('');
  useEffect(() => {
    const timer = setTimeout(() => setQ(text), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [text]);
  const list = useConversations(q);
  return (
    <section aria-labelledby={heading} className="flex min-h-0 flex-col gap-4" data-testid="conversation-list">
      <div className="flex items-center gap-2">
        <h2 id={heading} className="m-0 flex-1 font-ui text-[18px] leading-[26px] font-semibold text-text">
          {t('chat.list.title')}
        </h2>
        <Link to="/chat" activeOptions={{ exact: true }} onClick={onPick} className="mona-btn mona-btn--quiet mona-btn--icon no-underline" aria-label={t('chat.list.new')} title={t('chat.list.new')}>
          <Icon name="pencil" size={18} />
        </Link>
      </div>
      <SearchField value={text} onChange={setText} label={t('chat.list.search')} placeholder={t('chat.list.search')} size="sm" lang={lang} />
      <div className="min-h-0 flex-1 overflow-y-auto">
        {list.isPending ? <Skeleton lines={4} /> : null}
        {!list.isPending && list.items.length === 0 ? (
          <p className="m-0 px-3 font-ui text-[14px] leading-5 text-text-muted">{q.trim() ? t('chat.list.noMatch', { q: q.trim() }) : t('chat.list.empty')}</p>
        ) : null}
        <ul className="m-0 flex list-none flex-col gap-1 p-0">
          {list.items.map((c) => (
            <li key={c.id}>
              <Link
                to="/chat/$conversationId"
                params={{ conversationId: c.id }}
                onClick={onPick}
                aria-current={c.id === activeId ? 'page' : undefined}
                data-conversation={c.id}
                className="flex flex-col gap-0.5 rounded-md px-3 py-2 no-underline hover:bg-surface-sunken aria-[current=page]:bg-accent-soft"
              >
                <span className="line-clamp-2 font-ui text-[15px] leading-5 font-semibold text-text">{c.title}</span>
                <span className="font-ui text-[13px] leading-[18px] text-text-muted">{format.relative(c.lastMessageAt, lang)}</span>
              </Link>
            </li>
          ))}
        </ul>
        {list.hasNextPage ? (
          <Button variant="ghost" size="sm" loading={list.isFetchingNextPage} onClick={() => void list.fetchNextPage()}>
            {t('chat.list.more')}
          </Button>
        ) : null}
      </div>
    </section>
  );
}
