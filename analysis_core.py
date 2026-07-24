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


def _load_optional_anthropic() -> tuple[Any | None, ImportError | None]:
    """Load Anthropic without preventing OpenAI-only application startup."""
    try:
        import anthropic as anthropic_module
    except ImportError as error:
        # ImportError also covers dependency incompatibilities raised from
        # inside the SDK, not only a completely missing package.
        return None, error
    return anthropic_module, None


def _load_optional_openai() -> tuple[Any | None, ImportError | None]:
    """Load the optional OpenAI SDK without breaking Anthropic-only startup."""
    try:
        import openai as openai_module
    except ImportError as error:
        # ImportError also covers binary/dependency incompatibilities raised
        # from inside the SDK, not only a completely missing package.
        return None, error
    return openai_module, None


anthropic, _ANTHROPIC_IMPORT_ERROR = _load_optional_anthropic()
openai, _OPENAI_IMPORT_ERROR = _load_optional_openai()


def _anthropic_unavailable_message(purpose: str) -> str:
    """Return a safe operator-facing message for a missing/broken Anthropic SDK."""
    if _ANTHROPIC_IMPORT_ERROR is not None:
        return (
            f"The Anthropic SDK could not be loaded for {purpose}. Rebuild the "
            "application dependencies from requirements.txt."
        )
    return f"The anthropic package is required for {purpose}"


def _openai_unavailable_message(purpose: str) -> str:
    """Return a safe operator-facing message for a missing/broken OpenAI SDK."""
    if _OPENAI_IMPORT_ERROR is not None:
        return (
            f"The OpenAI SDK could not be loaded for {purpose}. Rebuild the "
            "application dependencies from requirements.txt."
        )
    return f"The openai package is required for {purpose}"


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
SONNET_MODEL = "claude-sonnet-5"
OPUS_MODEL = "claude-opus-5"
SOL_MODEL = "gpt-5.6-sol"
PRIMARY_MODEL = HAIKU_MODEL

# One catalogue drives the picker, request routing, and cost estimates. Prices
# are USD per million tokens and reflect first-party API list prices on
# 2026-07-24. Both providers apply a 50% Batch API discount. Sonnet 5 uses
# Anthropic's introductory pricing through 2026-08-31.
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
    SONNET_MODEL: {
        "label": "Claude Sonnet 5",
        "provider": "anthropic",
        "input_price": 2.0,
        "cached_input_price": 0.2,
        "cache_write_price": 2.5,
        "output_price": 10.0,
        "batch_input_price": 1.0,
        "batch_output_price": 5.0,
        "description": (
            "High-capability Claude model; introductory pricing through "
            "31 August 2026"
        ),
        "secret_name": "ANTHROPIC_API_KEY",
        "adaptive_thinking": True,
    },
    OPUS_MODEL: {
        "label": "Claude Opus 5",
        "provider": "anthropic",
        "input_price": 5.0,
        "cached_input_price": 0.5,
        "cache_write_price": 6.25,
        "output_price": 25.0,
        "batch_input_price": 2.5,
        "batch_output_price": 12.5,
        "description": "Frontier Opus model for demanding senior review",
        "secret_name": "ANTHROPIC_API_KEY",
        "adaptive_thinking": True,
    },
    SOL_MODEL: {
        "label": "GPT-5.6 Sol",
        "provider": "openai",
        "input_price": 5.0,
        "cached_input_price": 0.5,
        "cache_write_price": 6.25,
        "output_price": 30.0,
        "batch_input_price": 2.5,
        "batch_output_price": 15.0,
        "description": "Frontier GPT-5.6 model for complex senior review",
        "secret_name": "OPENAI_API_KEY",
        "long_context_threshold": 272_000,
        "long_input_multiplier": 2.0,
        "long_output_multiplier": 1.5,
    },
}
USER_SELECTABLE_MODELS = (HAIKU_MODEL, LUNA_MODEL, TERRA_MODEL)
ANALYST_MODELS = (HAIKU_MODEL, LUNA_MODEL)
REVIEWER_MODELS = (LUNA_MODEL, HAIKU_MODEL, TERRA_MODEL, SONNET_MODEL)
SENIOR_REVIEWER_MODELS = (
    TERRA_MODEL,
    SONNET_MODEL,
    OPUS_MODEL,
    SOL_MODEL,
)
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


