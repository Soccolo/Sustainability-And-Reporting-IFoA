
# Sustainability Framework Analyser

A Streamlit application for assessing sustainability reports against multiple
reporting frameworks with Anthropic Claude or OpenAI GPT models.

## Models and pricing

Users can choose either a single model (Claude Haiku 4.5, GPT-6 Luna, or
GPT-6 Sol) or configure all three roles in the optional reviewed cascade:

1. **Analyst:** Claude Haiku 4.5 or GPT-6 Luna performs the initial assessment.
2. **Reviewer:** GPT-6 Luna, Claude Haiku 4.5, GPT-5.6 Terra, or Claude
   Sonnet 5 assesses every requirement blind: it reads the report itself and
   never sees the analyst's verdict, evidence or rationale, so agreement is
   independent confirmation rather than the reviewer following the analyst.
3. **Senior reviewer:** GPT-6 Sol or Claude Opus 5.5 reviews only requirements
   where analyst and reviewer assign different classifications. GPT-6 Sol, the
   default, always runs in OpenAI Fast mode at medium reasoning effort.

The analyst and reviewer must differ, as must the reviewer and senior reviewer.
These rules are enforced in both the UI and analysis engine. Single-model runs
never silently switch to a differently priced fallback.

List prices below are USD per million tokens as of 22 September 2026:

| Model | Standard input / output | Cache read / write | Batch input / output |
| --- | ---: | ---: | ---: |
| Claude Haiku 4.5 | $1 / $5 | $0.10 / $1.25 | $0.50 / $2.50 |
| GPT-6 Luna | $0.10 / $0.50 | $0.01 / $0.125 | $0.05 / $0.25 |
| GPT-5.6 Terra | $2 / $12 | $0.20 / $2.50 | $1 / $6 |
| Claude Sonnet 5 | $2 / $10 | $0.20 / $2.50 | $1 / $5 |
| Claude Opus 5.5 | $4 / $20 | $0.20 / $5 | $2 / $10 |
| GPT-6 Sol, Fast mode* | $4 / $20 | $0.40 / $5 | $1 / $5 |

\* GPT-6 Sol's standard rates are $2 / $10 (cache $0.20 / $2.50). The app
requests Fast mode (`service_tier: "fast"`), which OpenAI bills at twice the
standard rates, except for Batch API runs, which always use batch pricing. Each cost is taken from the tier the response reports: OpenAI
can downgrade Fast mode requests to standard processing under its ramp-rate
limits, and those report `service_tier: "default"` and are costed at standard
rates.

Sonnet 5's $2 / $10 is now Anthropic's standard price; the scheduled rise to
$3 / $15 did not happen. Opus 5.5 cache reads cost 0.05× input rather than the
usual 0.1×. Vision tokenisation differs by provider, and reasoning tokens are
included in billed output. GPT requests above 272,000 prompt tokens are billed
at OpenAI's long-context rates (2× input and cache, 1.5× output, for the whole
request); Claude models have no long-context premium. The application
calculates an estimated run cost from the usage returned by each provider.

Superseded models (GPT-5.6 Luna, GPT-5.6 Sol, and Claude Opus 5) can no longer
be selected but stay priced in the catalogue, so results and pending batches
created before the upgrade can still be costed and resumed.

## Estimated CO2 emissions

Every analysis and comparison shows an estimate of the electricity used to
serve its API requests and the resulting operational emissions, next to the
cost. The estimate is location-based. Model training, hardware manufacturing,
and water use are outside its boundary. Providers do not publish per-model
energy figures, so the estimate is built from published research:

- **Electricity per output token** is `0.1 + 0.003 × active parameters
  (billions)` Wh per 1,000 tokens. This line is fitted to the production-serving
  estimates of Oviedo et al. (2026), which include whole-server power and
  data-centre overhead (PUE). Those estimates are Mixtral 8x22B 0.06 Wh, Llama
  3.1 70B 0.09 Wh, and Llama 3.1 405B 0.39 Wh per query of about 300 output
  tokens.
- **Active parameters** come from EcoLogits' published ranges, taking the
  geometric midpoint. GPT-6 Luna, GPT-6 Sol, and Claude Opus 5.5 are not yet
  estimated, so they use their direct predecessors (GPT-5.6 Luna, GPT-5.6 Sol,
  and Claude Opus 5) as documented proxies.
