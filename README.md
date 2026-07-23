
# Sustainability Framework Analyser

A Streamlit application for assessing sustainability reports against multiple
reporting frameworks with Claude Haiku 4.5 or OpenAI GPT-5.6.

## Models and pricing

Users choose the model before each analysis. The selected model is used
throughout the run; the application does not silently switch to a differently
priced fallback.

List prices below are USD per million tokens as of 23 July 2026:

| Model | Standard input / output | Cache read / write | Batch input / output |
| --- | ---: | ---: | ---: |
| Claude Haiku 4.5 | $1 / $5 | $0.10 / $1.25 | $0.50 / $2.50 |
| GPT-5.6 Luna | $1 / $6 | $0.10 / $1.25 | $0.50 / $3 |
| GPT-5.6 Terra | $2.50 / $15 | $0.25 / $3.125 | $1.25 / $7.50 |

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

## Run locally

```bash
python -m pip install -r requirements.txt
streamlit run streamlit_app.py
```

Set `ANTHROPIC_API_KEY` and/or `OPENAI_API_KEY` in Streamlit secrets, or enter
the key for the selected provider in the application. API usage is billed
directly to the account associated with that key.

Run the core regression tests without making API calls:

```bash
python -m unittest discover -s tests -v
```
