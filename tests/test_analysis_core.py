import json
import sys
import types
import unittest
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch


try:
    import anthropic  # noqa: F401
except ModuleNotFoundError:
    fake_anthropic = types.ModuleType("anthropic")
    fake_anthropic.RateLimitError = type("RateLimitError", (Exception,), {})
    fake_anthropic.APIStatusError = type("APIStatusError", (Exception,), {})
    fake_anthropic.APIError = type("APIError", (Exception,), {})
    fake_anthropic.AuthenticationError = type(
        "AuthenticationError", (fake_anthropic.APIStatusError,), {}
    )
    fake_anthropic.Anthropic = object
    sys.modules["anthropic"] = fake_anthropic

import analysis_core


def message_for(items, input_tokens=100, output_tokens=20):
    return SimpleNamespace(
        stop_reason="end_turn",
        content=[SimpleNamespace(type="text", text=json.dumps(items))],
        usage=SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_input_tokens=10,
            cache_creation_input_tokens=5,
        ),
    )


class FakeBatches:
    def __init__(self, results):
        self._results = results
        self.requests = None

    def create(self, requests):
        self.requests = requests
        return SimpleNamespace(id="msgbatch_test", processing_status="ended")

    def retrieve(self, batch_id):
        raise AssertionError("An already-ended batch should not be polled")

    def results(self, batch_id):
        return iter(self._results)


class FakeClient:
    def __init__(self, results):
        self.messages = SimpleNamespace(batches=FakeBatches(results))


