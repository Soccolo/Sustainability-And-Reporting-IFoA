"""Core PDF and model-analysis helpers used by the Streamlit application.

This module deliberately has no Streamlit dependency so the API contract and
PDF handling can be unit tested without starting the UI.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import time
from io import BytesIO
from typing import Any, Callable, Iterable

import anthropic

try:
    import openai
except ModuleNotFoundError:  # Tests can inject a client without the SDK installed.
    openai = None


CLASSIFICATION_COVERS = "Covers the framework"
CLASSIFICATION_PARTLY = "Partly covers the framework"
CLASSIFICATION_DOESNT = "Doesn't cover the framework"
ALL_CLASSIFICATIONS = [
    CLASSIFICATION_COVERS,
    CLASSIFICATION_PARTLY,
    CLASSIFICATION_DOESNT,
]

HAIKU_MODEL = "claude-haiku-4-5-20251001"
LUNA_MODEL = "gpt-5.6-luna"
TERRA_MODEL = "gpt-5.6-terra"
PRIMARY_MODEL = HAIKU_MODEL

# One catalogue drives the picker, request routing, and cost estimates. Prices
# are USD per million tokens and reflect first-party API list prices on
# 2026-07-23. Both providers apply a 50% Batch API discount.
MODEL_CATALOG: dict[str, dict[str, Any]] = {
    HAIKU_MODEL: {
        "label": "Claude Haiku 4.5",
        "provider": "anthropic",
        "input_price": 1.0,
        "cached_input_price": 0.1,
        "cache_write_price": 1.25,
        "output_price": 5.0,
        "batch_input_price": 0.5,
        "batch_output_price": 2.5,
        "description": "Fastest option and lowest output-token cost",
        "secret_name": "ANTHROPIC_API_KEY",
    },
    LUNA_MODEL: {
        "label": "GPT-5.6 Luna",
        "provider": "openai",
        "input_price": 1.0,
        "cached_input_price": 0.1,
        "cache_write_price": 1.25,
        "output_price": 6.0,
        "batch_input_price": 0.5,
        "batch_output_price": 3.0,
        "description": "Economical GPT-5.6 reasoning for high-volume analysis",
        "secret_name": "OPENAI_API_KEY",
        "long_context_threshold": 272_000,
        "long_input_multiplier": 2.0,
        "long_output_multiplier": 1.5,
    },
    TERRA_MODEL: {
        "label": "GPT-5.6 Terra",
        "provider": "openai",
        "input_price": 2.5,
        "cached_input_price": 0.25,
        "cache_write_price": 3.125,
        "output_price": 15.0,
        "batch_input_price": 1.25,
        "batch_output_price": 7.5,
        "description": "Higher-capability GPT-5.6 analysis at a higher cost",
        "secret_name": "OPENAI_API_KEY",
        "long_context_threshold": 272_000,
        "long_input_multiplier": 2.0,
        "long_output_multiplier": 1.5,
    },
}
USER_SELECTABLE_MODELS = tuple(MODEL_CATALOG)
MODEL_PRICING_PER_MTOK = {
    model_id: (details["input_price"], details["output_price"])
    for model_id, details in MODEL_CATALOG.items()
}


class AnalysisAuthenticationError(RuntimeError):
    """Raised when the selected provider rejects its API key."""


def get_model_config(model_id: str) -> dict[str, Any]:
    """Return a selected model's canonical metadata or fail visibly."""
    try:
        return MODEL_CATALOG[model_id]
    except KeyError as error:
        raise ValueError(f"Unsupported analysis model: {model_id}") from error


def model_picker_label(model_id: str) -> str:
    """Return a concise model-and-price label for the Streamlit picker."""
    model = get_model_config(model_id)
    return (
        f"{model['label']} — ${model['input_price']:g} input / "
        f"${model['output_price']:g} output per 1M tokens"
    )


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


def build_openai_vision_blocks(
    pages: Iterable[dict[str, Any]],
    max_encoded_bytes: int | None = None,
) -> list[dict[str, Any]]:
    """Convert rendered pages to labelled OpenAI Responses image inputs."""
    anthropic_blocks = build_vision_blocks(
        pages, max_encoded_bytes=max_encoded_bytes
    )
    blocks: list[dict[str, Any]] = []
    for block in anthropic_blocks:
        if block["type"] == "text":
            blocks.append({"type": "input_text", "text": block["text"]})
        else:
            source = block["source"]
            blocks.append(
                {
                    "type": "input_image",
                    "image_url": (
                        f"data:{source['media_type']};base64,{source['data']}"
                    ),
                    # Dense tables benefit from explicit high detail while
                    # avoiding GPT-5.6's potentially larger auto/original input.
                    "detail": "high",
                }
            )
    return blocks


