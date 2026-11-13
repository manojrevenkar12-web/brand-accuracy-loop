import type { Console } from "../../shared/types";
import { Empty } from "../../shared/ui";
import "./diagnosis.css";

function Bar({ value, tone, label }: { value: number; tone: "right" | "wrong"; label: string }) {
  return (
    <div className="bar" aria-label={`${label}: ${value}%`}>
      <span className="bar__track">
        <span className={`bar__fill bar__fill--${tone}`} style={{ width: `${value}%` }} />
      </span>
      <span className="bar__value">{value}%</span>
    </div>
  );
}

export function Diagnosis({ rows }: { rows: Console["attribution"] }) {
  if (!rows.length) return <Empty>No wrong claims were diagnosed in this run.</Empty>;
  return (
    <div className="panel diagnosis">
      {rows.map((r) => (
        <div key={r.method} className="diagnosis__row">
          <p className="diagnosis__method">{r.method}</p>
          <span className="muted">Cause found</span>
          <Bar value={r.cause_found} tone="right" label="Cause found" />
          <span className="muted">Blamed a page that was right</span>
          <Bar value={r.innocent_page_blamed} tone="wrong" label="Blamed a page that was right" />
        </div>
      ))}
      <p className="muted">Out of {rows[0].wrong_claims} wrong claims in week 1.</p>
    </div>
  );
}
