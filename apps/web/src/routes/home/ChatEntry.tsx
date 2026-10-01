import { Button, MonaAvatar } from '@mona/ui';
import { useNavigate } from '@tanstack/react-router';
import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { usePageContext } from '../../shell/usePageContext';
import { useAppState } from '../../state/context';

/** The pill composer pinned to the bottom of Home; `/` focuses it. */
export function ChatEntry({ disabled = false }: { disabled?: boolean }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { openChat, registerChatEntry } = useAppState();
  const context = usePageContext();
  const [text, setText] = useState('');

  function submit(e: FormEvent) {
    e.preventDefault();
    const message = text.trim();
    if (!message || disabled) return;
    setText('');
    openChat({ send: { message, pageContext: context } });
  }

  return (
    <form
      onSubmit={submit}
      aria-label={t('home.chat.label')}
      className="sticky bottom-[72px] z-10 flex items-center gap-3 rounded-full border border-border-strong bg-surface-raised py-2 pr-2 pl-3 shadow-2 focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-focus lg:bottom-4"
      data-testid="chat-entry"
    >
      <MonaAvatar size={40} state={disabled ? 'offline' : 'idle'} />
      <input
        ref={registerChatEntry}
        type="text"
        value={text}
        disabled={disabled}
        onChange={(e) => setText(e.target.value)}
        aria-label={t('home.chat.label')}
        aria-keyshortcuts="/"
        placeholder={disabled ? t('states.offline.title') : t('home.chat.placeholder')}
        className="min-h-11 min-w-0 flex-1 border-0 bg-transparent font-ui text-[17px] leading-[26px] text-text outline-none placeholder:text-text-muted"
      />
      <Button variant="quiet" iconOnly icon="paperclip" aria-label={t('home.chat.attach')} type="button" onClick={() => void navigate({ to: '/intake' })} />
      <Button variant="primary" iconOnly icon="send" aria-label={t('home.chat.send')} type="submit" disabled={disabled || text.trim() === ''} />
    </form>
  );
}
