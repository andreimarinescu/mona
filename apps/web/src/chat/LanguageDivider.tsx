import { Icon, type Lang } from '@mona/ui';
import { useTranslation } from 'react-i18next';

export interface LanguageDividerProps {
  to: Lang;
  from: Lang;
  /** The reply language the person pinned, if any (C3 §2 `replyLanguage`). */
  pinned: Lang | undefined;
  onKeep(lang: Lang): void;
}

/** C3 §3.4: Mona followed the person into another language; "Keep" pins the previous one for later turns. */
export function LanguageDivider({ to, from, pinned, onKeep }: LanguageDividerProps) {
  const { t } = useTranslation();
  const language = (l: Lang) => t(`language.${l}`);
  return (
    <div className="flex items-center gap-3 py-1" data-testid="language-divider">
      <span aria-hidden className="h-px flex-1 bg-border" />
      <span className="inline-flex flex-wrap items-center gap-x-1 font-ui text-[13px] leading-[18px] text-text-muted">
        <Icon name="info" size={14} />
        <span>{t('chat.languageDivider.continuing', { language: language(to) })}</span>
        <span aria-hidden>·</span>
        {pinned ? (
          <span role="status">{t('chat.languageDivider.kept', { language: language(pinned) })}</span>
        ) : (
          <button type="button" className="cursor-pointer border-0 bg-transparent p-0 font-ui text-[13px] leading-[18px] text-accent-strong underline" onClick={() => onKeep(from)}>
            {t('chat.languageDivider.keep', { language: language(from) })}
          </button>
        )}
      </span>
      <span aria-hidden className="h-px flex-1 bg-border" />
    </div>
  );
}
