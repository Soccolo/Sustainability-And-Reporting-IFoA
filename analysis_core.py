"""Core PDF and Claude analysis helpers used by the Streamlit application.

This module deliberately has no Streamlit dependency so the API contract and
PDF handling can be unit tested without starting the UI.
"""

from __future__ import annotations

import base64
import json
import re
import time
from typing import Any, Callable, Iterable

import anthropic


CLASSIFICATION_COVERS = "Covers the framework"
CLASSIFICATION_PARTLY = "Partly covers the framework"
CLASSIFICATION_DOESNT = "Doesn't cover the framework"
ALL_CLASSIFICATIONS = [
    CLASSIFICATION_COVERS,
    CLASSIFICATION_PARTLY,
    CLASSIFICATION_DOESNT,
]

PRIMARY_MODEL = "claude-haiku-4-5-20251001"
FALLBACK_MODEL = "claude-sonnet-5"

# Sonnet uses the conservative post-promotional standard rate so estimates do
# not become understated when temporary pricing ends. Batch and cache modifiers
# are applied per response below.
MODEL_PRICING_PER_MTOK = {
    PRIMARY_MODEL: (1.0, 5.0),
    FALLBACK_MODEL: (3.0, 15.0),
}


def extract_pdf_pages(
    pdf_file: Any,
    first_page: int = 1,
    last_page: int | None = None,
    include_vision: bool = False,
    max_vision_pages: int = 30,
) -> list[dict[str, Any]]:
    """Extract selected PDF pages and optionally render visual-heavy pages.

    Page numbers are one-based and always retained. Vision candidates include
    pages with embedded images, substantial vector drawing content, or little
    extractable text (which catches scanned/image-only pages). The page limit
    keeps multimodal requests below practical API payload and token limits.
    """
    import pymupdf

    pdf_bytes = pdf_file.read()
    if hasattr(pdf_file, "seek"):
        pdf_file.seek(0)

    pages: list[dict[str, Any]] = []
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        start_idx = max(0, first_page - 1)
        stop_idx = min(len(doc), last_page if last_page is not None else len(doc))
        if start_idx >= stop_idx:
            return []

        for page_idx in range(start_idx, stop_idx):
            page = doc[page_idx]
            text = page.get_text("text").strip()
            try:
                embedded_images = len(page.get_images(full=True))
            except Exception:
                embedded_images = 0
            try:
                page_area = max(float(page.rect.width * page.rect.height), 1.0)
                image_area = 0.0
                for image_info in page.get_image_info():
                    x0, y0, x1, y1 = image_info["bbox"]
                    image_area += max(0.0, x1 - x0) * max(0.0, y1 - y0)
                image_coverage = min(image_area / page_area, 1.0)
            except Exception:
                image_coverage = 0.0
            try:
                vector_drawings = len(page.get_drawings())
            except Exception:
                vector_drawings = 0

            # Rank large raster content, vector charts/tables, and scans above
            # recurring small logos. Image count is only a fallback signal when
            # older PyMuPDF versions cannot report image bounding boxes.
            sparse_text_bonus = 250 if len(text) < 100 else 0
            image_score = (
                image_coverage * 500
                if image_coverage > 0
                else embedded_images * 25
            )
            visual_score = image_score + min(vector_drawings, 100) * 3 + sparse_text_bonus
            is_visual_candidate = (
                embedded_images > 0 or vector_drawings >= 12 or len(text) < 100
            )
            pages.append(
                {
                    "page_number": page_idx + 1,
                    "text": text,
                    "visual_score": visual_score,
                    "is_visual_candidate": is_visual_candidate,
                }
            )

        if include_vision and max_vision_pages > 0:
            ranked = sorted(
                (p for p in pages if p["is_visual_candidate"]),
                key=lambda p: (-p["visual_score"], p["page_number"]),
            )[:max_vision_pages]
            render_page_numbers = {p["page_number"] for p in ranked}

            for page_data in pages:
                if page_data["page_number"] not in render_page_numbers:
                    continue
                page = doc[page_data["page_number"] - 1]
                pixmap = page.get_pixmap(
                    matrix=pymupdf.Matrix(1.25, 1.25), alpha=False
                )
                try:
                    image_bytes = pixmap.tobytes("jpeg", jpg_quality=60)
                except TypeError:  # PyMuPDF versions before jpg_quality support
                    image_bytes = pixmap.tobytes("jpeg")
                page_data["image_base64"] = base64.standard_b64encode(
                    image_bytes
                ).decode("ascii")

    return pages


