import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { pieces } from "../features/inspector/Inspector";
import type { Console } from "../shared/types";
import { App } from "./App";

const example = {
  id: "w0-1-chat", engine: "chat", locale: "en-US", citations: ["https://gearwire.example/q10-1"],
  text: "The Acme Q10 costs $329. It lasts about 30 hours.",
  claims: [
    { start: 19, end: 23, attribute: "price", truth: "inaccurate", verdict: "inaccurate", rules: "inaccurate",
      p_wrong: 0.99, verified: "$279 / €259", reasons: ["equals the value before the last verified change (points to wrong)"],
      source: "https://gearwire.example/q10-1", source_why: "cited, and says the same wrong value" },
    { start: 40, end: 48, attribute: "battery life", truth: "accurate", verdict: "accurate", rules: "inaccurate",
      p_wrong: 0.01, verified: "32 hours", reasons: [], source: null, source_why: null },
  ],
} as const;

const sample = {
  generated_from: "reports/dev.json",
  counts: { answers: 1280, claims: 4336, engines: ["chat"], german_claims: 1300 },
  designs: ["String match", "Rules", "Trained", "Trained + people"],
  ledger: [{ label: "False alarms per 1,000 claims", values: ["251", "19.1", "0", "0"] }],
  attribution: [{ method: "Find the page that says the same wrong value", cause_found: 80.6, innocent_page_blamed: 0, wrong_claims: 412 }],
  loop: { weeks: 2, budget: 30, series: [{ name: "No corrections", key: "none", values: [9.5, 9.9], landed: 0, sent: 0 }] },
  examples: [example],
  tickets: [{ kind: "publisher", product: "Acme Q10", attribute: "price", wrong_claims: 3, engines: ["chat"], draft: "Hello" }],
  heldout: null,
} as unknown as Console;

const renderApp = () => render(<QueryClientProvider client={new QueryClient()}><App /></QueryClientProvider>);
afterEach(() => vi.restoreAllMocks());

describe("console", () => {
  it("shows a skeleton, then the answer with its wrong figure corrected and explained", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(sample)));
    renderApp();
    expect(screen.getByLabelText("Loading")).toBeTruthy();
    expect(await screen.findByLabelText("$329: Wrong")).toBeTruthy();
    expect(screen.getAllByText("$279 / €259").length).toBe(2); // the correction above the line and in the note
    fireEvent.click(screen.getByLabelText("30 hours: Right"));
    expect(await screen.findByText(/rules said wrong/)).toBeTruthy();
    expect(screen.getByText("Ask the publisher")).toBeTruthy();
  });

  it("offers a retry when the data does not load", async () => {
    const f = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(new Response("", { status: 404 }));
    renderApp();
    expect(await screen.findByRole("alert")).toBeTruthy();
    f.mockResolvedValueOnce(new Response(JSON.stringify(sample)));
    fireEvent.click(screen.getByText("Retry"));
    await waitFor(() => expect(screen.getByText("False alarms per 1,000 claims")).toBeTruthy());
  });

  it("says what to do when there is no run", async () => {
    const empty = { ...sample, ledger: [], examples: [], tickets: [], attribution: [] };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(empty)));
    renderApp();
    expect((await screen.findAllByText(/No run yet|No answers in this run/)).length).toBe(2);
    expect(screen.getByText(/nothing to send/)).toBeTruthy();
  });

  it("splits an answer into plain text and claims", () => {
    const parts = pieces(example as never);
    expect(parts.map((p) => p.text)).toEqual(["The Acme Q10 costs ", "$329", ". It lasts about ", "30 hours", "."]);
  });
});
