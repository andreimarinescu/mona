import { toasts } from './toast/store';

if (import.meta.env.DEV) Object.assign(window, { __mona: { toasts } });