def format_report_text(pages: Iterable[dict[str, Any]]) -> str:
    """Build model context without losing PDF page boundaries."""
    sections = []
    for page in pages:
        page_number = page.get("page_number", "?")
        text = page.get("text", "").strip()
        sections.append(f"[Page {page_number}]\n{text or '[No extractable text; inspect page image]'}")
    return "\n\n".join(sections)


def build_vision_blocks(
    pages: Iterable[dict[str, Any]],
    max_encoded_bytes: int | None = None,
) -> list[dict[str, Any]]:
    """Convert rendered pages to labelled Anthropic image content blocks."""
    blocks: list[dict[str, Any]] = []
    candidates = sorted(
        (page for page in pages if page.get("image_base64")),
        key=lambda page: (-page.get("visual_score", 0), page["page_number"]),
    )
    selected = []
    encoded_bytes = 0
    for page in candidates:
        image_data = page.get("image_base64")
        if (
            max_encoded_bytes is not None
            and encoded_bytes + len(image_data) > max_encoded_bytes
        ):
            continue
        selected.append(page)
        encoded_bytes += len(image_data)

    for page in sorted(selected, key=lambda item: item["page_number"]):
        image_data = page["image_base64"]
        blocks.extend(
            [
                {
                    "type": "text",
                    "text": f"PDF page {page['page_number']} (visual rendering):",
                },
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": image_data,
                    },
                },
            ]
        )
    return blocks


