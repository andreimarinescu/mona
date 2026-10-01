export interface SparklineProps {
  values: number[];
  label: string;
}

/** Daily bars, the last one (today) in the accent colour; `label` is the sentence a screen reader gets. */
export function Sparkline({ values, label }: SparklineProps) {
  const peak = Math.max(1, ...values);
  const width = 6;
  const gap = 4;
  const height = 48;
  return (
    <svg role="img" aria-label={label} viewBox={`0 0 ${values.length * (width + gap) - gap} ${height}`} className="h-12 w-full max-w-[220px]" preserveAspectRatio="none" data-testid="sparkline">
      {values.map((v, i) => {
        const h = v === 0 ? 2 : Math.max(3, Math.round((v / peak) * (height - 2)));
        return <rect key={i} x={i * (width + gap)} y={height - h} width={width} height={h} rx={1.5} fill={i === values.length - 1 ? 'var(--accent)' : 'var(--chart-auto)'} data-today={i === values.length - 1 ? '' : undefined} />;
      })}
    </svg>
  );
}