def validate_review_cascade_roles(
    analyst_model_id: str,
    reviewer_model_id: str,
    senior_reviewer_model_id: str,
) -> None:
    """Validate role eligibility and adjacent-role separation."""
    role_rules = (
        ("Analyst", analyst_model_id, ANALYST_MODELS),
        ("Reviewer", reviewer_model_id, REVIEWER_MODELS),
        (
            "Senior reviewer",
            senior_reviewer_model_id,
            SENIOR_REVIEWER_MODELS,
        ),
    )
    for role, model_id, allowed_models in role_rules:
        if model_id not in allowed_models:
            raise ValueError(
                f"{get_model_config(model_id)['label']} cannot be used as "
                f"{role.lower()}."
            )
    if analyst_model_id == reviewer_model_id:
        raise ValueError("The analyst and reviewer must be different models.")
    if reviewer_model_id == senior_reviewer_model_id:
        raise ValueError(
            "The reviewer and senior reviewer must be different models."
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
    only_requirement_ids: set[str] | None = None,
    review_context: dict[str, Any] | None = None,
    review_instruction: str | None = None,
) -> tuple[str, dict[str, dict[str, str]]]:
    refs = requirement_refs or {}
    expected: dict[str, dict[str, str]] = {}
    scope_instruction = (
        f"Assess each supplied requirement of the {full_name} ({framework}) framework."
        if only_requirement_ids is not None
        else f"Assess every requirement of the {full_name} ({framework}) framework."
    )
    lines = [
        scope_instruction,
        "Use both the page-tagged text and the labelled PDF page images supplied before this instruction.",
        "",
    ]
    idx = start_index
    for topic, requirements in topics.items():
        for requirement in requirements:
            requirement_id = f"R{idx:04d}"
            reference = refs.get((framework, requirement), "")
            reference_tag = f" (Source: {reference})" if reference else ""
            if (
                only_requirement_ids is None
                or requirement_id in only_requirement_ids
            ):
                lines.append(
                    f"{requirement_id}. [{topic}]{reference_tag} {requirement}"
                )
                expected[requirement_id] = {
                    "topic": topic,
                    "reference": reference,
                    "requirement": requirement,
                }
            idx += 1

    if review_instruction:
        lines.extend(["", review_instruction])
    if review_context is not None:
        missing_context = set(expected) - set(review_context)
        if missing_context:
            raise ValueError(
                f"Missing review context for {framework}: "
                f"{sorted(missing_context)}"
            )
        lines.extend(
            [
                "",
                "PRIOR MODEL RECORDS BY REQUIREMENT ID:",
                "Use these records only as directed after your independent evidence assessment.",
            ]
        )
        for requirement_id in expected:
            lines.append(
                f"{requirement_id}: "
                f"{json.dumps(review_context[requirement_id], ensure_ascii=False, sort_keys=True)}"
            )

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
        except Exception as error:
            rate_limit_type = (
                getattr(anthropic, "RateLimitError", None)
                if anthropic is not None
                else None
            )
            if rate_limit_type is None or not isinstance(error, rate_limit_type):
                raise
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
    requirement_id_filters: dict[str, set[str]] | None = None,
    review_contexts: dict[str, dict[str, Any]] | None = None,
    review_instruction: str | None = None,
    usage_accumulator: dict[str, Any] | None = None,
    results_accumulator: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, Any]]:
    """Assess frameworks using Anthropic Messages or Message Batches."""
    model = get_model_config(model_id)
    if model["provider"] != "anthropic":
        raise ValueError(f"{model_id} is not an Anthropic model")
    if client is None:
        if anthropic is None:
            raise RuntimeError(
                _anthropic_unavailable_message("Anthropic analysis")
            )
        client = anthropic.Anthropic(api_key=api_key)
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
        requirement_filter = (
            requirement_id_filters.get(framework, set())
            if requirement_id_filters is not None
            else None
        )
        if requirement_id_filters is not None and not requirement_filter:
            continue
        prompt, expected = _build_prompt(
            framework,
            framework_full_names.get(framework, framework),
            topics,
            requirement_refs,
            only_requirement_ids=requirement_filter,
            review_context=(
                review_contexts.get(framework, {})
                if review_contexts is not None
                else None
            ),
            review_instruction=review_instruction,
        )
        if not expected:
            continue
        request_params = {
            "model": model_id,
            # Adaptive thinking shares this output budget with the required
            # JSON response, so newer Sonnet/Opus stages need more headroom.
            "max_tokens": 32768 if model.get("adaptive_thinking") else 16384,
            "system": system,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        *vision_blocks,
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        }
        if model.get("adaptive_thinking"):
            request_params["thinking"] = {"type": "adaptive"}
        prepared.append(
            {
                "framework": framework,
                "custom_id": _custom_id(index, framework),
                "expected": expected,
                "params": request_params,
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

    results = results_accumulator if results_accumulator is not None else []
    usage_total = usage_accumulator if usage_accumulator is not None else {}
    for key in (
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cache_write_tokens",
        "batch_input_tokens",
        "batch_output_tokens",
    ):
        usage_total.setdefault(key, 0)
    usage_total.setdefault("usage_records", [])
    usage_total.setdefault("models_used", set())
    usage_total.update(
        {
            "provider": "anthropic",
            "selected_model": model_id,
            "batch_api": bool(use_batch and prepared),
            "batch_id": None,
            "vision_pages": len(vision_blocks) // 2,
        }
    )
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
            except Exception as error:
                api_status_type = (
                    getattr(anthropic, "APIStatusError", None)
                    if anthropic is not None
                    else None
                )
                if (
                    api_status_type is None
                    or not isinstance(error, api_status_type)
                    or getattr(error, "status_code", None) != 413
                ):
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
            requirement_filter = (
                requirement_id_filters.get(framework, set())
                if requirement_id_filters is not None
                else None
            )
            framework_review_context = (
                review_contexts.get(framework, {})
                if review_contexts is not None
                else None
            )
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
                    only_requirement_ids=requirement_filter,
                    review_context=framework_review_context,
                    review_instruction=review_instruction,
                )
                requirement_index += len(requirements)
                if not topic_expected:
                    continue
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
    reasoning_effort: str = "medium",
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
        "reasoning": {"effort": reasoning_effort},
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
    requirement_id_filters: dict[str, set[str]] | None = None,
    review_contexts: dict[str, dict[str, Any]] | None = None,
    review_instruction: str | None = None,
    reasoning_effort: str = "medium",
    usage_accumulator: dict[str, Any] | None = None,
    results_accumulator: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, Any]]:
    """Assess frameworks using OpenAI Responses or the file-based Batch API."""
    model = get_model_config(model_id)
    if model["provider"] != "openai":
        raise ValueError(f"{model_id} is not an OpenAI model")
    if client is None:
        if openai is None:
            raise RuntimeError(_openai_unavailable_message("GPT-5.6 analysis"))
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
        requirement_filter = (
            requirement_id_filters.get(framework, set())
            if requirement_id_filters is not None
            else None
        )
        if requirement_id_filters is not None and not requirement_filter:
            continue
        prompt, expected = _build_prompt(
            framework,
            framework_full_names.get(framework, framework),
            topics,
            requirement_refs,
            wrap_items=True,
            only_requirement_ids=requirement_filter,
            review_context=(
                review_contexts.get(framework, {})
                if review_contexts is not None
                else None
            ),
            review_instruction=review_instruction,
        )
        if not expected:
            continue
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
                    reasoning_effort=reasoning_effort,
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

    results = results_accumulator if results_accumulator is not None else []
    usage_total = usage_accumulator if usage_accumulator is not None else {}
    for key in (
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cache_write_tokens",
        "batch_input_tokens",
        "batch_output_tokens",
    ):
        usage_total.setdefault(key, 0)
    usage_total.setdefault("usage_records", [])
    usage_total.setdefault("models_used", set())
    usage_total.update(
        {
            "provider": "openai",
            "selected_model": model_id,
            "batch_api": bool(use_batch and prepared),
            "batch_id": None,
            "vision_pages": len(vision_blocks) // 2,
        }
    )
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
            requirement_filter = (
                requirement_id_filters.get(framework, set())
                if requirement_id_filters is not None
                else None
            )
            framework_review_context = (
                review_contexts.get(framework, {})
                if review_contexts is not None
                else None
            )
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
                    only_requirement_ids=requirement_filter,
                    review_context=framework_review_context,
                    review_instruction=review_instruction,
                )
                requirement_index += len(requirements)
                if not topic_expected:
                    continue
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
        auth_types = []
        anthropic_auth_type = (
            getattr(anthropic, "AuthenticationError", None)
            if anthropic is not None
            else None
        )
        if isinstance(anthropic_auth_type, type):
            auth_types.append(anthropic_auth_type)
        if openai is not None and hasattr(openai, "AuthenticationError"):
            auth_types.append(openai.AuthenticationError)
        if auth_types and isinstance(error, tuple(auth_types)):
            raise AnalysisAuthenticationError(
                f"Invalid {model['provider'].title()} API key"
            ) from error
        raise


