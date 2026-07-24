
# Sustainability Framework Analyser

A Streamlit application for assessing sustainability reports against multiple
reporting frameworks with Claude Haiku 4.5 or OpenAI GPT-5.6.

## Models and pricing

Users can choose either a single model or configure all three roles in the
optional reviewed cascade:

1. **Analyst:** Claude Haiku 4.5 or GPT-5.6 Luna performs the initial assessment.
2. **Reviewer:** GPT-5.6 Luna, Claude Haiku 4.5, GPT-5.6 Terra, or Claude
   Sonnet 5 reviews every analyst verdict, including its evidence, confidence,
   and audit rationale.
3. **Senior reviewer:** GPT-5.6 Terra, Claude Sonnet 5, Claude Opus 5, or
   GPT-5.6 Sol reviews only requirements where analyst and reviewer assign
   different classifications.

The analyst and reviewer must differ, as must the reviewer and senior reviewer.
These rules are enforced in both the UI and analysis engine. Single-model runs
never silently switch to a differently priced fallback.

List prices below are USD per million tokens as of 24 July 2026:

| Model | Standard input / output | Cache read / write | Batch input / output |
| --- | ---: | ---: | ---: |
| Claude Haiku 4.5 | $1 / $5 | $0.10 / $1.25 | $0.50 / $2.50 |
| GPT-5.6 Luna | $1 / $6 | $0.10 / $1.25 | $0.50 / $3 |
| GPT-5.6 Terra | $2.50 / $15 | $0.25 / $3.125 | $1.25 / $7.50 |
| Claude Sonnet 5* | $2 / $10 | $0.20 / $2.50 | $1 / $5 |
| Claude Opus 5 | $5 / $25 | $0.50 / $6.25 | $2.50 / $12.50 |
| GPT-5.6 Sol | $5 / $30 | $0.50 / $6.25 | $2.50 / $15 |

\* Sonnet 5 introductory pricing applies through 31 August 2026; the app's
catalogue should be updated when Anthropic's standard $3 / $15 rates begin.

Vision tokenisation differs by provider, and GPT-5.6 reasoning tokens are
included in billed output. Luna and Terra requests above 272,000 input tokens
use OpenAI's higher long-context rates. The application calculates an estimated
run cost from the usage returned by the selected provider.

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
  Message Batches for Haiku or OpenAI Batch for Luna and Terra. Results are
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
