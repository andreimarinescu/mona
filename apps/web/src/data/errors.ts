import { ApiError } from './http';

export const ERROR_CODES = [
  'invalid_request',
  'unauthenticated',
  'invalid_password',
  'csrf_failed',
  'not_allowed',
  'not_found',
  'not_ready',
  'stale',
  'conflict',
  'turn_in_progress',
  'already_answered',
  'already_undone',
  'superseded',
  'in_use',
  'too_large',
  'unsupported_media_type',
  'invalid_template',
  'invalid_rule',
  'invalid_value',
  'not_undoable',
  'not_renderable',
  'locked',
  'too_many_attempts',
  'internal',
  'unavailable',
] as const;

export function errorKey(err: unknown): string {
  const code = err instanceof ApiError ? err.code : 'internal';
  return (ERROR_CODES as readonly string[]).includes(code) ? `errors.${code}` : 'errors.internal';
}

export function errorValues(err: unknown): Record<string, string | number> {
  if (!(err instanceof ApiError)) return {};
  const offset = err.details?.offset;
  const message = err.details?.message;
  return { offset: typeof offset === 'number' ? offset : 0, message: typeof message === 'string' ? message : '' };
}