_CASCADE_VERDICT_FIELDS = (
    "classification",
    "confidence",
    "relevant_extracts",
    "confidence_reason",
    "rationale",
)
_CASCADE_STATUS_VALUES = (
    "analyst_reviewer_agree",
    "senior_reviewer_adjudicated",
    "three_way_disagreement",
    "reviewer_failed",
    "senior_reviewer_failed",
)
_CASCADE_PROVISIONAL_STATUSES = {
    "three_way_disagreement",
    "reviewer_failed",
    "senior_reviewer_failed",
}
_CASCADE_USAGE_KEYS = (
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "batch_input_tokens",
    "batch_output_tokens",
)


def _cascade_verdict_snapshot(result: dict[str, Any]) -> dict[str, Any]:
    """Return the evidence and verdict fields passed between cascade stages."""
    snapshot = {
        field: result.get(field, "")
        for field in _CASCADE_VERDICT_FIELDS
    }
    extracts = snapshot["relevant_extracts"]
    snapshot["relevant_extracts"] = (
        [str(extract) for extract in extracts]
        if isinstance(extracts, list)
        else []
    )
    return snapshot


def _index_cascade_results(
    results: Iterable[dict[str, Any]],
    stage: str,
) -> dict[tuple[str, str], dict[str, Any]]:
    """Index a stage by canonical identifiers and reject ambiguous joins."""
    indexed: dict[tuple[str, str], dict[str, Any]] = {}
    for result in results:
        key = (
            str(result.get("framework", "")),
            str(result.get("requirement_id", "")),
        )
        if key in indexed:
            raise ValueError(
                f"{stage} returned duplicate cascade result key {key!r}"
            )
        indexed[key] = result
    return indexed


