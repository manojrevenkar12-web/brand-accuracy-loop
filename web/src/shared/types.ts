export type Verdict = "accurate" | "inaccurate" | "unverifiable" | "review";

export interface ClaimRow {
  start: number;
  end: number;
  attribute: string;
  truth: Verdict;
  verdict: Verdict;
  rules: Verdict;
  p_wrong: number | null;
  verified: string;
  reasons: string[];
  source: string | null;
  source_why: string | null;
}

export interface Example {
  id: string;
  engine: string;
  locale: string;
  text: string;
  citations: string[];
  claims: ClaimRow[];
}

export interface Series {
  name: string;
  key: string;
  values: number[];
  landed: number;
  sent: number;
}

export interface Ticket {
  kind: "brand_page" | "publisher" | "engine_feed";
  product: string;
  attribute: string;
  wrong_claims: number;
  engines: string[];
  draft: string;
}

export interface Console {
  generated_from: string;
  counts: { answers: number; claims: number; engines: string[]; german_claims: number };
  designs: string[];
  ledger: { label: string; values: string[] }[];
  attribution: { method: string; cause_found: number; innocent_page_blamed: number; wrong_claims: number }[];
  loop: { weeks: number; budget: number; series: Series[] };
  examples: Example[];
  tickets: Ticket[];
  heldout: null | {
    answers: number;
    claims: number;
    trained: number;
    false_alarms: number;
    rules_false_alarms: number;
    wrong_before: number;
    wrong_after: number;
  };
}