def _openai_result_schema() -> dict[str, Any]:
    """Return the strict result contract shared by Luna and Terra."""
    item_properties = {
        "requirement_id": {"type": "string"},
        "topic": {"type": "string"},
        "reference": {"type": "string"},
        "requirement": {"type": "string"},
        "relevant_extracts": {
            "type": "array",
            "items": {"type": "string"},
        },
        "classification": {
            "type": "string",
            "enum": ALL_CLASSIFICATIONS,
        },
        "confidence": {
            "type": "string",
            "enum": ["high", "medium", "low"],
        },
        "confidence_reason": {"type": "string"},
        "rationale": {"type": "string"},
    }
    return {
        "type": "json_schema",
        "name": "framework_assessment",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": item_properties,
                        "required": list(item_properties),
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["items"],
            "additionalProperties": False,
        },
    }


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
    """Return estimated USD cost and net prompt-cache savings."""
    cost = 0.0
    cache_savings = 0.0
    for record in usage_records:
        model = get_model_config(str(record.get("model", "")))
        input_rate = float(model["input_price"])
        cached_input_rate = float(model["cached_input_price"])
        cache_write_rate = float(model["cache_write_price"])
        output_rate = float(model["output_price"])
        pricing_factor = 0.5 if record.get("batch_priced") else 1.0
        input_tokens = int(record.get("input_tokens", 0) or 0)
        output_tokens = int(record.get("output_tokens", 0) or 0)
        cache_read = int(record.get("cache_read_tokens", 0) or 0)
        cache_write = int(record.get("cache_write_tokens", 0) or 0)

        total_prompt_tokens = input_tokens + cache_read + cache_write
        if total_prompt_tokens > int(model.get("long_context_threshold", 10**18)):
            input_multiplier = float(model.get("long_input_multiplier", 1.0))
            output_multiplier = float(model.get("long_output_multiplier", 1.0))
            input_rate *= input_multiplier
            cached_input_rate *= input_multiplier
            cache_write_rate *= input_multiplier
            output_rate *= output_multiplier

        cost += pricing_factor * (
            input_tokens * input_rate
            + output_tokens * output_rate
            + cache_read * cached_input_rate
            + cache_write * cache_write_rate
        ) / 1_000_000
        cache_savings += pricing_factor * (
            cache_read * (input_rate - cached_input_rate)
            - cache_write * (cache_write_rate - input_rate)
        ) / 1_000_000
    return cost, cache_savings


def _system_prompt_text(report_text: str) -> str:
    return (
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
    )


def _system_message(report_text: str) -> list[dict[str, Any]]:
    return [
        {
            "type": "text",
            "text": _system_prompt_text(report_text),
            "cache_control": {"type": "ephemeral"},
        }
    ]