def _cascade_review_contexts(
    indexed_results: dict[tuple[str, str], dict[str, Any]],
    model_name: str,
) -> dict[str, dict[str, Any]]:
    contexts: dict[str, dict[str, Any]] = {}
    for (framework, requirement_id), result in indexed_results.items():
        contexts.setdefault(framework, {})[requirement_id] = {
            model_name: _cascade_verdict_snapshot(result)
        }
    return contexts


def _aggregate_cascade_usage(
    stages: Iterable[tuple[str, dict[str, Any]]],
) -> dict[str, Any]:
    """Combine billed usage while retaining the stage behind every record."""
    aggregate: dict[str, Any] = {
        key: 0 for key in _CASCADE_USAGE_KEYS
    }
    aggregate.update(
        {
            "usage_records": [],
            "models_used": set(),
            "provider": "cascade",
            "selected_model": "review_cascade",
            "batch_api": False,
            "batch_id": None,
            "vision_pages": 0,
            "usage_by_stage": {},
        }
    )
    for stage, usage in stages:
        stage_summary = {
            key: int(usage.get(key, 0) or 0)
            for key in _CASCADE_USAGE_KEYS
        }
        stage_summary["models_used"] = sorted(usage.get("models_used", set()))
        aggregate["usage_by_stage"][stage] = stage_summary
        for key in _CASCADE_USAGE_KEYS:
            aggregate[key] += stage_summary[key]
        aggregate["models_used"].update(usage.get("models_used", set()))
        aggregate["vision_pages"] = max(
            aggregate["vision_pages"],
            int(usage.get("vision_pages", 0) or 0),
        )
        for record in usage.get("usage_records", []):
            aggregate["usage_records"].append(
                {**record, "cascade_stage": stage}
            )
    return aggregate


def _is_recoverable_cascade_stage_error(error: Exception) -> bool:
    """Return whether a provider/reconciliation failure can yield partial results."""
    recoverable: list[type[BaseException]] = [
        ValueError,
        TimeoutError,
        RuntimeError,
        ConnectionError,
    ]
    for error_name in (
        "APIConnectionError",
        "APITimeoutError",
        "RateLimitError",
        "InternalServerError",
    ):
        error_type = (
            getattr(anthropic, error_name, None)
            if anthropic is not None
            else None
        )
        if isinstance(error_type, type):
            recoverable.append(error_type)
    if openai is not None:
        for error_name in (
            "APIConnectionError",
            "APITimeoutError",
            "RateLimitError",
            "InternalServerError",
        ):
            error_type = getattr(openai, error_name, None)
            if isinstance(error_type, type):
                recoverable.append(error_type)
    return isinstance(error, tuple(recoverable))


def _summarise_cascade_results(
    results: list[dict[str, Any]],
    selected_frameworks: list[str],
    progress_callback: Callable[[float], None] | None,
) -> dict[str, dict[str, Any]]:
    """Summarise only resolved verdicts while retaining provisional counts."""
    summaries = _summarise_results(
        results,
        selected_frameworks,
        progress_callback,
    )
    for framework, summary in summaries.items():
        framework_results = [
            result
            for result in results
            if result["framework"] == framework
        ]
        resolved_results = [
            result
            for result in framework_results
            if result["cascade_status"] not in _CASCADE_PROVISIONAL_STATUSES
        ]
        counts = {classification: 0 for classification in ALL_CLASSIFICATIONS}
        for result in resolved_results:
            counts[result["classification"]] += 1
        summary["counts"] = counts
        summary["scored_total"] = len(resolved_results)
        summary["provisional"] = len(framework_results) - len(resolved_results)
        summary["avg_score"] = (
            sum(
                1.0
                if result["classification"] == CLASSIFICATION_COVERS
                else 0.5
                if result["classification"] == CLASSIFICATION_PARTLY
                else 0.0
                for result in resolved_results
            )
            / len(resolved_results)
            if resolved_results
            else 0.0
        )
        summary["cascade_status_counts"] = {
            status: sum(
                result["cascade_status"] == status
                for result in framework_results
            )
            for status in _CASCADE_STATUS_VALUES
        }
        summary["needs_human_review"] = sum(
            bool(result["needs_human_review"])
            for result in framework_results
        )
    return summaries


