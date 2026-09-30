import { useEffect } from 'react';
import { useAppState } from '../state/context';

const TEXT_FIELD = 'input:not([type="checkbox"]):not([type="radio"]):not([type="button"]):not([type="submit"]), textarea, select, [contenteditable=""], [contenteditable="true"]';
const OWNS_ESCAPE = '[role="menu"], [role="dialog"], [role="alertdialog"]';

function inTextField(target: EventTarget | null): boolean {
  return target instanceof Element && target.closest(TEXT_FIELD) !== null;
}

export function useShellShortcuts(home: boolean) {
  const { chat, askMona, closeChat } = useAppState();
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.defaultPrevented) return;
      if (e.key === '/' && !e.ctrlKey && !e.metaKey && !e.altKey && !inTextField(e.target)) {
        e.preventDefault();
        askMona({ home });
      } else if (e.key === 'Escape' && chat.open) {
        if (e.target instanceof Element && e.target.closest(OWNS_ESCAPE)) return;
        closeChat();
      }
    }
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [home, chat.open, askMona, closeChat]);
}