class AnalysisCoreTests(unittest.TestCase):
    def test_page_text_and_vision_blocks_keep_page_identity(self):
        pages = [
            {"page_number": 7, "text": "Emissions table", "image_base64": "abc"},
            {"page_number": 8, "text": "Narrative only"},
        ]

        self.assertEqual(
            analysis_core.format_report_text(pages),
            "[Page 7]\nEmissions table\n\n[Page 8]\nNarrative only",
        )
        blocks = analysis_core.build_vision_blocks(pages)
        self.assertEqual(blocks[0]["text"], "PDF page 7 (visual rendering):")
        self.assertEqual(blocks[1]["source"]["media_type"], "image/jpeg")
        self.assertEqual(len(blocks), 2)

    def test_vision_budget_keeps_highest_value_pages(self):
        pages = [
            {
                "page_number": 1,
                "visual_score": 10,
                "image_base64": "aa",
            },
            {
                "page_number": 2,
                "visual_score": 100,
                "image_base64": "bb",
            },
        ]
        blocks = analysis_core.build_vision_blocks(
            pages, max_encoded_bytes=3
        )
        self.assertEqual(blocks[0]["text"], "PDF page 2 (visual rendering):")
        self.assertEqual(len(blocks), 2)

    def test_invalid_confidence_is_conservatively_low(self):
        self.assertEqual(analysis_core.normalise_confidence(None), "low")
        self.assertEqual(analysis_core.normalise_confidence("uncertain"), "low")
        self.assertEqual(analysis_core.normalise_confidence("Moderate"), "medium")
        self.assertEqual(analysis_core.normalise_confidence("HIGH"), "high")

    def test_cost_estimate_includes_cache_and_batch_modifiers(self):
        cost, savings = analysis_core.estimate_usage_cost(
            [
                {
                    "model": analysis_core.PRIMARY_MODEL,
                    "batch_priced": True,
                    "input_tokens": 1_000_000,
                    "output_tokens": 1_000_000,
                    "cache_read_tokens": 1_000_000,
                    "cache_write_tokens": 1_000_000,
                }
            ]
        )
        self.assertAlmostEqual(cost, 3.675)
        self.assertAlmostEqual(savings, 0.325)

    def test_requirement_set_must_be_exact_and_uses_canonical_text(self):
        expected = {
            "R0001": {
                "topic": "governance",
                "reference": "FW 1",
                "requirement": "Canonical first requirement",
            },
            "R0002": {
                "topic": "metrics",
                "reference": "FW 2",
                "requirement": "Canonical second requirement",
            },
        }
        with self.assertRaises(ValueError):
            analysis_core._validate_items(
                [{"requirement_id": "R0001"}], expected
            )
        with self.assertRaises(ValueError):
            analysis_core._validate_items(
                [
                    {"requirement_id": "R0001"},
                    {"requirement_id": "R0001"},
                ],
                expected,
            )

        items = [
            {
                "requirement_id": "R0001",
                "topic": "model-mutated-topic",
                "requirement": "model-mutated-text",
                "classification": "Covers the framework",
                "confidence": "high",
            },
            {
                "requirement_id": "R0002",
                "classification": "Doesn't cover the framework",
                "confidence": "medium",
            },
        ]
        normalised = analysis_core._normalise_items(
            "FW", analysis_core._validate_items(items, expected), expected
        )
        self.assertEqual(
            normalised[0]["requirement"], "Canonical first requirement"
        )
        self.assertEqual(normalised[0]["topic"], "governance")

    def test_pdf_extraction_renders_visual_and_scanned_pages(self):
        class FakePixmap:
            def tobytes(self, output, jpg_quality=None):
                self.output = output
                self.quality = jpg_quality
                return b"jpeg-bytes"

        class FakePage:
            def __init__(self, text, image_count=0, drawing_count=0):
                self.text = text
                self.image_count = image_count
                self.drawing_count = drawing_count

            def get_text(self, mode):
                return self.text

            def get_images(self, full=True):
                return [object()] * self.image_count

            def get_drawings(self):
                return [object()] * self.drawing_count

            def get_pixmap(self, matrix, alpha):
                return FakePixmap()

        class FakeDoc:
            def __init__(self):
                self.pages = [
                    # A repeated small logo should rank below a vector chart.
                    FakePage("Normal narrative " * 20, image_count=1),
                    FakePage("", image_count=1),
                    FakePage("Chart labels " * 20, drawing_count=15),
                ]

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def __len__(self):
                return len(self.pages)

            def __getitem__(self, index):
                return self.pages[index]

        fake_pymupdf = SimpleNamespace(
            open=lambda **kwargs: FakeDoc(),
            Matrix=lambda x, y: (x, y),
        )
        with patch.dict(sys.modules, {"pymupdf": fake_pymupdf}):
            pages = analysis_core.extract_pdf_pages(
                BytesIO(b"pdf"), include_vision=True, max_vision_pages=2
            )

        self.assertNotIn("image_base64", pages[0])
        self.assertIn("image_base64", pages[1])
        self.assertIn("image_base64", pages[2])
        self.assertEqual([p["page_number"] for p in pages], [1, 2, 3])

    def test_batch_results_are_mapped_by_custom_id_and_low_confidence_first(self):
        # API batch results deliberately arrive in reverse request order.
        result_b = SimpleNamespace(
            custom_id="framework-01-fw-b",
            result=SimpleNamespace(
                type="succeeded",
                message=message_for(
                    [
                        {
                            "requirement_id": "R0001",
                            "topic": "metrics",
                            "requirement": "B requirement",
                            "classification": "Covers the framework",
                            "confidence": "high",
                            "confidence_reason": "Clear table.",
                            "rationale": "Specific evidence is present.",
                            "relevant_extracts": ["[Page 9] 100 tCO2e"],
                        }
                    ]
                ),
            ),
        )
        result_a = SimpleNamespace(
            custom_id="framework-00-fw-a",
            result=SimpleNamespace(
                type="succeeded",
                message=message_for(
                    [
                        {
                            "requirement_id": "R0001",
                            "topic": "governance",
                            "requirement": "A requirement",
                            "classification": "Partly covers the framework",
                            "confidence": "low",
                            "confidence_reason": "Borderline evidence.",
                            "rationale": "Some evidence is present.",
                            "relevant_extracts": ["[Page 3] Board oversight"],
                        }
                    ]
                ),
            ),
        )
        client = FakeClient([result_b, result_a])

        results, summaries, usage = analysis_core.analyze_report_with_claude(
            report_text="[Page 3] Board oversight",
            selected_frameworks=["FW A", "FW B"],
            api_key="unused",
            framework_requirements={
                "FW A": {"governance": ["A requirement"]},
                "FW B": {"metrics": ["B requirement"]},
            },
            framework_full_names={"FW A": "Framework A", "FW B": "Framework B"},
            report_pages=[{"page_number": 3, "text": "", "image_base64": "abc"}],
            use_batch=True,
            poll_interval_seconds=0,
            client=client,
        )

        self.assertEqual([r["framework"] for r in results], ["FW A", "FW B"])
        self.assertEqual(results[0]["confidence"], "low")
        self.assertEqual(summaries["FW A"]["low_confidence"], 1)
        self.assertEqual(usage["batch_id"], "msgbatch_test")
        self.assertEqual(usage["input_tokens"], 200)
        self.assertEqual(usage["batch_input_tokens"], 200)
        self.assertEqual(usage["batch_output_tokens"], 40)
        self.assertEqual(len(client.messages.batches.requests), 2)
        first_content = client.messages.batches.requests[0]["params"]["messages"][0]["content"]
        self.assertEqual(first_content[1]["type"], "image")
        self.assertIn('"confidence": "<high | medium | low>"', first_content[-1]["text"])

    def test_existing_batch_is_retrieved_without_resubmission(self):
        batch_result = SimpleNamespace(
            custom_id="framework-00-fw-a",
            result=SimpleNamespace(
                type="succeeded",
                message=message_for(
                    [
                        {
                            "requirement_id": "R0001",
                            "classification": "Covers the framework",
                            "confidence": "high",
                            "confidence_reason": "Clear evidence.",
                            "rationale": "The requirement is met.",
                            "relevant_extracts": ["[Page 1] Evidence"],
                        }
                    ]
                ),
            ),
        )
        client = FakeClient([batch_result])
        client.messages.batches.retrieve = lambda batch_id: SimpleNamespace(
            id=batch_id, processing_status="ended"
        )

        results, _, usage = analysis_core.analyze_report_with_claude(
            report_text="[Page 1] Evidence",
            selected_frameworks=["FW A"],
            api_key="unused",
            framework_requirements={
                "FW A": {"governance": ["A requirement"]}
            },
            framework_full_names={"FW A": "Framework A"},
            use_batch=True,
            existing_batch_id="msgbatch_existing",
            poll_interval_seconds=0,
            client=client,
        )

        self.assertEqual(client.messages.batches.requests, None)
        self.assertEqual(usage["batch_id"], "msgbatch_existing")
        self.assertEqual(results[0]["requirement"], "A requirement")

    def test_billed_invalid_batch_response_is_counted_before_retry(self):
        invalid_batch_result = SimpleNamespace(
            custom_id="framework-00-fw-a",
            result=SimpleNamespace(
                type="succeeded",
                message=message_for(
                    [{"requirement_id": "WRONG"}],
                    input_tokens=70,
                    output_tokens=7,
                ),
            ),
        )
        client = FakeClient([invalid_batch_result])
        client.messages.create = lambda **params: message_for(
            [
                {
                    "requirement_id": "R0001",
                    "classification": "Covers the framework",
                    "confidence": "high",
                    "rationale": "Complete.",
                }
            ],
            input_tokens=30,
            output_tokens=3,
        )

        results, _, usage = analysis_core.analyze_report_with_claude(
            report_text="[Page 1] Evidence",
            selected_frameworks=["FW A"],
            api_key="unused",
            framework_requirements={
                "FW A": {"governance": ["A requirement"]}
            },
            framework_full_names={"FW A": "Framework A"},
            use_batch=True,
            poll_interval_seconds=0,
            client=client,
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(usage["input_tokens"], 100)
        self.assertEqual(usage["output_tokens"], 10)
        self.assertEqual(usage["batch_input_tokens"], 70)
        self.assertEqual(len(usage["usage_records"]), 2)


if __name__ == "__main__":
    unittest.main()
