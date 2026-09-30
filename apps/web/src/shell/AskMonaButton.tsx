import { MonaAvatar } from '@mona/ui';
import { useTranslation } from 'react-i18next';
import { useAppState } from '../state/context';

export function AskMonaButton() {
  const { t } = useTranslation();
  const { openChat, registerAskButton } = useAppState();
  return (
    <button
      type="button"
      ref={registerAskButton}
      className="mona-btn mona-btn--secondary w-full"
      style={{ justifyContent: 'space-between' }}
      aria-label={t('shell.ask.label')}
      aria-keyshortcuts="/"
      onClick={(e) => openChat({ opener: e.currentTarget })}
    >
      <span className="inline-flex items-center gap-2">
        <MonaAvatar size={28} />
        {t('shell.ask.label')}
      </span>
      <kbd className="mona-kbd" aria-hidden>
        /
      </kbd>
    </button>
  );
}
