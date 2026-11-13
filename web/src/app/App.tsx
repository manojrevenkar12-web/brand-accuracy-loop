import { Diagnosis } from "../features/diagnosis/Diagnosis";
import { Inspector } from "../features/inspector/Inspector";
import { Ledger } from "../features/ledger/Ledger";
import { LoopChart } from "../features/loop/LoopChart";
import { Tickets } from "../features/tickets/Tickets";
import { useConsole } from "../shared/api";
import { ErrorState, Section, Skeleton } from "../shared/ui";

export function App() {
  const { data, isPending, error, refetch } = useConsole();
  return (
    <main className="page">
      <header className="masthead">
        <h1>What the assistants said about your products, checked.</h1>
        <p>
          Every price, warranty, range and fee an AI engine states is read out of its answer, compared with the facts
          the brand verified, and, when it is wrong, traced to the page or the engine memory it came from.
        </p>
      </header>
      {isPending ? (
        <Skeleton rows={7} />
      ) : error ? (
        <ErrorState message={error.message} onRetry={() => refetch()} />
      ) : (
        <>
          <Inspector examples={data.examples} />
          <Section id="ledger" title="How often each verifier is right"
            lede={`${data.counts.claims.toLocaleString("en")} claims in ${data.counts.answers.toLocaleString("en")} answers from ${data.counts.engines.length} engines, ${Math.round((100 * data.counts.german_claims) / data.counts.claims)} % of them German, counted against the simulated world's truth.`}>
            <Ledger designs={data.designs} rows={data.ledger} />
          </Section>
          <div className="split">
            <Section id="diagnosis" title="Who gets the ticket"
              lede="A publisher should hear from a brand only when its page really says the wrong thing.">
              <Diagnosis rows={data.attribution} />
            </Section>
            <Section id="loop" title="Wrong claims, week by week"
              lede="The same answers, engine luck and publisher replies for every design; only the tickets differ.">
              <LoopChart loop={data.loop} />
            </Section>
          </div>
          <Section id="tickets" title="This week's first tickets"
            lede="Ranked by how many answers each cause made wrong. A person approves each one before it is sent.">
            <Tickets tickets={data.tickets} />
          </Section>
          {data.heldout && (
            <Section id="heldout" title="On the held-out world"
              lede={`Run once with the dev-trained verifier: ${data.heldout.claims.toLocaleString("en")} claims. ${data.heldout.trained}% judged right, ${data.heldout.false_alarms} false alarms per 1,000 claims (rules: ${data.heldout.rules_false_alarms}). Wrong claims went from ${data.heldout.wrong_before}% to ${data.heldout.wrong_after}% over the loop.`}>
              <></>
            </Section>
          )}
          <p className="muted">Generated from {data.generated_from}.</p>
        </>
      )}
    </main>
  );
}