- **Prompt tokens** count as 0.2 of an output token, because they are processed
  in parallel. This matches both providers' 5:1 output-to-input price ratio.
  **Cache reads** skip recomputation and count as 0.02. Attention work grows
  with context, so energy per token rises linearly with prompt length, reaching
  +100% for prompt tokens and +50% for output tokens at 272,000 tokens.
- **Fast mode** requests count double. This is a conservative assumption: Fast
  mode buys extra accelerator time per token, reflected in its 2× price. Batch
  requests use the same factors as standard requests.
- **Electricity is converted** at 349.7 g CO2e/kWh, the US average total output
  emission rate in EPA eGRID2023 (770.9 lb CO2e/MWh).
- **The plausible range** shown runs from a third of to three times the central
  figure. It reflects uncertainty in model size, hardware generation, idle
  capacity, and data-centre location.

The per-model factors in use are listed in the app under "How the cost and CO2
estimates are calculated". Sources: Oviedo et al. (2026), "Energy use of AI
inference, efficiency pathways, and test-time scaling", *Joule*
([arXiv:2509.20241](https://arxiv.org/abs/2509.20241));
[EcoLogits](https://ecologits.ai) model parameter estimates;
[EPA eGRID2023 summary data](https://www.epa.gov/egrid/summary-data).

## Accuracy and scale features

- **Vision-aware PDF analysis:** PyMuPDF retains PDF page numbers and renders up
  to 30 visually dense, drawing-heavy, or scanned pages as JPEGs. The selected
  model receives those page images alongside page-tagged extracted text, so
  charts and image-based tables can contribute evidence.
- **Confidence flags:** every requirement verdict includes `high`, `medium`, or
  `low` confidence plus a reason. Low-confidence verdicts are sorted into a
  human-review queue and included in the Excel export.
- **Complete-result checks:** stable requirement IDs are reconciled against the
  requested framework set, preventing omitted, duplicated, or rewritten model
  results from silently changing the coverage score.
- **Selective cross-model review:** the optional cascade records every model's
  verdict and rationale. Analyst/reviewer agreements are accepted without
  calling the senior reviewer; disagreements are sent for adjudication. Three
  different classifications are flagged for human review and excluded from
  coverage percentages rather than presented as model agreement.
- **Provider-aware batches:** independent framework requests use Anthropic
  Message Batches for Haiku or OpenAI Batch for Luna and Sol. Results are
  matched through unique `custom_id` values even when returned out of order.
  Failed or malformed items retry individually with the same selected model,
  oversized multimodal payloads fall back safely, and usage reflects the 50%
  batch discount.
- **Page citations:** extracted evidence is requested in `[Page N] quote` format.

Both vision and batch processing can be disabled in the Report Analyser UI.
Provider batches can take up to 24 hours; the current UI waits for up to one
hour, retains the provider, model, batch ID, and analysis context in the
Streamlit session, and offers a resume action without resubmitting. Closing or
losing the Streamlit session can still lose that local resume reference, and
batch inputs and outputs remain subject to the selected provider's API data
retention policies.

The reviewed cascade deliberately uses standard API requests because later
stages depend on earlier results, while the current resume mechanism safely
tracks only one provider batch. Cascade mode is therefore slower and normally
costs more than a single-model run, but it avoids re-submitting completed review
stages. The app requests only the provider keys required by the selected roles.
When an OpenAI key permits the Models endpoint, access to every selected OpenAI
model is checked before billable generation starts. Restricted keys that cannot
read Models are validated by the first actual Responses request instead. If a
later review stage has a recoverable transient or response-reconciliation
failure, earlier results and recorded usage are retained as provisional
human-review items instead of being silently discarded. Authentication and
permanent request errors remain fatal so they cannot be mistaken for model
verdicts.

## Run locally

```bash
python -m pip install -r requirements.txt
streamlit run streamlit_app.py
```

Set `ANTHROPIC_API_KEY` and/or `OPENAI_API_KEY` in Streamlit secrets, or enter
the key for each selected provider in the application. API usage is billed
directly to the account associated with those keys.

Run the core regression tests without making API calls:

```bash
python -m unittest discover -s tests -v
```
