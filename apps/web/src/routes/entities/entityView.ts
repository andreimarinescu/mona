import { format, type Lang } from '@mona/ui';
import type { Entity, PersonDetail } from '../../data/dto';

export function monogram(name: string): string {
  const words = name.split(/[\s'’-]+/).filter(Boolean);
  const letters = words.length > 1 ? [words[0]![0], words[1]![0]] : [words[0]?.slice(0, 2)];
  return letters.join('').toUpperCase();
}

/** `MM-DD` as "31 December" in the page language. */
export function fiscalYearEndText(mmdd: string, lang: Lang): string {
  const [m, d] = mmdd.split('-').map(Number);
  return m && d ? format.date(new Date(2000, m - 1, d), lang, 'dayMonth') : mmdd;
}

export function formatSiren(siren: string): string {
  return /^\d{9}$/.test(siren) ? siren.replace(/(\d{3})(?=\d)/g, '$1 ') : siren;
}

export function personLine(entity: Entity, people: PersonDetail[]): { name: string; role: string | null }[] {
  return entity.people.map((link) => {
    const person = people.find((p) => p.id === link.personId);
    return { name: person?.shortName ?? person?.displayName ?? '?', role: link.role };
  });
}

/** Visitors last, as the registry shows it: a built-in holding area rather than one of the practice's entities. */
export function sortEntities(items: Entity[], visitorsId: string | null): Entity[] {
  return [...items].sort((a, b) => Number(a.id === visitorsId) - Number(b.id === visitorsId));
}
