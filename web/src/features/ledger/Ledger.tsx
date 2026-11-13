import type { Console } from "../../shared/types";
import { Empty } from "../../shared/ui";

export const TRAINED = 2; // column of the trained verifier, the design the rest of the console uses

export function Ledger({ designs, rows }: { designs: string[]; rows: Console["ledger"] }) {
  if (!rows.length) return <Empty>No run yet. Run python3 scripts/evaluate.py, then scripts/readme.py.</Empty>;
  return (
    <div className="panel" style={{ overflowX: "auto" }}>
      <table>
        <thead>
          <tr>
            <th scope="col">Measured on every claim</th>
            {designs.map((d, i) => (
              <th scope="col" key={d} style={i === TRAINED ? { color: "var(--ink)" } : undefined}>{d}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.label}>
              <th scope="row">{r.label}</th>
              {r.values.map((v, i) => (
                <td key={i} style={i === TRAINED ? { fontWeight: 700 } : undefined}>{v}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