def _build_prompt(
    framework: str,
    full_name: str,
    topics: dict[str, list[str]],
    requirement_refs: dict[tuple[str, str], str] | None,
    start_index: int = 1,
    wrap_items: bool = False,
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

    response_instruction = (
        'Respond only with a JSON object whose single "items" property is an '
        "array. Each array element must contain exactly these keys:"
        if wrap_items
        else "Respond only with a JSON array. Each element must contain exactly these keys:"
    )
    lines.extend(
        [
            "",
            response_instruction,
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


def _parse_json_items(raw: str, *, wrapped: bool = False) -> list[dict[str, Any]]:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()
    parsed = json.loads(raw)
    if wrapped:
        if not isinstance(parsed, dict) or set(parsed) != {"items"}:
            raise ValueError('Model response must be an object containing only "items"')
        parsed = parsed["items"]
    if not isinstance(parsed, list):
        raise ValueError("Model response must contain a JSON array")
    if not all(isinstance(item, dict) for item in parsed):
        raise ValueError("Every model result must be a JSON object")
    return parsed


def _parse_message(message: Any) -> list[dict[str, Any]]:
    if _get(message, "stop_reason") == "max_tokens":
        raise ValueError("Response truncated (max_tokens reached)")
    raw = "".join(
        str(_get(block, "text", ""))
        for block in _get(message, "content", [])
        if _get(block, "type") == "text"
    )
    return _parse_json_items(raw)


def _parse_openai_response(response: Any) -> list[dict[str, Any]]:
    status = str(_get(response, "status", "completed") or "")
    if status == "incomplete":
        reason = _get(_get(response, "incomplete_details", {}), "reason", "unknown")
        raise ValueError(f"Response incomplete ({reason})")
    raw = str(_get(response, "output_text", "") or "")
    if not raw:
        parts: list[str] = []
        for output_item in _get(response, "output", []) or []:
            if _get(output_item, "type") != "message":
                continue
            for content in _get(output_item, "content", []) or []:
                if _get(content, "type") == "output_text":
                    parts.append(str(_get(content, "text", "")))
        raw = "".join(parts)
    return _parse_json_items(raw, wrapped=True)


def _usage_values(message: Any, provider: str = "anthropic") -> dict[str, int]:
    usage = _get(message, "usage", {})
    if provider == "openai":
        details = _get(usage, "input_tokens_details", {})
        total_input = int(_get(usage, "input_tokens", 0) or 0)
        cache_read = int(_get(details, "cached_tokens", 0) or 0)
        cache_write = int(
            _get(
                details,
                "cache_write_tokens",
                _get(usage, "cache_write_tokens", 0),
            )
            or 0
        )
        return {
            # OpenAI reports cached tokens inside input_tokens; normalise to
            # mutually exclusive buckets so cost calculations do not double-count.
            "input_tokens": max(0, total_input - cache_read - cache_write),
            "output_tokens": int(_get(usage, "output_tokens", 0) or 0),
            "cache_read_tokens": cache_read,
            "cache_write_tokens": cache_write,
        }
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
            "The selected model returned an incomplete requirement set "
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
    provider: str = "anthropic",
    batch_priced: bool = False,
) -> None:
    usage = _usage_values(message, provider=provider)
    for key, value in usage.items():
        total[key] += value
    if batch_priced:
        total["batch_input_tokens"] += usage["input_tokens"]
        total["batch_output_tokens"] += usage["output_tokens"]
    total["usage_records"].append(
        {
            "model": model,
            "provider": provider,
            "batch_priced": batch_priced,
            **usage,
        }
    )
    total["models_used"].add(model)


def _anthropic_sync_request(
    client: Any,
    params: dict[str, Any],
    max_attempts: int = 3,
) -> Any:
    """Retry transient rate limits without changing the user's chosen model."""
    for attempt in range(max_attempts):
        try:
            return client.messages.create(**params)
        except anthropic.RateLimitError:
            if attempt + 1 >= max_attempts:
                raise
            time.sleep(2**attempt)
    raise RuntimeError("Anthropic request retry loop ended unexpectedly")


def _summarise_results(
    results: list[dict[str, Any]],
    selected_frameworks: Iterable[str],
    progress_callback: Callable[[float], None] | None = None,
) -> dict[str, dict[str, Any]]:
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
            1.0
            if r["classification"] == CLASSIFICATION_COVERS
            else 0.5
            if r["classification"] == CLASSIFICATION_PARTLY
            else 0.0
            for r in framework_results
        ) / total
        framework_summaries[framework] = {
            "counts": counts,
            "total": total,
            "avg_score": score,
            "low_confidence": sum(
                r["confidence"] == "low" for r in framework_results
            ),
        }

    confidence_order = {"low": 0, "medium": 1, "high": 2}
    results.sort(
        key=lambda r: (
            confidence_order[r["confidence"]],
            r["framework"],
            r["topic"],
        )
    )
    if progress_callback:
        progress_callback(1.0)
    return framework_summaries


def _analyze_report_with_anthropic(
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
    model_id: str = PRIMARY_MODEL,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, Any]]:
    """Assess frameworks using Anthropic Messages or Message Batches."""
    model = get_model_config(model_id)
    if model["provider"] != "anthropic":
        raise ValueError(f"{model_id} is not an Anthropic model")
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
                    "model": model_id,
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
        "provider": "anthropic",
        "selected_model": model_id,
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
        message = _anthropic_sync_request(client, prepared_item["params"])
        _add_usage(usage_total, message, model_id)
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
                topic_message = _anthropic_sync_request(client, topic_params)
                _add_usage(usage_total, topic_message, model_id)
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

    framework_summaries = _summarise_results(
        results, selected_frameworks, progress_callback
    )
    return results, framework_summaries, usage_total


