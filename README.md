
# Sustainability Framework Analyser

A Streamlit application for assessing sustainability reports against multiple
reporting frameworks with Claude.

## Accuracy and scale features

- **Vision-aware PDF analysis:** PyMuPDF retains PDF page numbers and renders up
  to 30 visually dense, drawing-heavy, or scanned pages as JPEGs. Claude receives
  those page images alongside page-tagged extracted text, so charts and
  image-based tables can contribute evidence.
- **Confidence flags:** every requirement verdict includes `high`, `medium`, or
  `low` confidence plus a reason. Low-confidence verdicts are sorted into a
  human-review queue and included in the Excel export.
- **Complete-result checks:** stable requirement IDs are reconciled against the
  requested framework set, preventing omitted, duplicated, or rewritten model
  results from silently changing the coverage score.
- **Message Batches:** independent framework requests are submitted through the
  Anthropic Message Batches API by default. Results are matched through unique
  `custom_id` values even when returned out of order. Failed or malformed batch
  items retry individually, oversized multimodal payloads fall back safely, and
  batch usage is shown using the 50% batch pricing.
- **Page citations:** extracted evidence is requested in `[Page N] quote` format.

Both vision and batch processing can be disabled in the Report Analyser UI.
Anthropic notes that a Message Batch may take up to 24 hours; the current UI
waits for up to one hour, retains the batch ID and analysis context in the
Streamlit session, and offers a resume action without resubmitting the batch.

## Run locally

```bash
python -m pip install -r requirements.txt
streamlit run streamlit_app.py
```

Set `ANTHROPIC_API_KEY` in Streamlit secrets or enter it in the application.

Run the core regression tests without making API calls:

```bash
python -m unittest discover -s tests -v
```
