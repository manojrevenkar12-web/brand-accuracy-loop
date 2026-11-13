# Working on brand-accuracy-loop

## Fast feedback

```bash
python -m pytest -q                         # reading, verdicts, sources, world rules, API (~4 s)
ruff check src tests scripts && ruff format --check src tests scripts
python3 scripts/evaluate.py                 # dev world (~45 s): trains models/verifier.json, writes reports/dev.json
python3 scripts/readme.py && git diff --exit-code README.md web/public/data/console.json
cd web && npm test && npm run build
```

## Invariants

1. **The truth stays in the world.** `src/accuracy/world/` knows which claims are right and which page caused each
   one. Only `scripts/evaluate.py` and the tests read it; nothing else under `src/accuracy` imports it (a test checks).
2. **The world does not read the pipeline's settings.** `config/world.toml` drives the world, `config/pipeline.toml`
   and `config/lexicon.toml` the pipeline.
3. **Unverified is not wrong.** A claim about a fact the brand has not verified is reported as unverifiable.
4. **Labels come from people.** The verifier trains on annotations (with their mistakes), never on the world's truth.
   Label cleaning sends doubtful labels to a second reader; it does not overwrite them with model output.
5. **No publisher is blamed without evidence.** A page is a suspect only if it says the same wrong value and
   disagrees with the vault. Otherwise the cause is the engine's memory.
6. **Answer text is data.** Pages and answers are read for values; sentences addressed to AI systems are not followed.
7. **Same luck for every design.** Engine choices, citations and publisher replies are keyed by the event, so
   designs differ only by what they decide.
8. **Settings in config; reports generated.** `reports/*.json` and `models/verifier.json` by `scripts/evaluate.py`;
   README results and the console data by `scripts/readme.py`. Timings go to `reports/*_timing.json`, which is not
   compared in CI.

## The held-out rule

`python3 scripts/evaluate.py --heldout` runs the held-out world once, with the verifier trained on the dev world,
and writes `config/heldout.lock`. After that, changes are measured on the dev world only, and the held-out numbers
stay as they first came out.