def normalise_classification(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if "covers" in raw and "partly" not in raw and "doesn" not in raw:
        return CLASSIFICATION_COVERS
    if "partly" in raw:
        return CLASSIFICATION_PARTLY
    return CLASSIFICATION_DOESNT


def normalise_confidence(value: Any) -> str:
    """Return high/medium/low, defaulting uncertain values to human review."""
    raw = str(value or "").strip().lower()
    if raw in {"high", "medium", "low"}:
        return raw
    if raw in {"certain", "very high"}:
        return "high"
    if raw in {"moderate", "mid"}:
        return "medium"
    return "low"


def estimate_usage_cost(
    usage_records: Iterable[dict[str, Any]],
) -> tuple[float, float]:
    """Return conservative USD cost and net prompt-cache savings.

    The default five-minute cache costs 1.25x for writes and 0.1x for reads.
    These multipliers stack with the Message Batches 50% discount.
    """
    cost = 0.0
    cache_savings = 0.0
    for record in usage_records:
        input_rate, output_rate = MODEL_PRICING_PER_MTOK.get(
            record.get("model"), (3.0, 15.0)
        )
        pricing_factor = 0.5 if record.get("batch_priced") else 1.0
        input_tokens = int(record.get("input_tokens", 0) or 0)
        output_tokens = int(record.get("output_tokens", 0) or 0)
        cache_read = int(record.get("cache_read_tokens", 0) or 0)
        cache_write = int(record.get("cache_write_tokens", 0) or 0)
        cost += pricing_factor * (
            input_tokens * input_rate
            + output_tokens * output_rate
            + cache_read * input_rate * 0.1
            + cache_write * input_rate * 1.25
        ) / 1_000_000
        cache_savings += pricing_factor * (
            cache_read * input_rate * 0.9
            - cache_write * input_rate * 0.25
        ) / 1_000_000
    return cost, cache_savings


def _system_message(report_text: str) -> list[dict[str, Any]]:
    return [
        {
            "type": "text",
            "text": (
                "You are an expert sustainability and ESG analyst. Assess only from the "
                "provided report evidence, including page images containing charts, diagrams, "
                "and image-based tables. For each requirement, search the entire report, extract "
                "the strongest short verbatim evidence, classify coverage rigorously, and explain "
                "the verdict. Prefix every extract with its page marker, for example "
                "'[Page 12] Scope 1 emissions were...'.\n\n"
                "Use exactly one classification: 'Covers the framework' for comprehensive, "
                "specific evidence; 'Partly covers the framework' for incomplete, vague, or "
                "borderline evidence; or \"Doesn't cover the framework\" when meaningful evidence "
                "is absent.\n\n"
                "Also assign confidence in the verdict: high when evidence and boundary are clear; "
                "medium when interpretation is needed; low when evidence is ambiguous, conflicting, "
                "hard to read, chart-dependent, or near a classification boundary. Confidence is "
                "about certainty in the verdict, not whether coverage is good.\n\n"
                f"REPORT TEXT BY PDF PAGE:\n{report_text}"
            ),
            "cache_control": {"type": "ephemeral"},
        }
    ]


def _build_prompt(
    framework: str,
    full_name: str,
    topics: dict[str, list[str]],
    requirement_refs: dict[tuple[str, str], str] | None,
    start_index: int = 1,
) -> tuple[str, dict[str, dict[str, str]]]:
    refs = requirement_refs or {}
    expected: dict[str, dict[str, str]] = {}
    lines = [
        f"Assess every requirement of the {full_name} ({framework}) framework.",
        "Use both the page-tagged text and the labelled PDF page images supplied before this instruction.",
        "",
    ]
    idx = start_index
    for topic, requirements in topics.items():
        for requirement in requirements:
            requirement_id = f"R{idx:04d}"
            reference = refs.get((framework, requirement), "")
            reference_tag = f" (Source: {reference})" if reference else ""
            lines.append(
                f"{requirement_id}. [{topic}]{reference_tag} {requirement}"
            )
            expected[requirement_id] = {
                "topic": topic,
                "reference": reference,
                "requirement": requirement,
            }
            idx += 1

    lines.extend(
        [
            "",
            "Respond only with a JSON array. Each element must contain exactly these keys:",
            "{",
            '  "requirement_id": "<R-number exactly as supplied>",',
            '  "topic": "<topic from square brackets>",',
            '  "reference": "<Source reference exactly as supplied, or empty string>",',
            '  "requirement": "<requirement text>",',
            '  "relevant_extracts": ["[Page N] <short verbatim quote>", "..."],',
            '  "classification": "<Covers the framework | Partly covers the framework | Doesn\'t cover the framework>",',
            '  "confidence": "<high | medium | low>",',
            '  "confidence_reason": "<one concise sentence explaining uncertainty>",',
            '  "rationale": "<2-3 sentence evidence-based explanation>"',
            "}",
            "If there is no relevant evidence, use an empty extracts array and Doesn't cover the framework.",
            "Return raw JSON only: no markdown, backticks, or preamble.",
        ]
    )
    return "\n".join(lines), expected


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _parse_message(message: Any) -> list[dict[str, Any]]:
    if _get(message, "stop_reason") == "max_tokens":
        raise ValueError("Response truncated (max_tokens reached)")
    raw = "".join(
        str(_get(block, "text", ""))
        for block in _get(message, "content", [])
        if _get(block, "type") == "text"
    ).strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()
    parsed = json.loads(raw)
    if not isinstance(parsed, list):
        raise ValueError("Claude response must be a JSON array")
    if not all(isinstance(item, dict) for item in parsed):
        raise ValueError("Every Claude result must be a JSON object")
    return parsed


def _usage_values(message: Any) -> dict[str, int]:
    usage = _get(message, "usage", {})
    return {
        "input_tokens": int(_get(usage, "input_tokens", 0) or 0),
        "output_tokens": int(_get(usage, "output_tokens", 0) or 0),
        "cache_read_tokens": int(_get(usage, "cache_read_input_tokens", 0) or 0),
        "cache_write_tokens": int(_get(usage, "cache_creation_input_tokens", 0) or 0),
    }


def _validate_items(
    items: Iterable[dict[str, Any]],
    expected: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    items = list(items)
    returned_ids = [str(item.get("requirement_id", "")) for item in items]
    if (
        len(returned_ids) != len(set(returned_ids))
        or set(returned_ids) != set(expected)
    ):
        missing = sorted(set(expected) - set(returned_ids))
        extras = sorted(set(returned_ids) - set(expected))
        raise ValueError(
            "Claude returned an incomplete requirement set "
            f"(missing={missing}, unexpected_or_duplicate={extras})."
        )
    return items


def _normalise_items(
    framework: str,
    items: Iterable[dict[str, Any]],
    expected: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    normalised = []
    for item in items:
        requirement_id = str(item["requirement_id"])
        canonical = expected[requirement_id]
        extracts = item.get("relevant_extracts", [])
        if not isinstance(extracts, list):
            extracts = []
        normalised.append(
            {
                "framework": framework,
                "requirement_id": requirement_id,
                "topic": canonical["topic"],
                "reference": canonical["reference"],
                "requirement": canonical["requirement"],
                "relevant_extracts": [str(extract) for extract in extracts],
                "classification": normalise_classification(item.get("classification")),
                "confidence": normalise_confidence(item.get("confidence")),
                "confidence_reason": item.get("confidence_reason", ""),
                "rationale": item.get("rationale", ""),
            }
        )
    return normalised


def _custom_id(index: int, framework: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", framework.lower()).strip("-")[:40]
    return f"framework-{index:02d}-{slug or 'unknown'}"


def _add_usage(
    total: dict[str, Any],
    message: Any,
    model: str,
    *,
    batch_priced: bool = False,
) -> None:
    usage = _usage_values(message)
    for key, value in usage.items():
        total[key] += value
    if batch_priced:
        total["batch_input_tokens"] += usage["input_tokens"]
        total["batch_output_tokens"] += usage["output_tokens"]
    total["usage_records"].append(
        {
            "model": model,
            "batch_priced": batch_priced,
            **usage,
        }
    )
    total["models_used"].add(model)


def _sync_request(
    client: Any,
    params: dict[str, Any],
    fallback_model: str,
) -> tuple[Any, str]:
    try:
        return client.messages.create(**params), params["model"]
    except anthropic.RateLimitError:
        fallback_params = {**params, "model": fallback_model}
        return client.messages.create(**fallback_params), fallback_model


def analyze_report_with_claude(
    report_text: str,
    selected_frameworks: list[str],
    api_key: str,
    framework_requirements: dict[str, dict[str, list[str]]],
    framework_full_names: dict[str, str],
    requirement_refs: dict[tuple[str, str], str] | None = None,
    report_pages: list[dict[str, Any]] | None = None,
    use_batch: bool = True,
    progress_callback: Callable[[float], None] | None = None,
    status_callback: Callable[[str, str], None] | None = None,
    poll_interval_seconds: float = 2.0,
    max_batch_wait_seconds: float = 3600.0,
    existing_batch_id: str | None = None,
    batch_id_callback: Callable[[str], None] | None = None,
    client: Any | None = None,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, Any]]:
    """Assess all selected frameworks using batch or synchronous Messages API."""
    client = client or anthropic.Anthropic(api_key=api_key)
    system = _system_message(report_text)
    framework_count = sum(
        bool(framework_requirements.get(framework))
        for framework in selected_frameworks
    )
    # Reserve room under the 256 MB batch cap for repeated report text,
    # prompts, and JSON overhead. Individual requests also stay comfortably
    # below the standard Messages endpoint payload limit.
    report_text_bytes = len(report_text.encode("utf-8"))
    vision_budget = min(
        18_000_000,
        180_000_000 // max(1, framework_count),
        max(0, 24_000_000 - report_text_bytes),
    )
    vision_blocks = build_vision_blocks(
        report_pages or [], max_encoded_bytes=vision_budget
    )
    prepared: list[dict[str, Any]] = []

    for index, framework in enumerate(selected_frameworks):
        topics = framework_requirements.get(framework)
        if not topics:
            continue
        prompt, expected = _build_prompt(
            framework,
            framework_full_names.get(framework, framework),
            topics,
            requirement_refs,
        )
        prepared.append(
            {
                "framework": framework,
                "custom_id": _custom_id(index, framework),
                "expected": expected,
                "params": {
                    "model": PRIMARY_MODEL,
                    "max_tokens": 16384,
                    "system": system,
                    "messages": [
                        {
                            "role": "user",
                            "content": [*vision_blocks, {"type": "text", "text": prompt}],
                        }
                    ],
                },
            }
        )

    # Enforce a safe per-request payload ceiling for both batch and standard
    # Messages calls. If JSON overhead pushes a request over the limit, first
    # drop its optional page images; if text alone is too large, ask the user
    # to select a narrower page range before any billable request is made.
    for item in prepared:
        request_bytes = len(
            json.dumps(item["params"], ensure_ascii=False).encode("utf-8")
        )
        if request_bytes > 30_000_000 and vision_blocks:
            item["params"]["messages"][0]["content"] = [
                item["params"]["messages"][0]["content"][-1]
            ]
            request_bytes = len(
                json.dumps(item["params"], ensure_ascii=False).encode("utf-8")
            )
        if request_bytes > 30_000_000:
            raise ValueError(
                f"The {item['framework']} request is too large for the "
                "Messages API. Select a narrower PDF page range."
            )

    results: list[dict[str, Any]] = []
    usage_total: dict[str, Any] = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "batch_input_tokens": 0,
        "batch_output_tokens": 0,
        "usage_records": [],
        "models_used": set(),
        "batch_api": bool(use_batch and prepared),
        "batch_id": None,
        "vision_pages": len(vision_blocks) // 2,
    }
    failures: list[dict[str, Any]] = []

    if use_batch and prepared:
        batch_requests = [
            {"custom_id": item["custom_id"], "params": item["params"]}
            for item in prepared
        ]
        serialized_batch_bytes = len(
            json.dumps({"requests": batch_requests}, ensure_ascii=False).encode(
                "utf-8"
            )
        )
        if serialized_batch_bytes > 240_000_000:
            if status_callback:
                status_callback(
                    "warning",
                    "The multimodal batch would exceed the safe payload limit; "
                    "using individual requests instead.",
                )
            failures = list(prepared)
            usage_total["batch_api"] = False
            batch = None
        elif existing_batch_id:
            batch = client.messages.batches.retrieve(existing_batch_id)
        else:
            try:
                batch = client.messages.batches.create(requests=batch_requests)
            except anthropic.APIStatusError as error:
                if getattr(error, "status_code", None) != 413:
                    raise
                if status_callback:
                    status_callback(
                        "warning",
                        "Anthropic rejected the batch payload as too large; "
                        "using individual requests instead.",
                    )
                failures = list(prepared)
                usage_total["batch_api"] = False
                batch = None

        if batch is None:
            pass
        else:
            usage_total["batch_id"] = batch.id
            if batch_id_callback:
                batch_id_callback(batch.id)
            if status_callback:
                action = "Resuming" if existing_batch_id else "Submitted"
                status_callback(
                    "info",
                    f"{action} batch {batch.id}; waiting for "
                    f"{len(prepared)} framework results.",
                )
            started = time.monotonic()
            while _get(batch, "processing_status") != "ended":
                if time.monotonic() - started > max_batch_wait_seconds:
                    raise TimeoutError(
                        f"Message Batch {batch.id} is still processing. "
                        "Resume it from the Report Analyser instead of submitting again."
                    )
                if poll_interval_seconds:
                    time.sleep(poll_interval_seconds)
                batch = client.messages.batches.retrieve(batch.id)
                counts = _get(batch, "request_counts", {})
                completed = sum(
                    int(_get(counts, key, 0) or 0)
                    for key in ("succeeded", "errored", "canceled", "expired")
                )
                if progress_callback:
                    progress_callback(min(0.95, completed / max(1, len(prepared))))

            by_id = {item["custom_id"]: item for item in prepared}
            seen_ids: set[str] = set()
            for batch_result in client.messages.batches.results(batch.id):
                custom_id = _get(batch_result, "custom_id")
                prepared_item = by_id.get(custom_id)
                if not prepared_item:
                    continue
                seen_ids.add(custom_id)
                result = _get(batch_result, "result")
                if _get(result, "type") != "succeeded":
                    failures.append(prepared_item)
                    continue
                message = _get(result, "message")
                _add_usage(
                    usage_total,
                    message,
                    prepared_item["params"]["model"],
                    batch_priced=True,
                )
                try:
                    items = _validate_items(
                        _parse_message(message), prepared_item["expected"]
                    )
                    results.extend(
                        _normalise_items(
                            prepared_item["framework"],
                            items,
                            prepared_item["expected"],
                        )
                    )
                except (ValueError, json.JSONDecodeError):
                    failures.append(prepared_item)

            failures.extend(
                item for item in prepared if item["custom_id"] not in seen_ids
            )
    else:
        failures = list(prepared)

    # Retrying only failed requests preserves a useful run when one batch item
    # errors or returns malformed/truncated JSON.
    for index, prepared_item in enumerate(failures):
        if status_callback and usage_total["batch_api"]:
            status_callback(
                "warning",
                f"Retrying {prepared_item['framework']} outside the batch after an incomplete batch result.",
            )
        message, model = _sync_request(client, prepared_item["params"], FALLBACK_MODEL)
        _add_usage(usage_total, message, model)
        try:
            items = _validate_items(
                _parse_message(message), prepared_item["expected"]
            )
        except (ValueError, json.JSONDecodeError):
            # Large framework responses get a final topic-by-topic retry.
            framework = prepared_item["framework"]
            items = []
            topics = framework_requirements[framework]
            requirement_index = 1
            retry_vision_blocks = prepared_item["params"]["messages"][0][
                "content"
            ][:-1]
            for topic, requirements in topics.items():
                topic_prompt, topic_expected = _build_prompt(
                    framework,
                    framework_full_names.get(framework, framework),
                    {topic: requirements},
                    requirement_refs,
                    start_index=requirement_index,
                )
                requirement_index += len(requirements)
                topic_params = {
                    **prepared_item["params"],
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                *retry_vision_blocks,
                                {
                                    "type": "text",
                                    "text": topic_prompt,
                                },
                            ],
                        }
                    ],
                }
                topic_message, topic_model = _sync_request(client, topic_params, FALLBACK_MODEL)
                _add_usage(usage_total, topic_message, topic_model)
                topic_items = _validate_items(
                    _parse_message(topic_message), topic_expected
                )
                items.extend(
                    _normalise_items(framework, topic_items, topic_expected)
                )
        else:
            items = _normalise_items(
                prepared_item["framework"], items, prepared_item["expected"]
            )
        results.extend(items)
        if progress_callback and not use_batch:
            progress_callback((index + 1) / max(1, len(failures)))

    framework_summaries: dict[str, dict[str, Any]] = {}
    for framework in selected_frameworks:
        framework_results = [r for r in results if r["framework"] == framework]
        if not framework_results:
            continue
        counts = {classification: 0 for classification in ALL_CLASSIFICATIONS}
        for result in framework_results:
            counts[result["classification"]] += 1
        total = len(framework_results)
        score = sum(
            1.0 if r["classification"] == CLASSIFICATION_COVERS else
            0.5 if r["classification"] == CLASSIFICATION_PARTLY else 0.0
            for r in framework_results
        ) / total
        framework_summaries[framework] = {
            "counts": counts,
            "total": total,
            "avg_score": score,
            "low_confidence": sum(r["confidence"] == "low" for r in framework_results),
        }

    confidence_order = {"low": 0, "medium": 1, "high": 2}
    results.sort(key=lambda r: (confidence_order[r["confidence"]], r["framework"], r["topic"]))
    if progress_callback:
        progress_callback(1.0)
    return results, framework_summaries, usage_total
