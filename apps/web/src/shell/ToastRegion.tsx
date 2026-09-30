import { Toast, ToastStack, format } from '@mona/ui';
import { useTranslation } from 'react-i18next';
import { useAppState } from '../state/context';
import { toasts, type ToastStore } from '../toast/store';
import { useToasts } from '../toast/useToasts';
import { useLang } from './useLang';

export function ToastRegion({ store = toasts }: { store?: ToastStore }) {
  const { t } = useTranslation();
  const lang = useLang();
  const { chat } = useAppState();
  const items = useToasts(store);
  return (
    <div
      className={`fixed bottom-24 right-4 z-[60] w-[420px] max-w-[calc(100vw_-_32px)] lg:bottom-6 ${chat.open ? 'lg:right-[484px]' : 'lg:right-6'}`}
      data-testid="toast-region"
    >
      <ToastStack inline>
        {items.map((item) => (
          <Toast
            key={item.id}
            tone={item.tone}
            from={item.from}
            lang={lang}
            title={t(item.message, { count: item.count, n: format.number(item.count, lang), ...item.values })}
            action={item.undo.length > 0 ? { label: t('toast.undo'), icon: 'undo', onClick: () => store.undo(item.id) } : undefined}
            onClose={() => store.dismiss(item.id)}
          />
        ))}
      </ToastStack>
    </div>
  );
}
