import { chart, seriesShort } from "../../app/theme";
import type { Console } from "../../shared/types";
import { Empty } from "../../shared/ui";

export function LoopChart({ loop }: { loop: Console["loop"] }) {
  const series = loop.series;
  if (!series.length || !series[0].values.length) return <Empty>The correction loop did not run.</Empty>;
  const { width, height, pad, yMax, yTicks, dot, label } = chart;
  const weeks = series[0].values.length;
  const x = (i: number) => pad.left + (i * (width - pad.left - pad.right)) / Math.max(1, weeks - 1);
  const y = (v: number) => pad.top + (1 - v / yMax) * (height - pad.top - pad.bottom);
  const ranked = [...series].sort((a, b) => b.values[weeks - 1] - a.values[weeks - 1]);
  return (
    <div className="panel">
      <svg viewBox={`0 0 ${width} ${height}`} role="img"
        aria-label={`Share of wrong claims over ${weeks} weeks for each way of choosing tickets`}>
        {yTicks.map((t) => (
          <g key={t}>
            <line x1={pad.left} x2={width - pad.right} y1={y(t)} y2={y(t)} stroke="var(--rule)" />
            <text x={pad.left - 8} y={y(t)} textAnchor="end" dominantBaseline="middle" fontSize={label} fill="var(--ink-soft)">{t}%</text>
          </g>
        ))}
        {Array.from({ length: weeks }, (_, i) => (
          <text key={i} x={x(i)} y={height - 8} textAnchor="middle" fontSize={label} fill="var(--ink-soft)">{i + 1}</text>
        ))}
        {ranked.map((s, rank) => {
          const color = `var(--series-${rank})`;
          const last = s.values[weeks - 1];
          return (
            <g key={s.key}>
              <polyline fill="none" stroke={color} strokeWidth={rank === ranked.length - 1 ? 3 : 2}
                points={s.values.map((v, i) => `${x(i)},${y(v)}`).join(" ")} />
              <circle cx={x(weeks - 1)} cy={y(last)} r={dot} fill={color} />
              <text x={x(weeks - 1) + 8} y={y(last)} dominantBaseline="middle" fontSize={label} fill="var(--ink)">
                {last}% {seriesShort[s.key] ?? s.name}
              </text>
            </g>
          );
        })}
      </svg>
      <p className="muted">Week of the loop along the bottom; {loop.budget} tickets a week.</p>
    </div>
  );
}