def _cascade_confidence_reason(
    *,
    status: str,
    analyst_result: dict[str, Any],
    analyst_label: str,
    reviewer_label: str,
    senior_label: str,
    reviewer_result: dict[str, Any] | None = None,
    senior_result: dict[str, Any] | None = None,
) -> str:
    """Explain deterministic confidence reconciliation without contradiction."""
    analyst_confidence = analyst_result.get("confidence", "low")
    if status == "reviewer_failed":
        return (
            f"{reviewer_label} review did not complete, so this "
            f"{analyst_label} verdict is provisional and requires human "
            f"review. {analyst_label} self-rated {analyst_confidence}: "
            f"{analyst_result.get('confidence_reason', '')}"
        ).strip()

    reviewer_result = reviewer_result or {}
    reviewer_confidence = reviewer_result.get("confidence", "low")
    if status == "analyst_reviewer_agree":
        return (
            f"{analyst_label} and {reviewer_label} agreed; final confidence "
            f"uses the lower of their self-ratings ({analyst_label}: "
            f"{analyst_confidence}; {reviewer_label}: "
            f"{reviewer_confidence}). {reviewer_label} review: "
            f"{reviewer_result.get('confidence_reason', '')}"
        ).strip()
    if status == "senior_reviewer_failed":
        return (
            f"{analyst_label} and {reviewer_label} disagreed and "
            f"{senior_label} review did not complete, so {reviewer_label}'s "
            "displayed verdict is provisional and requires human review. "
            f"{reviewer_label} self-rated {reviewer_confidence}: "
            f"{reviewer_result.get('confidence_reason', '')}"
        ).strip()

    senior_result = senior_result or {}
    senior_confidence = senior_result.get("confidence", "low")
    if status == "three_way_disagreement":
        return (
            f"{analyst_label}, {reviewer_label}, and {senior_label} assigned "
            "three different classifications; the displayed senior-reviewer "
            f"verdict is provisional and requires human review. {senior_label} "
            f"self-rated {senior_confidence}: "
            f"{senior_result.get('confidence_reason', '')}"
        ).strip()
    return (
        f"{analyst_label} and {reviewer_label} disagreed; {senior_label} "
        "adjudicated the result. Final confidence is capped at medium after "
        f"model disagreement ({senior_label} self-rated "
        f"{senior_confidence}). {senior_label}: "
        f"{senior_result.get('confidence_reason', '')}"
    ).strip()