def _openai_prompt_cache_key(
    report_text: str,
    report_pages: Iterable[dict[str, Any]],
) -> str:
    """Scope cache bucketing to one report without exposing report content."""
    digest = hashlib.sha256(report_text.encode("utf-8"))
    for page in report_pages:
        image_data = page.get("image_base64")
        if not image_data:
            continue
        digest.update(str(page.get("page_number", "")).encode("ascii"))
        digest.update(hashlib.sha256(image_data.encode("ascii")).digest())
    return f"esg-{digest.hexdigest()[:40]}"


def _openai_request_params(
    model_id: str,
    system_text: str,
    prompt: str,
    vision_blocks: list[dict[str, Any]],
    prompt_cache_key: str,
) -> dict[str, Any]:
    return {
        "model": model_id,
        "instructions": system_text,
        "input": [
            {
                "role": "user",
                "content": [
                    *vision_blocks,
                    {"type": "input_text", "text": prompt},
                ],
            }
        ],
        "text": {"format": _openai_result_schema()},
        # Make the effective effort explicit and comparable across Luna/Terra.
        "reasoning": {"effort": "medium"},
        "max_output_tokens": 32_768,
        "store": False,
        "prompt_cache_key": prompt_cache_key,
    }


def _openai_sync_request(
    client: Any,
    params: dict[str, Any],
    max_attempts: int = 3,
) -> Any:
    """Retry OpenAI rate limits without changing model or provider."""
    rate_limit_type = getattr(openai, "RateLimitError", None) if openai else None
    for attempt in range(max_attempts):
        try:
            return client.responses.create(**params)
        except Exception as error:
            is_rate_limit = rate_limit_type and isinstance(error, rate_limit_type)
            if not is_rate_limit or attempt + 1 >= max_attempts:
                raise
            time.sleep(2**attempt)
    raise RuntimeError("OpenAI request retry loop ended unexpectedly")


def _openai_file_text(file_response: Any) -> str:
    value = _get(file_response, "text")
    if isinstance(value, str):
        return value
    content = _get(file_response, "content")
    if isinstance(content, bytes):
        return content.decode("utf-8")
    if isinstance(content, str):
        return content
    read = getattr(file_response, "read", None)
    if callable(read):
        value = read()
        return value.decode("utf-8") if isinstance(value, bytes) else str(value)
    raise ValueError("OpenAI batch output file did not contain readable text")


