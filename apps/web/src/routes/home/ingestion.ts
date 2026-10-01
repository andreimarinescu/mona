export interface IngestionFigures {
  week: number;
  today: number;
  peak: number;
  peakDate: string | null;
}

/** The 7-day total, today's count and the busiest day of the 14 daily counts (oldest first). */
export function ingestionFigures(days: { date: string; count: number }[]): IngestionFigures {
  const week = days.slice(-7).reduce((sum, d) => sum + d.count, 0);
  const today = days[days.length - 1]?.count ?? 0;
  let peak = 0;
  let peakDate: string | null = null;
  for (const d of days) {
    if (d.count > peak) {
      peak = d.count;
      peakDate = d.date;
    }
  }
  return { week, today, peak, peakDate };
}
