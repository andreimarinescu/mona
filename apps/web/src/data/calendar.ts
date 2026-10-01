const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;

/** C8 §6.2: a `YYYY-MM-DD` date is a local calendar day, never UTC midnight. */
export function calendarDate(iso: string): Date {
  const m = ISO_DATE.exec(iso);
  return m ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])) : new Date(iso);
}

export function toIsoDate(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function addDays(iso: string, days: number): string {
  const d = calendarDate(iso);
  d.setDate(d.getDate() + days);
  return toIsoDate(d);
}
