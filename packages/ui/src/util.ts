import type { Lang } from './types';

export function cx(...parts: unknown[]): string {
  return parts.filter(Boolean).join(' ');
}

export function pick<T>(dict: Record<Lang, T>, lang?: Lang): T {
  return (lang && dict[lang]) || dict.en;
}