def _analyze_report_with_openai(
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
    model_id: str = LUNA_MODEL,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, Any]]:
    """Assess frameworks using OpenAI Responses or the file-based Batch API."""
    model = get_model_config(model_id)
    if model["provider"] != "openai":
        raise ValueError(f"{model_id} is not an OpenAI model")
    if client is None:
        if openai is None:
            raise RuntimeError(
                "The openai package is required for GPT-5.6 analysis"
            )
        client = openai.OpenAI(api_key=api_key)

    pages = report_pages or []
    framework_count = sum(
        bool(framework_requirements.get(framework))
        for framework in selected_frameworks
    )
    report_text_bytes = len(report_text.encode("utf-8"))
    vision_budget = min(
        18_000_000,
        180_000_000 // max(1, framework_count),
        max(0, 24_000_000 - report_text_bytes),
    )
    vision_blocks = build_openai_vision_blocks(
        pages, max_encoded_bytes=vision_budget
    )
    system_text = _system_prompt_text(report_text)
    prompt_cache_key = _openai_prompt_cache_key(report_text, pages)
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
            wrap_items=True,
        )
        prepared.append(
            {
                "framework": framework,
                "custom_id": _custom_id(index, framework),
                "expected": expected,
                "params": _openai_request_params(
                    model_id,
                    system_text,
                    prompt,
                    vision_blocks,
                    prompt_cache_key,
                ),
            }
        )

    for item in prepared:
        request_bytes = len(
            json.dumps(item["params"], ensure_ascii=False).encode("utf-8")
        )
        if request_bytes > 30_000_000 and vision_blocks:
            item["params"]["input"][0]["content"] = [
                item["params"]["input"][0]["content"][-1]
            ]
            request_bytes = len(
                json.dumps(item["params"], ensure_ascii=False).encode("utf-8")
            )
        if request_bytes > 30_000_000:
            raise ValueError(
                f"The {item['framework']} request is too large for the "
                "Responses API. Select a narrower PDF page range."
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
        "provider": "openai",
        "selected_model": model_id,
        "batch_api": bool(use_batch and prepared),
        "batch_id": None,
        "vision_pages": len(vision_blocks) // 2,
    }
    failures: list[dict[str, Any]] = []

    if use_batch and prepared:
        rows = [
            json.dumps(
                {
                    "custom_id": item["custom_id"],
                    "method": "POST",
                    "url": "/v1/responses",
                    "body": item["params"],
                },
                ensure_ascii=False,
            )
            for item in prepared
        ]
        jsonl_bytes = ("\n".join(rows) + "\n").encode("utf-8")
        if len(jsonl_bytes) > 190_000_000:
            if status_callback:
                status_callback(
                    "warning",
                    "The multimodal OpenAI batch would exceed the safe "
                    "input-file limit; using individual requests instead.",
                )
            batch = None
            failures = list(prepared)
            usage_total["batch_api"] = False
        elif existing_batch_id:
            batch = client.batches.retrieve(existing_batch_id)
        else:
            batch_file = BytesIO(jsonl_bytes)
            batch_file.name = "sustainability-analysis.jsonl"
            try:
                uploaded = client.files.create(file=batch_file, purpose="batch")
                batch = client.batches.create(
                    input_file_id=uploaded.id,
                    endpoint="/v1/responses",
                    completion_window="24h",
                )
            except Exception as error:
                if getattr(error, "status_code", None) != 413:
                    raise
                if status_callback:
                    status_callback(
                        "warning",
                        "OpenAI rejected the batch payload as too large; "
                        "using individual requests instead.",
                    )
                batch = None
                failures = list(prepared)
                usage_total["batch_api"] = False

        if batch is not None:
            usage_total["batch_id"] = batch.id
            if batch_id_callback:
                batch_id_callback(batch.id)
            if status_callback:
                action = "Resuming" if existing_batch_id else "Submitted"
                status_callback(
                    "info",
                    f"{action} OpenAI batch {batch.id}; waiting for "
                    f"{len(prepared)} framework results.",
                )

            terminal_statuses = {
                "completed",
                "failed",
                "expired",
                "cancelled",
                "canceled",
            }
            started = time.monotonic()
            while str(_get(batch, "status", "")) not in terminal_statuses:
                if time.monotonic() - started > max_batch_wait_seconds:
                    raise TimeoutError(
                        f"OpenAI Batch {batch.id} is still processing. "
                        "Resume it from the Report Analyser instead of submitting again."
                    )
                if poll_interval_seconds:
                    time.sleep(poll_interval_seconds)
                batch = client.batches.retrieve(batch.id)
                counts = _get(batch, "request_counts", {})
                completed = int(_get(counts, "completed", 0) or 0)
                failed = int(_get(counts, "failed", 0) or 0)
                if progress_callback:
                    progress_callback(
                        min(
                            0.95,
                            (completed + failed) / max(1, len(prepared)),
                        )
                    )

            by_id = {item["custom_id"]: item for item in prepared}
            seen_ids: set[str] = set()
            output_file_id = _get(batch, "output_file_id")
            if output_file_id:
                output_text = _openai_file_text(
                    client.files.content(output_file_id)
                )
                for line in output_text.splitlines():
                    if not line.strip():
                        continue
                    try:
                        batch_result = json.loads(line)
                    except json.JSONDecodeError:
                        # A corrupt line cannot be matched safely. Leave its
                        # request unseen so the missing-ID reconciliation below
                        # retries it synchronously with the selected model.
                        continue
                    custom_id = str(batch_result.get("custom_id", ""))
                    prepared_item = by_id.get(custom_id)
                    if not prepared_item or custom_id in seen_ids:
                        continue
                    seen_ids.add(custom_id)
                    response_wrapper = batch_result.get("response") or {}
                    status_code = int(response_wrapper.get("status_code", 0) or 0)
                    response = response_wrapper.get("body")
                    if not (200 <= status_code < 300) or not response:
                        failures.append(prepared_item)
                        continue
                    _add_usage(
                        usage_total,
                        response,
                        model_id,
                        provider="openai",
                        batch_priced=True,
                    )
                    try:
                        items = _validate_items(
                            _parse_openai_response(response),
                            prepared_item["expected"],
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

    for index, prepared_item in enumerate(failures):
        if status_callback and usage_total["batch_api"]:
            status_callback(
                "warning",
                f"Retrying {prepared_item['framework']} outside the batch "
                "after an incomplete batch result.",
            )
        response = _openai_sync_request(client, prepared_item["params"])
        _add_usage(
            usage_total,
            response,
            model_id,
            provider="openai",
        )
        try:
            items = _validate_items(
                _parse_openai_response(response),
                prepared_item["expected"],
            )
        except (ValueError, json.JSONDecodeError):
            framework = prepared_item["framework"]
            items = []
            topics = framework_requirements[framework]
            requirement_index = 1
            retry_vision_blocks = prepared_item["params"]["input"][0][
                "content"
            ][:-1]
            for topic, requirements in topics.items():
                topic_prompt, topic_expected = _build_prompt(
                    framework,
                    framework_full_names.get(framework, framework),
                    {topic: requirements},
                    requirement_refs,
                    start_index=requirement_index,
                    wrap_items=True,
                )
                requirement_index += len(requirements)
                topic_params = {
                    **prepared_item["params"],
                    "input": [
                        {
                            "role": "user",
                            "content": [
                                *retry_vision_blocks,
                                {"type": "input_text", "text": topic_prompt},
                            ],
                        }
                    ],
                }
                topic_response = _openai_sync_request(client, topic_params)
                _add_usage(
                    usage_total,
                    topic_response,
                    model_id,
                    provider="openai",
                )
                topic_items = _validate_items(
                    _parse_openai_response(topic_response),
                    topic_expected,
                )
                items.extend(
                    _normalise_items(framework, topic_items, topic_expected)
                )
        else:
            items = _normalise_items(
                prepared_item["framework"],
                items,
                prepared_item["expected"],
            )
        results.extend(items)
        if progress_callback and not use_batch:
            progress_callback((index + 1) / max(1, len(failures)))

    framework_summaries = _summarise_results(
        results, selected_frameworks, progress_callback
    )
    return results, framework_summaries, usage_total


def analyze_report(
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
    model_id: str = PRIMARY_MODEL,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, Any]]:
    """Route one analysis run to the explicitly selected model provider."""
    model = get_model_config(model_id)
    common = {
        "report_text": report_text,
        "selected_frameworks": selected_frameworks,
        "api_key": api_key,
        "framework_requirements": framework_requirements,
        "framework_full_names": framework_full_names,
        "requirement_refs": requirement_refs,
        "report_pages": report_pages,
        "use_batch": use_batch,
        "progress_callback": progress_callback,
        "status_callback": status_callback,
        "poll_interval_seconds": poll_interval_seconds,
        "max_batch_wait_seconds": max_batch_wait_seconds,
        "existing_batch_id": existing_batch_id,
        "batch_id_callback": batch_id_callback,
        "client": client,
        "model_id": model_id,
    }
    try:
        if model["provider"] == "anthropic":
            return _analyze_report_with_anthropic(**common)
        return _analyze_report_with_openai(**common)
    except Exception as error:
        auth_types = [anthropic.AuthenticationError]
        if openai is not None and hasattr(openai, "AuthenticationError"):
            auth_types.append(openai.AuthenticationError)
        if isinstance(error, tuple(auth_types)):
            raise AnalysisAuthenticationError(
                f"Invalid {model['provider'].title()} API key"
            ) from error
        raise


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
    """Backward-compatible Haiku entry point."""
    return analyze_report(
        report_text=report_text,
        selected_frameworks=selected_frameworks,
        api_key=api_key,
        framework_requirements=framework_requirements,
        framework_full_names=framework_full_names,
        requirement_refs=requirement_refs,
        report_pages=report_pages,
        use_batch=use_batch,
        progress_callback=progress_callback,
        status_callback=status_callback,
        poll_interval_seconds=poll_interval_seconds,
        max_batch_wait_seconds=max_batch_wait_seconds,
        existing_batch_id=existing_batch_id,
        batch_id_callback=batch_id_callback,
        client=client,
        model_id=PRIMARY_MODEL,
    )
