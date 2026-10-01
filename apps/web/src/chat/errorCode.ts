import { ERROR_CODES } from '../data/errors';

export const STREAM_CODES = ['mona_offline', 'stream_interrupted', 'internal'];

/** C3 §4.4 `errorText`, or the C2 error code of a refused request; anything else is `internal`. */
export function chatErrorCode(error: Error): string {
  const text = error.message.trim();
  if (STREAM_CODES.includes(text)) return text;
  try {
    const code = (JSON.parse(text) as { error?: { code?: string } }).error?.code;
    if (code && (ERROR_CODES as readonly string[]).includes(code)) return code;
  } catch {
    /* not a C2 envelope */
  }
  return 'internal';
}
