import { ticketWords } from "../../app/theme";
import type { Ticket } from "../../shared/types";
import { Empty } from "../../shared/ui";
import "./tickets.css";

export function Tickets({ tickets }: { tickets: Ticket[] }) {
  if (!tickets.length) return <Empty>No wrong claims this week, so nothing to send.</Empty>;
  return (
    <ol className="tickets">
      {tickets.map((t, i) => (
        <li key={i} className="panel ticket">
          <div className="ticket__head">
            <strong>{ticketWords[t.kind]}</strong>
            <span className="muted">{t.wrong_claims} wrong answers, {t.engines.join(", ")}</span>
          </div>
          <p className="ticket__what">{t.product}: {t.attribute.replace("_", " ")}</p>
          <p className="ticket__draft">{t.draft}</p>
        </li>
      ))}
    </ol>
  );
}
