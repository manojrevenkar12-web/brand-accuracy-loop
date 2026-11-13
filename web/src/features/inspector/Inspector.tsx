import { AnimatePresence, motion as m } from "framer-motion";
import { useMemo, useState } from "react";
import { motion, verdictWords } from "../../app/theme";
import type { ClaimRow, Example } from "../../shared/types";
import { Empty } from "../../shared/ui";
import "./inspector.css";

type Piece = { text: string; claim?: ClaimRow; index?: number };

export function pieces(ex: Example): Piece[] {
  const claims = [...ex.claims].sort((a, b) => a.start - b.start);
  const out: Piece[] = [];
  let at = 0;
  claims.forEach((c, index) => {
    if (c.start < at) return; // overlapping spans: keep the first
    if (c.start > at) out.push({ text: ex.text.slice(at, c.start) });
    out.push({ text: ex.text.slice(c.start, c.end), claim: c, index });
    at = c.end;
  });
  if (at < ex.text.length) out.push({ text: ex.text.slice(at) });
  return out;
}

function Mark({ piece, active, onSelect, order }: { piece: Piece; active: boolean; onSelect: () => void; order: number }) {
  const c = piece.claim!;
  const wrong = c.verdict === "inaccurate";
  return (
    <span className="mark-wrap">
      <button
        className={`mark mark--${c.verdict}${active ? " is-active" : ""}`}
        aria-pressed={active}
        aria-label={`${piece.text}: ${verdictWords[c.verdict]}`}
        onClick={onSelect}
      >
        {piece.text}
        <m.span
          className="mark__line"
          aria-hidden
          initial={{ scaleX: 0 }}
          animate={{ scaleX: 1 }}
          transition={{ duration: motion.markDraw, delay: order * motion.markStagger, ease: motion.ease }}
        />
      </button>
      {wrong && c.verified && (
        <m.span
          className="mark__insert"
          aria-hidden
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: motion.note, delay: motion.markDraw + order * motion.markStagger }}
        >
          {c.verified}
        </m.span>
      )}
    </span>
  );
}

function Note({ claim, said }: { claim: ClaimRow; said: string }) {
  const agree = claim.verdict === claim.truth || (claim.verdict === "review");
  return (
    <m.aside
      key={`${claim.start}-${claim.attribute}`}
      className={`note note--${claim.verdict}`}
      initial={{ opacity: 0, x: 8 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0 }}
      transition={{ duration: motion.note, ease: motion.ease }}
      aria-live="polite"
    >
      <p className="note__verdict">{verdictWords[claim.verdict]}</p>
      <dl>
        <dt>Claim about</dt>
        <dd>{claim.attribute}</dd>
        <dt>The answer said</dt>
        <dd>{said}</dd>
        {claim.verified && (
          <>
            <dt>The brand verified</dt>
            <dd>{claim.verified}</dd>
          </>
        )}
        {claim.p_wrong !== null && (
          <>
            <dt>Chance it is wrong</dt>
            <dd>{Math.round(claim.p_wrong * 100)} %</dd>
          </>
        )}
      </dl>
      {claim.reasons.length > 0 && (
        <>
          <p className="note__head">What weighed most</p>
          <ul>{claim.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
        </>
      )}
      {claim.source && (
        <>
          <p className="note__head">Where it came from</p>
          <p className="note__source">
            {claim.source === "model" ? "The engine's own memory" : <a href={claim.source}>{claim.source}</a>}
            <span className="muted"> {claim.source_why}</span>
          </p>
        </>
      )}
      <p className="note__check muted">
        Hand-written rules said {verdictWords[claim.rules].toLowerCase()}. The simulated world's truth:{" "}
        {verdictWords[claim.truth].toLowerCase()}{agree ? "." : ", so this verdict is a miss."}
      </p>
    </m.aside>
  );
}

export function Inspector({ examples }: { examples: Example[] }) {
  const [which, setWhich] = useState(0);
  const [picked, setPicked] = useState<number | null>(null);
  const ex = examples[Math.min(which, examples.length - 1)];
  const parts = useMemo(() => (ex ? pieces(ex) : []), [ex]);
  if (!ex) return <Empty>No answers in this run yet. Run python3 scripts/evaluate.py, then scripts/readme.py.</Empty>;

  const firstWrong = parts.find((p) => p.claim?.verdict === "inaccurate")?.index ?? parts.find((p) => p.claim)?.index ?? null;
  const selected = picked ?? firstWrong;
  const sel = parts.find((p) => p.index === selected);
  let order = 0;

  return (
    <div className="inspector">
      <div className="inspector__picker" role="tablist" aria-label="Answers">
        {examples.map((e, i) => (
          <button
            key={e.id}
            role="tab"
            aria-selected={i === which}
            className="chip"
            onClick={() => {
              setWhich(i);
              setPicked(null);
            }}
          >
            {e.engine}, {e.locale}
          </button>
        ))}
      </div>
      <div className="inspector__body">
        <article className="sheet" lang={ex.locale.slice(0, 2)} key={ex.id}>
          <p className="sheet__text">
            {parts.map((p, i) =>
              p.claim ? (
                <Mark key={i} piece={p} order={order++} active={p.index === selected} onSelect={() => setPicked(p.index!)} />
              ) : (
                <span key={i}>{p.text}</span>
              ),
            )}
          </p>
          {ex.citations.length > 0 && (
            <ol className="sheet__cites">
              {ex.citations.map((u) => <li key={u}>{u.replace("https://", "")}</li>)}
            </ol>
          )}
        </article>
        <AnimatePresence mode="wait">{sel?.claim && <Note claim={sel.claim} said={sel.text} />}</AnimatePresence>
      </div>
    </div>
  );
}
