export interface DayBucket<T> {
  key: string;
  date: Date;
  items: T[];
}

function dayKey(d: Date): string {
  return `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`;
}

export function groupByDay<T>(items: T[], at: (item: T) => string): DayBucket<T>[] {
  const buckets: DayBucket<T>[] = [];
  for (const item of items) {
    const date = new Date(at(item));
    const key = dayKey(date);
    const last = buckets[buckets.length - 1];
    if (last?.key === key) last.items.push(item);
    else buckets.push({ key, date, items: [item] });
  }
  return buckets;
}

export function dayRelation(date: Date, now: Date): 'today' | 'yesterday' | 'other' {
  if (dayKey(date) === dayKey(now)) return 'today';
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  return dayKey(date) === dayKey(yesterday) ? 'yesterday' : 'other';
}