def analyze_report_with_review_cascade(
    report_text: str,
    selected_frameworks: list[str],
    anthropic_api_key: str,
    openai_api_key: str,
    framework_requirements: dict[str, dict[str, list[str]]],
    framework_full_names: dict[str, str],
    requirement_refs: dict[tuple[str, str], str] | None = None,
    report_pages: list[dict[str, Any]] | None = None,
    progress_callback: Callable[[float], None] | None = None,
    status_callback: Callable[[str, str], None] | None = None,
    anthropic_client: Any | None = None,
    openai_client: Any | None = None,
    analyst_model_id: str = HAIKU_MODEL,
    reviewer_model_id: str = LUNA_MODEL,
    senior_reviewer_model_id: str = TERRA_MODEL,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, Any]]:
    """Run a configurable analyst, reviewer, and conditional senior reviewer.

    Standard requests are used because each stage depends on the one before it.
    The senior reviewer receives only requirements whose first two
    classifications differ.
    """
    validate_review_cascade_roles(
        analyst_model_id,
        reviewer_model_id,
        senior_reviewer_model_id,
    )
    role_models = {
        "analyst": analyst_model_id,
        "reviewer": reviewer_model_id,
        "senior_reviewer": senior_reviewer_model_id,
    }
    role_configs = {
        role: get_model_config(model_id)
        for role, model_id in role_models.items()
    }
    required_providers = {
        config["provider"] for config in role_configs.values()
    }
    if (
        "anthropic" in required_providers
        and (
            not isinstance(anthropic_api_key, str)
            or not anthropic_api_key.strip()
        )
    ):
        raise ValueError(
            "An Anthropic API key is required for the selected cascade roles."
        )
    if (
        "openai" in required_providers
        and (
            not isinstance(openai_api_key, str)
            or not openai_api_key.strip()
        )
    ):
        raise ValueError(
            "An OpenAI API key is required for the selected cascade roles."
        )

    # Resolve every required provider before the first billable request.
    resolved_anthropic = anthropic_client
    if "anthropic" in required_providers and resolved_anthropic is None:
        if anthropic is None:
            raise RuntimeError(
                _anthropic_unavailable_message("the review cascade")
            )
        resolved_anthropic = anthropic.Anthropic(api_key=anthropic_api_key)
    resolved_openai = openai_client
    if "openai" in required_providers and resolved_openai is None:
        if openai is None:
            raise RuntimeError(_openai_unavailable_message("the review cascade"))
        resolved_openai = openai.OpenAI(api_key=openai_api_key)

    analyst_label = role_configs["analyst"]["label"]
    reviewer_label = role_configs["reviewer"]["label"]
    senior_label = role_configs["senior_reviewer"]["label"]

    def stage_progress(start: float, span: float) -> Callable[[float], None] | None:
        if progress_callback is None:
            return None

        def update(value: float) -> None:
            progress_callback(start + span * min(1.0, max(0.0, value)))

        return update

    def run_stage(
        model_id: str,
        *,
        progress: Callable[[float], None] | None,
        requirement_filters: dict[str, set[str]] | None = None,
        review_contexts: dict[str, dict[str, Any]] | None = None,
        review_instruction: str | None = None,
        reasoning_effort: str = "medium",
        usage_accumulator: dict[str, Any] | None = None,
        results_accumulator: list[dict[str, Any]] | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, Any]]:
        config = get_model_config(model_id)
        common = {
            "report_text": report_text,
            "selected_frameworks": selected_frameworks,
            "api_key": (
                anthropic_api_key
                if config["provider"] == "anthropic"
                else openai_api_key
            ),
            "framework_requirements": framework_requirements,
            "framework_full_names": framework_full_names,
            "requirement_refs": requirement_refs,
            "report_pages": report_pages,
            "use_batch": False,
            "progress_callback": progress,
            "status_callback": status_callback,
            "client": (
                resolved_anthropic
                if config["provider"] == "anthropic"
                else resolved_openai
            ),
            "model_id": model_id,
            "requirement_id_filters": requirement_filters,
            "review_contexts": review_contexts,
            "review_instruction": review_instruction,
            "usage_accumulator": usage_accumulator,
            "results_accumulator": results_accumulator,
        }
        if config["provider"] == "anthropic":
            return _analyze_report_with_anthropic(**common)
        return _analyze_report_with_openai(
            **common,
            reasoning_effort=reasoning_effort,
        )

    try:
        # The Models API is a non-generation access check. Validate every
        # selected OpenAI role before generation starts when the key permits
        # that endpoint. Restricted keys can still allow Responses writes.
        selected_openai_models = tuple(
            dict.fromkeys(
                model_id
                for model_id in role_models.values()
                if get_model_config(model_id)["provider"] == "openai"
            )
        )
        models_api = getattr(resolved_openai, "models", None)
        retrieve_model = getattr(models_api, "retrieve", None)
        if selected_openai_models and callable(retrieve_model):
            if status_callback:
                status_callback(
                    "info",
                    "Checking OpenAI access to the selected cascade models "
                    "before analysis.",
                )
            for selected_openai_model in selected_openai_models:
                try:
                    retrieve_model(selected_openai_model)
                except Exception as error:
                    openai_auth_type = (
                        getattr(openai, "AuthenticationError", None)
                        if openai is not None
                        else None
                    )
                    if (
                        openai_auth_type is not None
                        and isinstance(error, openai_auth_type)
                    ):
                        raise AnalysisAuthenticationError(
                            "Invalid OpenAI API key"
                        ) from error
                    openai_not_found_type = (
                        getattr(openai, "NotFoundError", None)
                        if openai is not None
                        else None
                    )
                    if (
                        openai_not_found_type is not None
                        and isinstance(error, openai_not_found_type)
                    ):
                        raise RuntimeError(
                            "The OpenAI API key cannot access the required "
                            f"cascade model {selected_openai_model}."
                        ) from error
                    if status_callback:
                        status_callback(
                            "warning",
                            "Could not verify the selected models through the "
                            "OpenAI Models endpoint. Continuing because "
                            "restricted keys may still permit Responses calls; "
                            "the first applicable request will validate access.",
                        )
                    break

        if status_callback:
            status_callback(
                "info",
                f"Cascade stage 1/3: {analyst_label} is assessing every "
                "requirement.",
            )
        haiku_results, _, haiku_usage = run_stage(
            analyst_model_id,
            progress=stage_progress(0.0, 0.4),
        )
        haiku_index = _index_cascade_results(
            haiku_results, analyst_label
        )

        if status_callback:
            status_callback(
                "info",
                f"Cascade stage 2/3: {reviewer_label} is independently "
                f"reviewing every {analyst_label} verdict.",
            )
        luna_instruction = (
            "For each requirement, first assess the report evidence independently "
            "without relying on the prior verdict. Only after reaching an "
            f"independent view, audit the supplied {analyst_label} record and "
            "correct it if necessary. Return your own final verdict in the "
            "required schema."
        )
        luna_usage: dict[str, Any] = {}
        luna_results_buffer: list[dict[str, Any]] = []
        luna_stage_error: Exception | None = None
        try:
            run_stage(
                reviewer_model_id,
                progress=stage_progress(0.4, 0.4),
                review_contexts=_cascade_review_contexts(
                    haiku_index, "analyst"
                ),
                review_instruction=luna_instruction,
                reasoning_effort="medium",
                usage_accumulator=luna_usage,
                results_accumulator=luna_results_buffer,
            )
        except Exception as error:
            if not _is_recoverable_cascade_stage_error(error):
                raise
            luna_stage_error = error

        try:
            luna_index = _index_cascade_results(
                luna_results_buffer, reviewer_label
            )
        except ValueError as error:
            luna_stage_error = error
            luna_index = {}
        unexpected_luna_keys = set(luna_index) - set(haiku_index)
        if unexpected_luna_keys:
            luna_stage_error = ValueError(
                f"{reviewer_label} returned unexpected cascade requirement keys "
                f"{sorted(unexpected_luna_keys)}."
            )
            luna_index = {
                key: result
                for key, result in luna_index.items()
                if key in haiku_index
            }
        luna_failed_keys = set(haiku_index) - set(luna_index)
        if luna_failed_keys:
            luna_stage_error = luna_stage_error or ValueError(
                f"{reviewer_label} did not return every {analyst_label} "
                "cascade requirement key."
            )

        if luna_failed_keys:
            if status_callback:
                status_callback(
                    "warning",
                    f"{reviewer_label} review did not complete for "
                    f"{len(luna_failed_keys)} requirement(s). Successful "
                    f"{reviewer_label} reviews are retained; only missing "
                    "reviews are provisional.",
                )

        disagreement_keys = {
            key
            for key in luna_index
            if haiku_index[key]["classification"]
            != luna_index[key]["classification"]
        }
        terra_index: dict[tuple[str, str], dict[str, Any]] = {}
        terra_usage: dict[str, Any] | None = None
        terra_failed_keys: set[tuple[str, str]] = set()
        terra_stage_error: Exception | None = None
        if disagreement_keys:
            if status_callback:
                status_callback(
                    "info",
                    f"Cascade stage 3/3: {senior_label} is adjudicating only "
                    "the "
                    f"{len(disagreement_keys)} disputed verdict(s).",
                )
            terra_filters: dict[str, set[str]] = {}
            terra_contexts: dict[str, dict[str, Any]] = {}
            for framework, requirement_id in disagreement_keys:
                terra_filters.setdefault(framework, set()).add(requirement_id)
                terra_contexts.setdefault(framework, {})[requirement_id] = {
                    "analyst": _cascade_verdict_snapshot(
                        haiku_index[(framework, requirement_id)]
                    ),
                    "reviewer": _cascade_verdict_snapshot(
                        luna_index[(framework, requirement_id)]
                    ),
                }
            terra_instruction = (
                "For each supplied disputed requirement, first assess the report "
                "evidence independently without relying on either prior verdict. "
                f"Only after reaching an independent view, adjudicate the "
                f"{analyst_label} and {reviewer_label} disagreement and return "
                "your own final verdict in the required schema."
            )
            terra_usage = {}
            terra_results_buffer: list[dict[str, Any]] = []
            try:
                run_stage(
                    senior_reviewer_model_id,
                    progress=stage_progress(0.8, 0.2),
                    requirement_filters=terra_filters,
                    review_contexts=terra_contexts,
                    review_instruction=terra_instruction,
                    reasoning_effort="high",
                    usage_accumulator=terra_usage,
                    results_accumulator=terra_results_buffer,
                )
            except Exception as error:
                if not _is_recoverable_cascade_stage_error(error):
                    raise
                terra_stage_error = error

            try:
                terra_index = _index_cascade_results(
                    terra_results_buffer, senior_label
                )
            except ValueError as error:
                terra_stage_error = error
                terra_index = {}
            unexpected_terra_keys = set(terra_index) - disagreement_keys
            if unexpected_terra_keys:
                terra_stage_error = ValueError(
                    f"{senior_label} returned unexpected cascade requirement "
                    "keys "
                    f"{sorted(unexpected_terra_keys)}."
                )
                terra_index = {
                    key: result
                    for key, result in terra_index.items()
                    if key in disagreement_keys
                }
            terra_failed_keys = disagreement_keys - set(terra_index)
            if terra_failed_keys:
                terra_stage_error = terra_stage_error or ValueError(
                    f"{senior_label} did not return every disputed cascade "
                    "requirement key."
                )

            if terra_failed_keys:
                if status_callback:
                    status_callback(
                        "warning",
                        f"{senior_label} review did not complete for "
                        f"{len(terra_failed_keys)} disputed requirement(s). "
                        "Successful adjudications are retained; only missing "
                        "adjudications are provisional.",
                    )
        elif status_callback:
            status_callback(
                "info",
                f"{analyst_label} and {reviewer_label} agree on every "
                f"classification; {senior_label} was not called.",
            )

        confidence_rank = {"low": 0, "medium": 1, "high": 2}
        framework_order = {
            framework: index
            for index, framework in enumerate(selected_frameworks)
        }
        ordered_keys = sorted(
            haiku_index,
            key=lambda key: (
                framework_order.get(key[0], len(framework_order)),
                key[1],
            ),
        )
        final_results: list[dict[str, Any]] = []
        for key in ordered_keys:
            haiku_result = haiku_index[key]
            if key in luna_failed_keys:
                final_result = dict(haiku_result)
                cascade_status = "reviewer_failed"
                final_result["confidence"] = "low"
                final_result["confidence_reason"] = _cascade_confidence_reason(
                    status=cascade_status,
                    analyst_result=haiku_result,
                    analyst_label=analyst_label,
                    reviewer_label=reviewer_label,
                    senior_label=senior_label,
                )
                models_consulted = [analyst_model_id]
                needs_human_review = True
                verdicts = {
                    "analyst": _cascade_verdict_snapshot(haiku_result)
                }
                final_result.update(
                    {
                        "analysis_mode": "review_cascade",
                        "cascade_status": cascade_status,
                        "needs_human_review": needs_human_review,
                        "models_consulted": models_consulted,
                        "model_verdicts": verdicts,
                        "role_models": dict(role_models),
                    }
                )
                final_results.append(final_result)
                continue

            luna_result = luna_index[key]
            verdicts = {
                "analyst": _cascade_verdict_snapshot(haiku_result),
                "reviewer": _cascade_verdict_snapshot(luna_result),
            }
            if key not in disagreement_keys:
                final_result = dict(luna_result)
                final_result["confidence"] = min(
                    (
                        haiku_result["confidence"],
                        luna_result["confidence"],
                    ),
                    key=confidence_rank.__getitem__,
                )
                cascade_status = "analyst_reviewer_agree"
                final_result["confidence_reason"] = _cascade_confidence_reason(
                    status=cascade_status,
                    analyst_result=haiku_result,
                    analyst_label=analyst_label,
                    reviewer_label=reviewer_label,
                    senior_label=senior_label,
                    reviewer_result=luna_result,
                )
                models_consulted = [analyst_model_id, reviewer_model_id]
                needs_human_review = final_result["confidence"] == "low"
            elif key in terra_failed_keys:
                final_result = dict(luna_result)
                final_result["confidence"] = "low"
                cascade_status = "senior_reviewer_failed"
                final_result["confidence_reason"] = _cascade_confidence_reason(
                    status=cascade_status,
                    analyst_result=haiku_result,
                    analyst_label=analyst_label,
                    reviewer_label=reviewer_label,
                    senior_label=senior_label,
                    reviewer_result=luna_result,
                )
                models_consulted = [analyst_model_id, reviewer_model_id]
                needs_human_review = True
            else:
                terra_result = terra_index[key]
                verdicts["senior_reviewer"] = _cascade_verdict_snapshot(
                    terra_result
                )
                final_result = dict(terra_result)
                if final_result["confidence"] == "high":
                    final_result["confidence"] = "medium"
                prior_labels = {
                    haiku_result["classification"],
                    luna_result["classification"],
                }
                if terra_result["classification"] not in prior_labels:
                    cascade_status = "three_way_disagreement"
                    final_result["confidence"] = "low"
                    needs_human_review = True
                else:
                    cascade_status = "senior_reviewer_adjudicated"
                    needs_human_review = final_result["confidence"] == "low"
                final_result["confidence_reason"] = _cascade_confidence_reason(
                    status=cascade_status,
                    analyst_result=haiku_result,
                    analyst_label=analyst_label,
                    reviewer_label=reviewer_label,
                    senior_label=senior_label,
                    reviewer_result=luna_result,
                    senior_result=terra_result,
                )
                models_consulted = [
                    analyst_model_id,
                    reviewer_model_id,
                    senior_reviewer_model_id,
                ]

            final_result.update(
                {
                    "analysis_mode": "review_cascade",
                    "cascade_status": cascade_status,
                    "needs_human_review": needs_human_review,
                    "models_consulted": models_consulted,
                    "model_verdicts": verdicts,
                    "role_models": dict(role_models),
                }
            )
            final_results.append(final_result)

        summaries = _summarise_cascade_results(
            final_results,
            selected_frameworks,
            progress_callback,
        )

        stage_usage = [
            ("analyst", haiku_usage),
            ("reviewer", luna_usage),
        ]
        if terra_usage is not None:
            stage_usage.append(("senior_reviewer", terra_usage))
        usage = _aggregate_cascade_usage(stage_usage)
        failure_stages = []
        if luna_failed_keys:
            failure_stages.append("reviewer")
        if terra_failed_keys:
            failure_stages.append("senior_reviewer")
        usage.update(
            {
                "cascade_complete": not failure_stages,
                "cascade_failure_stage": (
                    failure_stages[0] if failure_stages else None
                ),
                "cascade_failure_stages": failure_stages,
                "role_models": dict(role_models),
            }
        )
        return final_results, summaries, usage
    except AnalysisAuthenticationError:
        raise
    except Exception as error:
        anthropic_auth_type = (
            getattr(anthropic, "AuthenticationError", None)
            if anthropic is not None
            else None
        )
        if (
            anthropic_auth_type is not None
            and isinstance(error, anthropic_auth_type)
        ):
            raise AnalysisAuthenticationError(
                "Invalid Anthropic API key"
            ) from error
        openai_auth_type = (
            getattr(openai, "AuthenticationError", None)
            if openai is not None
            else None
        )
        if openai_auth_type is not None and isinstance(error, openai_auth_type):
            raise AnalysisAuthenticationError(
                "Invalid OpenAI API key"
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
