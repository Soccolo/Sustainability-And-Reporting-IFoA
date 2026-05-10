"""
Sustainability Framework Analyser - Streamlit App
Deploy to Streamlit Cloud for free public access.

Uses Claude Haiku 4.5 API for intelligent report analysis
against sustainability framework requirements.

Requirements are loaded from ReportingFrameworks_v1.xlsx (in the project repo).
"""

import streamlit as st

# Force light theme without needing .streamlit/config.toml
st._config.set_option("theme.base", "light")
st._config.set_option("theme.primaryColor", "#ff4b4b")
st._config.set_option("theme.backgroundColor", "#ffffff")
st._config.set_option("theme.secondaryBackgroundColor", "#f5f5f5")
st._config.set_option("theme.textColor", "#1a1a1a")

import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import json
import anthropic
from io import BytesIO
from collections import defaultdict

# Page config
st.set_page_config(
    page_title="Sustainability Framework Analyser",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS — force light theme without breaking tabs, Plotly, or alert boxes
st.markdown("""
<style>
    /* ===== Global background ===== */
    .stApp {
        background-color: #ffffff;
        color: #1a1a1a;
    }
    .main .block-container {
        padding-top: 2rem;
        color: #1a1a1a;
    }

    /* ===== Typography — scoped to avoid Plotly / tab leaks ===== */
    h1, h2, h3, h4 {
        color: #1a1a1a !important;
    }
    .stMarkdown, .stMarkdown p, .stMarkdown span, .stMarkdown li,
    .stText, .stCaption, .stSubheader {
        color: #1a1a1a !important;
    }

    /* ===== Labels (checkbox, select, input, file uploader) ===== */
    .stCheckbox label, .stCheckbox label span,
    .stSelectbox label, .stTextInput label, .stTextArea label,
    .stFileUploader label, .stNumberInput label {
        color: #1a1a1a !important;
    }

    /* ===== Tabs ===== */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: #f0f0f0 !important;
        border-radius: 8px;
        padding: 10px 20px;
        color: #555555 !important;
    }
    /* Selected tab — higher specificity so it wins */
    .stTabs [data-baseweb="tab"][aria-selected="true"],
    .stTabs [data-baseweb="tab"][aria-selected="true"] * {
        background-color: #1a1a1a !important;
        color: #ffffff !important;
    }

    /* ===== Buttons ===== */
    .stButton > button {
        background-color: #f0f0f0 !important;
        color: #1a1a1a !important;
        border: 1px solid #d0d0d0 !important;
    }
    .stButton > button:hover {
        background-color: #e0e0e0 !important;
        border-color: #b0b0b0 !important;
    }
    .stButton > button[kind="primary"],
    .stButton > button[data-testid="stBaseButton-primary"] {
        background-color: #ff4b4b !important;
        color: #ffffff !important;
        border: none !important;
    }

    /* ===== Inputs (text, password, number, textarea) ===== */
    .stTextInput input, .stNumberInput input, .stTextArea textarea {
        background-color: #ffffff !important;
        color: #1a1a1a !important;
        border: 1px solid #d0d0d0 !important;
    }
    .stTextInput > div > div, .stNumberInput > div > div {
        background-color: #ffffff !important;
    }
    .stNumberInput button {
        background-color: #f0f0f0 !important;
        color: #1a1a1a !important;
        border-color: #d0d0d0 !important;
    }

    /* ===== Select boxes (dropdowns) ===== */
    [data-baseweb="select"] {
        background-color: #ffffff !important;
    }
    [data-baseweb="select"] > div {
        background-color: #ffffff !important;
        border-color: #d0d0d0 !important;
    }
    [data-baseweb="select"] span, [data-baseweb="select"] div {
        color: #1a1a1a !important;
    }
    /* Dropdown menu */
    [data-baseweb="popover"], [data-baseweb="menu"] {
        background-color: #ffffff !important;
    }
    [data-baseweb="popover"] li, [data-baseweb="menu"] li {
        color: #1a1a1a !important;
    }

    /* ===== File uploader ===== */
    .stFileUploader section {
        background-color: #f5f5f5 !important;
        border-color: #d0d0d0 !important;
    }
    .stFileUploader section span, .stFileUploader section small,
    .stFileUploader section div {
        color: #555555 !important;
    }
    .stFileUploader section button {
        background-color: #ffffff !important;
        color: #1a1a1a !important;
        border: 1px solid #d0d0d0 !important;
    }
    [data-testid="stFileUploaderDropzone"] {
        background-color: #f5f5f5 !important;
        border-color: #d0d0d0 !important;
    }
    [data-testid="stFileUploaderDropzone"] * {
        color: #555555 !important;
    }
    /* Uploaded file name */
    [data-testid="stFileUploaderFile"] span,
    [data-testid="stFileUploaderFile"] div {
        color: #1a1a1a !important;
    }

    /* ===== Expanders (Results) ===== */
    [data-testid="stExpander"] {
        background-color: #ffffff !important;
        border-color: #e0e0e0 !important;
    }
    [data-testid="stExpander"] summary,
    [data-testid="stExpander"] summary span,
    [data-testid="stExpander"] summary p {
        color: #1a1a1a !important;
    }

    /* ===== Alert boxes — inherit their own colours ===== */
    .stAlert, .stAlert p, .stAlert span {
        color: inherit !important;
    }

    /* ===== Plotly — do NOT override; let it manage its own text ===== */
    .js-plotly-plot, .js-plotly-plot * {
        /* no color override */
    }

    /* ===== Badge classes ===== */
    .framework-card {
        background-color: #f5f5f5;
        border-radius: 8px;
        padding: 1rem;
        margin: 0.5rem 0;
    }
    .badge-covers {
        background-color: #dcfce7; color: #166534 !important;
        padding: 4px 12px; border-radius: 12px; font-weight: 600; font-size: 13px;
    }
    .badge-partly {
        background-color: #fef3c7; color: #92400e !important;
        padding: 4px 12px; border-radius: 12px; font-weight: 600; font-size: 13px;
    }
    .badge-doesnt {
        background-color: #fee2e2; color: #991b1b !important;
        padding: 4px 12px; border-radius: 12px; font-weight: 600; font-size: 13px;
    }
</style>
""", unsafe_allow_html=True)

# ============================================
# DATA
# ============================================

FRAMEWORK_COLORS = {
    "TCFD": "#3b82f6",
    "TNFD": "#10b981",
    "PRA": "#f59e0b",
    "IFRS S1": "#ef4444",
    "IFRS S2": "#dc2626",
    "TPT": "#8b5cf6",
    "BMA": "#ec4899",
    "MAS": "#14b8a6",
    "ESRS E1": "#f97316",
    "ESRS E4": "#fb923c",
    "OSFI": "#06b6d4",
    "SBTi": "#a855f7",
    "PSI": "#64748b"
}

FRAMEWORK_FULL_NAMES = {
    "TCFD": "Task Force on Climate-related Financial Disclosures",
    "TNFD": "Taskforce on Nature-related Financial Disclosures",
    "PRA": "Prudential Regulation Authority",
    "IFRS S1": "IFRS S1 – General Requirements for Disclosure of Sustainability-related Financial Information",
    "IFRS S2": "IFRS S2 – Climate-related Disclosures",
    "TPT": "Transition Plan Taskforce",
    "BMA": "Bermuda Monetary Authority",
    "MAS": "Monetary Authority of Singapore",
    "ESRS E1": "European Sustainability Reporting Standards – Climate Change (E1)",
    "ESRS E4": "European Sustainability Reporting Standards – Biodiversity and Ecosystems (E4)",
    "OSFI": "Office of the Superintendent of Financial Institutions",
    "SBTi": "Science Based Targets initiative",
    "PSI": "Principles for Sustainable Insurance"
}

ADOPTION_DICT = {
    "TCFD": ["Canada", "France", "Germany", "Italy", "Japan", "United Kingdom", "USA", "New Zealand", "Switzerland", "Singapore", "Brazil", "China", "South Africa"],
    "TNFD": ["Brazil", "China", "Colombia", "Costa Rica", "Egypt", "India", "Indonesia", "Kenya", "Malaysia", "Mexico", "Morocco", "Nigeria", "Peru", "Philippines", "South Africa"],
    "PRA": ["United Kingdom"],
    "IFRS S1": ["Turkey", "Bangladesh", "Brazil", "Australia", "Japan", "United Kingdom", "Canada", "Singapore", "New Zealand", "Nigeria", "South Africa", "Malaysia", "China"],
    "IFRS S2": ["Turkey", "Bangladesh", "Brazil", "Australia", "Japan", "United Kingdom", "Canada", "Singapore", "New Zealand", "Nigeria", "South Africa", "Malaysia", "China"],
    "TPT": ["United Kingdom"],
    "BMA": ["Bermuda"],
    "MAS": ["Singapore"],
    "ESRS E1": ["Austria", "Belgium", "Bulgaria", "Croatia", "Cyprus", "Czech Republic", "Denmark", "Estonia", "Finland", "France", "Germany", "Greece", "Hungary", "Ireland", "Italy", "Latvia", "Lithuania", "Luxembourg", "Malta", "Netherlands", "Poland", "Portugal", "Romania", "Slovakia", "Slovenia", "Spain", "Sweden"],
    "ESRS E4": ["Austria", "Belgium", "Bulgaria", "Croatia", "Cyprus", "Czech Republic", "Denmark", "Estonia", "Finland", "France", "Germany", "Greece", "Hungary", "Ireland", "Italy", "Latvia", "Lithuania", "Luxembourg", "Malta", "Netherlands", "Poland", "Portugal", "Romania", "Slovakia", "Slovenia", "Spain", "Sweden"],
    "OSFI": ["Canada"],
    "SBTi": ["Japan", "United Kingdom", "USA", "China", "Germany", "France", "India", "Italy", "Canada", "South Korea", "Mexico", "Brazil", "Australia", "South Africa", "Turkey", "Romania", "Malta"],
    "PSI": ["Japan", "United Kingdom", "USA", "Germany", "France", "Brazil", "Australia", "South Africa", "China", "India", "Singapore", "Canada", "Switzerland", "Netherlands", "Sweden"]
}

COUNTRY_COORDS = {
    "Canada": {"lat": 56.13, "lon": -106.35},
    "USA": {"lat": 37.09, "lon": -95.71},
    "Mexico": {"lat": 23.63, "lon": -102.55},
    "Brazil": {"lat": -14.24, "lon": -51.93},
    "Colombia": {"lat": 4.57, "lon": -74.30},
    "Costa Rica": {"lat": 9.75, "lon": -83.75},
    "Peru": {"lat": -9.19, "lon": -75.02},
    "United Kingdom": {"lat": 55.38, "lon": -3.44},
    "France": {"lat": 46.23, "lon": 2.21},
    "Germany": {"lat": 51.17, "lon": 10.45},
    "Italy": {"lat": 41.87, "lon": 12.57},
    "Spain": {"lat": 40.46, "lon": -3.75},
    "Switzerland": {"lat": 46.82, "lon": 8.23},
    "Austria": {"lat": 47.52, "lon": 14.55},
    "Belgium": {"lat": 50.50, "lon": 4.47},
    "Netherlands": {"lat": 52.13, "lon": 5.29},
    "Poland": {"lat": 51.92, "lon": 19.15},
    "Sweden": {"lat": 60.13, "lon": 18.64},
    "Denmark": {"lat": 56.26, "lon": 9.50},
    "Finland": {"lat": 61.92, "lon": 25.75},
    "Greece": {"lat": 39.07, "lon": 21.82},
    "Portugal": {"lat": 39.40, "lon": -8.22},
    "Ireland": {"lat": 53.14, "lon": -7.69},
    "Bulgaria": {"lat": 42.73, "lon": 25.49},
    "Romania": {"lat": 45.94, "lon": 24.97},
    "Hungary": {"lat": 47.16, "lon": 19.50},
    "Czech Republic": {"lat": 49.82, "lon": 15.47},
    "Slovakia": {"lat": 48.67, "lon": 19.70},
    "Slovenia": {"lat": 46.15, "lon": 14.99},
    "Croatia": {"lat": 45.10, "lon": 15.20},
    "Estonia": {"lat": 58.60, "lon": 25.01},
    "Latvia": {"lat": 56.88, "lon": 24.60},
    "Lithuania": {"lat": 55.17, "lon": 23.88},
    "Cyprus": {"lat": 35.13, "lon": 33.43},
    "Malta": {"lat": 35.94, "lon": 14.38},
    "Luxembourg": {"lat": 49.82, "lon": 6.13},
    "Turkey": {"lat": 38.96, "lon": 35.24},
    "Egypt": {"lat": 26.82, "lon": 30.80},
    "Morocco": {"lat": 31.79, "lon": -7.09},
    "South Africa": {"lat": -30.56, "lon": 22.94},
    "Nigeria": {"lat": 9.08, "lon": 8.68},
    "Kenya": {"lat": -0.02, "lon": 37.91},
    "Japan": {"lat": 36.20, "lon": 138.25},
    "South Korea": {"lat": 35.91, "lon": 127.77},
    "China": {"lat": 35.86, "lon": 104.20},
    "India": {"lat": 20.59, "lon": 78.96},
    "Singapore": {"lat": 1.35, "lon": 103.82},
    "Malaysia": {"lat": 4.21, "lon": 101.98},
    "Indonesia": {"lat": -0.79, "lon": 113.92},
    "Philippines": {"lat": 12.88, "lon": 121.77},
    "Bangladesh": {"lat": 23.68, "lon": 90.36},
    "Australia": {"lat": -25.27, "lon": 133.78},
    "New Zealand": {"lat": -40.90, "lon": 174.89},
    "Bermuda": {"lat": 32.32, "lon": -64.76}
}

# Similarity data from the notebook
# NOTE: Similarity keys use the original framework names (TCFD, TNFD, PRA, IFRS, TPT, BMA, MAS, ESRS, OSFI, SBTi).
# For split frameworks (IFRS S1/S2, ESRS E1/E4), similarity lookups fall back to the parent name.
SIMILARITY_PARENT_MAP = {
    "IFRS S1": "IFRS", "IFRS S2": "IFRS",
    "ESRS E1": "ESRS", "ESRS E4": "ESRS",
}


# ============================================
# LOAD SIMILARITY DATA FROM CSV FILES
# ============================================

SIMILARITY_METRIC_TYPES = [
    "all_metrics", "governance", "strategy", "risk", "metrics", "disclosure"
]

@st.cache_data
def load_similarity_data():
    """
    Load similarity matrices from CSV files in the same directory as the app.
    Expects files named: similarity_network_table_{metric_type}.csv
    Each CSV should have columns: Framework 1, Framework 2, Similarity
    Returns a dict mapping metric_type -> DataFrame.
    """
    import os
    base_dir = os.path.dirname(os.path.abspath(__file__))
    data = {}

    for metric in SIMILARITY_METRIC_TYPES:
        filename = f"similarity_network_table_{metric}.csv"
        filepath = os.path.join(base_dir, filename)
        try:
            df = pd.read_csv(filepath)
            # Ensure expected columns exist
            if all(
                col in df.columns
                for col in ["Framework 1", "Framework 2", "Similarity"]
            ):
                data[metric] = df
            else:
                st.warning(
                    f"Similarity file {filename} missing expected columns. "
                    f"Found: {list(df.columns)}"
                )
        except FileNotFoundError:
            pass  # Metric type won't be available
        except Exception as e:
            st.warning(f"Could not load {filename}: {e}")

    return data



# ============================================
# LOAD FRAMEWORK REQUIREMENTS FROM EXCEL
# ============================================

@st.cache_data
def load_framework_requirements():
    """
    Load framework requirements from ReportingFrameworks_v1.xlsx.
    Returns a dict: { framework: { topic: [recommendation_1, ...] } }
    Recommendations are deduplicated per framework+topic.
    """
    import os

    # Try multiple paths: same directory as script, then common locations
    possible_paths = [
        os.path.join(os.path.dirname(__file__), "ReportingFrameworks_v1.xlsx"),
        "ReportingFrameworks_v1.xlsx",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "ReportingFrameworks_v1.xlsx"),
    ]

    df = None
    for path in possible_paths:
        if os.path.exists(path):
            df = pd.read_excel(path, engine="openpyxl")
            break

    if df is None:
        st.error(
            "Could not find ReportingFrameworks_v1.xlsx. "
            "Please ensure the file is in the same directory as this script."
        )
        return {}

    requirements = defaultdict(lambda: defaultdict(list))

    for _, row in df.iterrows():
        framework = row.get("Framework")
        topic = row.get("Topic")
        recommendation = row.get("Recommendation")

        if pd.isna(framework) or pd.isna(topic) or pd.isna(recommendation):
            continue

        framework = str(framework).strip()
        topic = str(topic).strip()
        recommendation = str(recommendation).strip()

        # Deduplicate
        if recommendation not in requirements[framework][topic]:
            requirements[framework][topic].append(recommendation)

    # Convert defaultdicts to regular dicts for caching
    return {fw: dict(topics) for fw, topics in requirements.items()}


# ============================================
# CLASSIFICATION HELPERS
# ============================================

CLASSIFICATION_COVERS = "Covers the framework"
CLASSIFICATION_PARTLY = "Partly covers the framework"
CLASSIFICATION_DOESNT = "Doesn't cover the framework"

ALL_CLASSIFICATIONS = [CLASSIFICATION_COVERS, CLASSIFICATION_PARTLY, CLASSIFICATION_DOESNT]

CLASSIFICATION_COLORS = {
    CLASSIFICATION_COVERS: "#16a34a",
    CLASSIFICATION_PARTLY: "#d97706",
    CLASSIFICATION_DOESNT: "#dc2626",
}

CLASSIFICATION_BADGES = {
    CLASSIFICATION_COVERS: "badge-covers",
    CLASSIFICATION_PARTLY: "badge-partly",
    CLASSIFICATION_DOESNT: "badge-doesnt",
}


def classification_to_score(classification):
    """Map classification to a numeric value for summary statistics."""
    if classification == CLASSIFICATION_COVERS:
        return 1.0
    elif classification == CLASSIFICATION_PARTLY:
        return 0.5
    else:
        return 0.0


# ============================================
# HELPER FUNCTIONS
# ============================================

def extract_text_from_pdf(pdf_file):
    """Extract text from PDF page by page using pymupdf"""
    import pymupdf

    pdf_bytes = pdf_file.read()
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")

    text_list = []
    for page_num, page in enumerate(doc):
        text = page.get_text()
        text_list.append(text.replace('\n', ' '))

    doc.close()
    return text_list


def claude_analyze_report(report_text, selected_frameworks, api_key, framework_requirements, progress_bar=None):
    """
    Use Claude to assess a report requirement-by-requirement.

    For each framework requirement, Claude:
    1. Searches the full report for all relevant passages
    2. Classifies how well the requirement is addressed:
       - "Covers the framework"
       - "Partly covers the framework"
       - "Doesn't cover the framework"
    3. Provides a rationale referencing the specific text found

    Model strategy:
    - Tries claude-haiku-4-5 first (cheapest: $1/$5 per MTok)
    - Falls back to claude-sonnet-4 if Haiku hits rate limits or input size limits
    - Once fallback is triggered, stays on Sonnet for remaining frameworks

    Cost optimisation:
    - Prompt caching: report text in system message is cached across calls
      (cache reads are 90% cheaper than fresh input)
    - One API call per framework batches all its requirements together
    """
    client = anthropic.Anthropic(api_key=api_key)

    # System message with report text - this gets cached across framework calls
    system_message = [
        {
            "type": "text",
            "text": (
                "You are an expert sustainability and ESG analyst.\n\n"
                "You will be given a set of regulatory framework requirements. For EACH requirement, "
                "you must:\n"
                "1. Search the ENTIRE report below for ALL passages that address that requirement. "
                "The relevant content may be spread across multiple sections.\n"
                "2. Extract short verbatim quotes from the report (max ~40 words each) that are "
                "most relevant to the requirement.\n"
                "3. Classify how well the requirement is addressed using EXACTLY one of these three labels:\n"
                '   - "Covers the framework" — the report comprehensively addresses this requirement '
                "with specific, concrete content and detail.\n"
                '   - "Partly covers the framework" — the report addresses some aspects of this '
                "requirement but is incomplete, vague, or lacks concrete detail.\n"
                '   - "Doesn\'t cover the framework" — the report does not meaningfully address '
                "this requirement.\n"
                "4. Write a rationale (2-3 sentences) explaining the classification, referencing what the "
                "report does or does not cover.\n\n"
                "Be rigorous. 'Covers the framework' requires specific, concrete content — not just vague "
                "mentions. If the report only partially addresses a requirement, classify it as "
                "'Partly covers the framework'.\n\n"
                "REPORT TEXT:\n"
                f"{report_text}"
            ),
            "cache_control": {"type": "ephemeral"}
        }
    ]

    results = []
    total_steps = len(selected_frameworks)
    input_tokens_total = 0
    output_tokens_total = 0
    cache_read_tokens_total = 0
    cache_write_tokens_total = 0
    models_used = set()  # Track which models were actually used

    # Model fallback order: try Haiku first (cheapest), fall back to Sonnet if rate-limited
    PRIMARY_MODEL = "claude-haiku-4-5-20251001"
    FALLBACK_MODEL = "claude-sonnet-4-20250514"
    use_fallback = False  # Once we switch, stay on Sonnet for remaining frameworks

    for step, framework in enumerate(selected_frameworks):
        if framework not in framework_requirements:
            continue

        topics = framework_requirements[framework]
        fw_full_name = FRAMEWORK_FULL_NAMES.get(framework, framework)

        # Build the requirements list for this framework
        requirements_text = (
            f"Assess the report against each requirement of the "
            f"**{fw_full_name} ({framework})** framework.\n\n"
            f"For each requirement below, find all relevant text in the report, "
            f"classify it, and explain your reasoning.\n\n"
        )

        req_index = 1
        for topic, reqs in topics.items():
            for req in reqs:
                requirements_text += f"{req_index}. [{topic}] {req}\n"
                req_index += 1

        requirements_text += (
            "\n\nRespond ONLY with a JSON array. Each element must have exactly these keys:\n"
            "{\n"
            ' "topic": "<topic name from the square brackets>",\n'
            ' "requirement": "<the requirement text>",\n'
            ' "relevant_extracts": ["<short verbatim quote 1 from report>", "<quote 2>", ...],\n'
            ' "classification": "<one of: Covers the framework | Partly covers the framework | Doesn\'t cover the framework>",\n'
            ' "rationale": "<2-3 sentence explanation referencing what the report covers or misses>"\n'
            "}\n\n"
            "If no relevant text exists for a requirement, set relevant_extracts to an empty array "
            "and classification to \"Doesn't cover the framework\".\n"
            "No markdown, no backticks, no preamble — just the raw JSON array."
        )

        # Determine which model to use
        model = FALLBACK_MODEL if use_fallback else PRIMARY_MODEL
        response = None

        try:
            response = client.messages.create(
                model=model,
                max_tokens=8192,
                system=system_message,
                messages=[{"role": "user", "content": requirements_text}]
            )
            models_used.add(model)

        except (anthropic.RateLimitError, anthropic.APIStatusError) as e:
            # If Haiku fails with rate limit or overload, try Sonnet
            if model == PRIMARY_MODEL:
                st.warning(
                    f"Haiku rate limit hit on {framework} — switching to Sonnet for remaining frameworks."
                )
                use_fallback = True
                try:
                    response = client.messages.create(
                        model=FALLBACK_MODEL,
                        max_tokens=8192,
                        system=system_message,
                        messages=[{"role": "user", "content": requirements_text}]
                    )
                    models_used.add(FALLBACK_MODEL)
                except anthropic.APIError as e2:
                    st.error(f"Sonnet also failed for {framework}: {e2}")
                    if progress_bar:
                        progress_bar.progress((step + 1) / total_steps)
                    continue
            else:
                st.error(f"API error for {framework}: {e}")
                if progress_bar:
                    progress_bar.progress((step + 1) / total_steps)
                continue

        except anthropic.APIError as e:
            st.error(f"API error for {framework}: {e}")
            if progress_bar:
                progress_bar.progress((step + 1) / total_steps)
            continue

        if response is None:
            if progress_bar:
                progress_bar.progress((step + 1) / total_steps)
            continue

        try:
            # Track token usage
            usage = response.usage
            input_tokens_total += usage.input_tokens
            output_tokens_total += usage.output_tokens
            cache_read_tokens_total += getattr(usage, 'cache_read_input_tokens', 0)
            cache_write_tokens_total += getattr(usage, 'cache_creation_input_tokens', 0)

            # Parse the JSON response
            raw_text = response.content[0].text.strip()
            # Clean up common formatting issues
            if raw_text.startswith("```"):
                raw_text = raw_text.split("\n", 1)[1] if "\n" in raw_text else raw_text[3:]
                if raw_text.endswith("```"):
                    raw_text = raw_text[:-3]
                raw_text = raw_text.strip()

            scored_items = json.loads(raw_text)

            for item in scored_items:
                # Normalise the classification string
                raw_class = item.get("classification", CLASSIFICATION_DOESNT).strip()
                # Match to canonical labels (fuzzy)
                if "covers" in raw_class.lower() and "partly" not in raw_class.lower() and "doesn" not in raw_class.lower():
                    classification = CLASSIFICATION_COVERS
                elif "partly" in raw_class.lower():
                    classification = CLASSIFICATION_PARTLY
                else:
                    classification = CLASSIFICATION_DOESNT

                results.append({
                    "framework": framework,
                    "topic": item["topic"],
                    "requirement": item.get("requirement", ""),
                    "relevant_extracts": item.get("relevant_extracts", []),
                    "classification": classification,
                    "rationale": item.get("rationale", "")
                })

        except json.JSONDecodeError as e:
            st.warning(f"Could not parse response for {framework}. Raw response saved for debugging.")
            st.code(raw_text[:500], language="json")

        if progress_bar:
            progress_bar.progress((step + 1) / total_steps)

    # Calculate framework-level coverage summaries
    framework_summaries = {}
    for framework in selected_frameworks:
        fw_results = [r for r in results if r["framework"] == framework]
        if fw_results:
            counts = {c: 0 for c in ALL_CLASSIFICATIONS}
            for r in fw_results:
                counts[r["classification"]] = counts.get(r["classification"], 0) + 1
            total = len(fw_results)
            avg_score = sum(classification_to_score(r["classification"]) for r in fw_results) / total
            framework_summaries[framework] = {
                "counts": counts,
                "total": total,
                "avg_score": avg_score,
            }

    # Token usage summary
    token_usage = {
        "input_tokens": input_tokens_total,
        "output_tokens": output_tokens_total,
        "cache_read_tokens": cache_read_tokens_total,
        "cache_write_tokens": cache_write_tokens_total,
        "models_used": models_used,
    }

    return results, framework_summaries, token_usage


def get_explanation(score):
    if score >= 0.5:
        return "Strong alignment - document comprehensively addresses this requirement"
    elif score >= 0.35:
        return "Good alignment - document covers key aspects of this requirement"
    elif score >= 0.25:
        return "Partial alignment - document touches on some aspects but could be more comprehensive"
    elif score >= 0.15:
        return "Weak alignment - limited coverage of this requirement"
    else:
        return "Minimal alignment - requirement not substantially addressed in document"


def get_score_color(score):
    if score >= 0.4:
        return "score-high"
    elif score >= 0.3:
        return "score-medium"
    elif score >= 0.2:
        return "score-low"
    else:
        return "score-verylow"


def get_similarity_for_framework(df, framework):
    """Get similarity scores for a specific framework.
    For split frameworks (e.g. IFRS S1), falls back to the parent name (IFRS) in similarity data.
    """
    lookup_name = SIMILARITY_PARENT_MAP.get(framework, framework)

    mask = (df['Framework 1'] == lookup_name) | (df['Framework 2'] == lookup_name)
    filtered = df[mask].copy()

    result = []
    for _, row in filtered.iterrows():
        other = row['Framework 2'] if row['Framework 1'] == lookup_name else row['Framework 1']
        result.append({
            'framework': other,
            'similarity': row['Similarity']
        })

    return sorted(result, key=lambda x: x['similarity'], reverse=True)


def generate_results_excel(results, framework_summaries):
    """Generate a formatted Excel workbook from analysis results."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    wb = Workbook()

    # --- Sheet 1: Summary ---
    ws_summary = wb.active
    ws_summary.title = "Summary"
    header_font = Font(bold=True, size=12, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="1a1a1a")
    green_fill = PatternFill("solid", fgColor="dcfce7")
    amber_fill = PatternFill("solid", fgColor="fef3c7")
    red_fill = PatternFill("solid", fgColor="fee2e2")
    thin_border = Border(
        left=Side(style="thin"), right=Side(style="thin"),
        top=Side(style="thin"), bottom=Side(style="thin"),
    )

    summary_headers = ["Framework", "Covers", "Partly Covers", "Doesn't Cover", "Total Requirements"]
    for col, h in enumerate(summary_headers, 1):
        cell = ws_summary.cell(row=1, column=col, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")
        cell.border = thin_border

    row = 2
    for fw, s in framework_summaries.items():
        counts = s.get("counts", {})
        ws_summary.cell(row=row, column=1, value=fw).border = thin_border
        c_cell = ws_summary.cell(row=row, column=2, value=counts.get(CLASSIFICATION_COVERS, 0))
        c_cell.fill = green_fill
        c_cell.border = thin_border
        p_cell = ws_summary.cell(row=row, column=3, value=counts.get(CLASSIFICATION_PARTLY, 0))
        p_cell.fill = amber_fill
        p_cell.border = thin_border
        d_cell = ws_summary.cell(row=row, column=4, value=counts.get(CLASSIFICATION_DOESNT, 0))
        d_cell.fill = red_fill
        d_cell.border = thin_border
        ws_summary.cell(row=row, column=5, value=s.get("total", 0)).border = thin_border
        row += 1

    for col_letter in ["A", "B", "C", "D", "E"]:
        ws_summary.column_dimensions[col_letter].width = 22

    # --- Sheet 2: Detailed Results ---
    ws_detail = wb.create_sheet("Detailed Results")
    detail_headers = ["Framework", "Topic", "Requirement", "Classification", "Rationale", "Relevant Extracts"]
    for col, h in enumerate(detail_headers, 1):
        cell = ws_detail.cell(row=1, column=col, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", wrap_text=True)
        cell.border = thin_border

    for i, r in enumerate(results, 2):
        ws_detail.cell(row=i, column=1, value=r["framework"]).border = thin_border
        ws_detail.cell(row=i, column=2, value=prettify_topic_name(r["topic"])).border = thin_border
        req_cell = ws_detail.cell(row=i, column=3, value=r["requirement"])
        req_cell.alignment = Alignment(wrap_text=True)
        req_cell.border = thin_border

        class_cell = ws_detail.cell(row=i, column=4, value=r["classification"])
        if r["classification"] == CLASSIFICATION_COVERS:
            class_cell.fill = green_fill
        elif r["classification"] == CLASSIFICATION_PARTLY:
            class_cell.fill = amber_fill
        else:
            class_cell.fill = red_fill
        class_cell.border = thin_border

        ws_detail.cell(row=i, column=5, value=r.get("rationale", "")).border = thin_border
        ws_detail.cell(
            row=i, column=6,
            value="; ".join(r.get("relevant_extracts", []))
        ).border = thin_border

    ws_detail.column_dimensions["A"].width = 14
    ws_detail.column_dimensions["B"].width = 18
    ws_detail.column_dimensions["C"].width = 50
    ws_detail.column_dimensions["D"].width = 26
    ws_detail.column_dimensions["E"].width = 50
    ws_detail.column_dimensions["F"].width = 50

    # --- Sheet 3: Gap Analysis ---
    ws_gap = wb.create_sheet("Gap Analysis")
    gap_headers = ["Framework", "Topic", "Requirement", "Classification", "Rationale"]
    for col, h in enumerate(gap_headers, 1):
        cell = ws_gap.cell(row=1, column=col, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", wrap_text=True)
        cell.border = thin_border

    gap_row = 2
    for r in results:
        if r["classification"] != CLASSIFICATION_COVERS:
            ws_gap.cell(row=gap_row, column=1, value=r["framework"]).border = thin_border
            ws_gap.cell(row=gap_row, column=2, value=prettify_topic_name(r["topic"])).border = thin_border
            ws_gap.cell(row=gap_row, column=3, value=r["requirement"]).border = thin_border
            class_cell = ws_gap.cell(row=gap_row, column=4, value=r["classification"])
            class_cell.fill = amber_fill if r["classification"] == CLASSIFICATION_PARTLY else red_fill
            class_cell.border = thin_border
            ws_gap.cell(row=gap_row, column=5, value=r.get("rationale", "")).border = thin_border
            gap_row += 1

    ws_gap.column_dimensions["A"].width = 14
    ws_gap.column_dimensions["B"].width = 18
    ws_gap.column_dimensions["C"].width = 50
    ws_gap.column_dimensions["D"].width = 26
    ws_gap.column_dimensions["E"].width = 50

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return output


def render_gap_analysis(results, framework_summaries):
    """Render a gap analysis summary — grouped by framework, showing only gaps."""
    gaps = [r for r in results if r["classification"] != CLASSIFICATION_COVERS]

    if not gaps:
        st.success("No gaps found — the report covers all analysed requirements.")
        return

    doesnt_count = sum(1 for r in gaps if r["classification"] == CLASSIFICATION_DOESNT)
    partly_count = sum(1 for r in gaps if r["classification"] == CLASSIFICATION_PARTLY)

    st.markdown(
        f'<div style="background:#fff7ed;border:1px solid #fed7aa;border-radius:8px;padding:16px;margin-bottom:16px;">'
        f'<h4 style="margin:0 0 8px 0;color:#9a3412;">Gap Analysis — What\'s Missing</h4>'
        f'<p style="margin:0;color:#333333;">'
        f'<span class="badge-doesnt">{doesnt_count} not covered</span>&nbsp;&nbsp;'
        f'<span class="badge-partly">{partly_count} partly covered</span>&nbsp;&nbsp;'
        f'— these requirements need attention.</p>'
        f'</div>',
        unsafe_allow_html=True
    )

    # Group by framework
    frameworks_in_gaps = []
    for r in gaps:
        if r["framework"] not in frameworks_in_gaps:
            frameworks_in_gaps.append(r["framework"])

    for fw in frameworks_in_gaps:
        fw_gaps = [r for r in gaps if r["framework"] == fw]
        doesnt = [r for r in fw_gaps if r["classification"] == CLASSIFICATION_DOESNT]
        partly = [r for r in fw_gaps if r["classification"] == CLASSIFICATION_PARTLY]

        with st.expander(f"**{fw}** — {len(doesnt)} not covered · {len(partly)} partly covered"):
            # Not covered first (most urgent)
            if doesnt:
                st.markdown("**Not covered** — action required:")
                for r in doesnt:
                    req_text = r["requirement"]
                    if len(req_text) > 200:
                        req_text = req_text[:200] + "…"
                    st.markdown(
                        f'<div style="background:#fee2e2;padding:10px;border-radius:6px;margin:6px 0;'
                        f'border-left:4px solid #dc2626;">'
                        f'<p style="margin:0 0 4px 0;font-size:13px;color:#1a1a1a;">'
                        f'<strong>[{prettify_topic_name(r["topic"])}]</strong> {req_text}</p>'
                        f'<p style="margin:0;font-size:12px;color:#555;">{r.get("rationale", "")}</p>'
                        f'</div>',
                        unsafe_allow_html=True
                    )

            if partly:
                st.markdown("**Partly covered** — could be strengthened:")
                for r in partly:
                    req_text = r["requirement"]
                    if len(req_text) > 200:
                        req_text = req_text[:200] + "…"
                    st.markdown(
                        f'<div style="background:#fef3c7;padding:10px;border-radius:6px;margin:6px 0;'
                        f'border-left:4px solid #d97706;">'
                        f'<p style="margin:0 0 4px 0;font-size:13px;color:#1a1a1a;">'
                        f'<strong>[{prettify_topic_name(r["topic"])}]</strong> {req_text}</p>'
                        f'<p style="margin:0;font-size:12px;color:#555;">{r.get("rationale", "")}</p>'
                        f'</div>',
                        unsafe_allow_html=True
                    )


def generate_comparison_excel(results_a, results_b, name_a, name_b, common_frameworks):
    """Generate an Excel workbook comparing two sets of results."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    wb = Workbook()
    ws = wb.active
    ws.title = "Comparison"

    header_font = Font(bold=True, size=11, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="1a1a1a")
    green_fill = PatternFill("solid", fgColor="dcfce7")
    amber_fill = PatternFill("solid", fgColor="fef3c7")
    red_fill = PatternFill("solid", fgColor="fee2e2")
    thin_border = Border(
        left=Side(style="thin"), right=Side(style="thin"),
        top=Side(style="thin"), bottom=Side(style="thin"),
    )

    headers = ["Framework", "Topic", "Requirement", f"{name_a}", f"{name_b}", "Difference"]
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", wrap_text=True)
        cell.border = thin_border

    # Build lookup for results_b
    b_lookup = {}
    for r in results_b:
        key = (r["framework"], r["topic"], r["requirement"][:100])
        b_lookup[key] = r

    row = 2
    for r_a in results_a:
        if r_a["framework"] not in common_frameworks:
            continue
        key = (r_a["framework"], r_a["topic"], r_a["requirement"][:100])
        r_b = b_lookup.get(key)

        ws.cell(row=row, column=1, value=r_a["framework"]).border = thin_border
        ws.cell(row=row, column=2, value=prettify_topic_name(r_a["topic"])).border = thin_border
        req_text = r_a["requirement"]
        if len(req_text) > 150:
            req_text = req_text[:150] + "…"
        ws.cell(row=row, column=3, value=req_text).border = thin_border

        cell_a = ws.cell(row=row, column=4, value=r_a["classification"])
        fill_map = {CLASSIFICATION_COVERS: green_fill, CLASSIFICATION_PARTLY: amber_fill, CLASSIFICATION_DOESNT: red_fill}
        cell_a.fill = fill_map.get(r_a["classification"], PatternFill())
        cell_a.border = thin_border

        if r_b:
            cell_b = ws.cell(row=row, column=5, value=r_b["classification"])
            cell_b.fill = fill_map.get(r_b["classification"], PatternFill())
            cell_b.border = thin_border

            # Difference
            score_a = classification_to_score(r_a["classification"])
            score_b = classification_to_score(r_b["classification"])
            if score_a > score_b:
                diff = f"{name_a} better"
            elif score_b > score_a:
                diff = f"{name_b} better"
            else:
                diff = "Same"
            ws.cell(row=row, column=6, value=diff).border = thin_border
        else:
            ws.cell(row=row, column=5, value="N/A").border = thin_border
            ws.cell(row=row, column=6, value="—").border = thin_border

        row += 1

    ws.column_dimensions["A"].width = 14
    ws.column_dimensions["B"].width = 18
    ws.column_dimensions["C"].width = 45
    ws.column_dimensions["D"].width = 26
    ws.column_dimensions["E"].width = 26
    ws.column_dimensions["F"].width = 18

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return output


# ============================================
# REQUIREMENT-LEVEL DIFF FOR SIMILARITY VIEW
# ============================================

def prettify_topic_name(name):
    """Insert spaces into concatenated topic names like 'RiskManagement' -> 'Risk Management'."""
    import re
    # Handle "and" between words first: "MetricsandTargets" -> "Metrics and Targets"
    spaced = re.sub(r'([a-z])(and)([A-Z])', r'\1 \2 \3', name)
    # Then insert space before uppercase letters that follow lowercase
    spaced = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', spaced)
    return spaced


def compute_requirement_diffs(fw_a, fw_b, framework_requirements):
    """
    Compare requirements between two frameworks for overlapping topics.
    Returns a list of dicts with topic, req_a, req_b, and diff HTML.
    """
    import difflib

    reqs_a = framework_requirements.get(fw_a, {})
    reqs_b = framework_requirements.get(fw_b, {})

    # Find overlapping topic names (case-insensitive match)
    topics_a = {t.lower(): t for t in reqs_a}
    topics_b = {t.lower(): t for t in reqs_b}
    common_topics = set(topics_a.keys()) & set(topics_b.keys())

    comparisons = []
    for topic_key in sorted(common_topics):
        topic_a = topics_a[topic_key]
        topic_b = topics_b[topic_key]
        list_a = reqs_a[topic_a]
        list_b = reqs_b[topic_b]

        # Pair requirements by position (zip to shorter list)
        for i in range(max(len(list_a), len(list_b))):
            req_a_text = list_a[i] if i < len(list_a) else None
            req_b_text = list_b[i] if i < len(list_b) else None
            comparisons.append({
                "topic": topic_a,
                "req_a": req_a_text,
                "req_b": req_b_text,
            })

    return comparisons


def render_diff_html(text_a, text_b):
    """Generate HTML showing word-level differences between two texts."""
    import difflib

    if text_a is None:
        return (
            '<span style="color:#888;font-style:italic;">'
            'No corresponding requirement</span>',
            f'<span>{text_b}</span>'
        )
    if text_b is None:
        return (
            f'<span>{text_a}</span>',
            '<span style="color:#888;font-style:italic;">'
            'No corresponding requirement</span>'
        )

    words_a = text_a.split()
    words_b = text_b.split()
    sm = difflib.SequenceMatcher(None, words_a, words_b)

    html_a_parts = []
    html_b_parts = []

    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == 'equal':
            html_a_parts.append(" ".join(words_a[i1:i2]))
            html_b_parts.append(" ".join(words_b[j1:j2]))
        elif op == 'replace':
            html_a_parts.append(
                f'<span style="background:#fecaca;padding:1px 3px;border-radius:3px;">'
                f'{" ".join(words_a[i1:i2])}</span>'
            )
            html_b_parts.append(
                f'<span style="background:#fecaca;padding:1px 3px;border-radius:3px;">'
                f'{" ".join(words_b[j1:j2])}</span>'
            )
        elif op == 'delete':
            html_a_parts.append(
                f'<span style="background:#fecaca;padding:1px 3px;border-radius:3px;">'
                f'{" ".join(words_a[i1:i2])}</span>'
            )
        elif op == 'insert':
            html_b_parts.append(
                f'<span style="background:#fecaca;padding:1px 3px;border-radius:3px;">'
                f'{" ".join(words_b[j1:j2])}</span>'
            )

    return " ".join(html_a_parts), " ".join(html_b_parts)


# ============================================
# MAIN APP
# ============================================


def main():
    st.title("Sustainability Framework Analyser")
    st.markdown("Compare & analyse ESG reporting frameworks")

    # Load requirements from Excel once
    framework_requirements = load_framework_requirements()

    # Load similarity CSVs
    similarity_data = load_similarity_data()

    tab0, tab1, tab2, tab3 = st.tabs([
        "Welcome", "Framework Map", "Report Analyser", "Side-by-Side Comparison"
    ])

    # ============================================
    # TAB 0: WELCOME / INTRODUCTION
    # ============================================
    with tab0:
        st.header("Welcome to the Sustainability Framework Analyser")
        st.markdown(
            "This tool was built by the **IFoA Sustainability and Reporting Working Party** "
            "to help actuaries and sustainability professionals navigate the growing landscape "
            "of climate and ESG reporting frameworks."
        )

        st.markdown("### What you can do")
        st.markdown(
            "**Framework Map** — Explore how sustainability frameworks are adopted globally. "
            "Select a framework to see which countries have adopted it, and compare its similarity "
            "to other frameworks across governance, strategy, risk, metrics, and disclosure dimensions."
        )
        st.markdown(
            "**Report Analyser** — Upload a transition plan or ESG report (PDF) and have it "
            "assessed requirement-by-requirement against the frameworks you choose. The tool uses "
            "Claude AI to classify each requirement as *Covered*, *Partly covered*, or *Not covered*, "
            "with rationale and relevant extracts from your document."
        )
        st.markdown(
            "**Side-by-Side Comparison** — Upload two reports to benchmark them against each other. "
            "Useful for comparing year-on-year progress or two firms' disclosures."
        )

        st.markdown("### How to use the Report Analyser")
        st.markdown(
            "1. Go to the **Report Analyser** tab.\n"
            "2. Select the frameworks you want to assess against.\n"
            "3. Upload your PDF and optionally select a page range.\n"
            "4. Click **Analyse Report** and wait for results.\n"
            "5. Review the detailed analysis, gap analysis, and download the Excel export."
        )

        st.markdown("---")
        st.markdown("### The Team")

        # ── Team profiles ──
        # Edit the list below to add/remove members.
        team_members = [
            {
                "name": "Lloyd Richards",
                "title": "Director & Head of Actuarial",
                "organisation": "Crowe UK",
                "linkedin_url": "https://www.linkedin.com/in/lloydrichards/",
                "bio": "Lead of the IFoA Sustainability and Reporting Working Party.",
            },
            {
                "name": "Cristian-Anton Calin",
                "title": "Pricing Actuary",
                "organisation": "Zurich Insurance",
                "linkedin_url": "https://linkedin.com/in/cristian-calin-b4969b1b2",
                "bio": "App Technical Developer.",
            },
            {
                "name": "Charchit Agrawal",
                "title": "Associate Director",
                "organisation": "BDO",
                "linkedin_url": "https://www.linkedin.com/in/charchit-agrawal-ba2a334/",
                "bio": "...",
            },
            {
                "name": "Diksha Thawani",
                "title": "Student Actuary",
                "organisation": "Zurich Kotak General Insurance",
                "linkedin_url": "https://www.linkedin.com/in/diksha-thawani/",
                "bio": "...",
            },
            {
                "name": "Ella Reid-Norris",
                "title": "Actuary, economist and strategist",
                "organisation": "Fair4All Finance",
                "linkedin_url": "https://www.linkedin.com/in/ella-reid-norris/",
                "bio": "...",
            },
            {
                "name": "Festus Cheruiyot",
                "title": "Actuarial Student",
                "organisation": "ACTEX Learning",
                "linkedin_url": "https://www.linkedin.com/in/festus-cheruiyot/",
                "bio": "...",
            },
            {
                "name": "Stephen Goh",
                "title": "Actuarial Consultant",
                "organisation": "Milliman UK",
                "linkedin_url": "https://www.linkedin.com/in/stephengoh/",
                "bio": "...",
            },
        ]

        cols_per_row = 3
        for row_start in range(0, len(team_members), cols_per_row):
            row_members = team_members[row_start:row_start + cols_per_row]
            profile_cols = st.columns(cols_per_row)
            for idx, member in enumerate(row_members):
                with profile_cols[idx]:
                    org_line = ""
                    if member["organisation"]:
                        org_line = (
                            '<p style="margin:0 0 8px 0;font-size:12px;'
                            f'color:#888;">{member["organisation"]}</p>'
                        )
                    st.markdown(
                        f'<div style="background:#f5f5f5;border:1px solid #e0e0e0;'
                        f'border-radius:10px;padding:20px;min-height:180px;">'
                        f'<p style="margin:0;font-size:17px;font-weight:700;'
                        f'color:#1a1a1a;">{member["name"]}</p>'
                        f'<p style="margin:2px 0 4px 0;font-size:13px;'
                        f'color:#d97706;font-weight:600;">{member["title"]}</p>'
                        f'{org_line}'
                        f'<p style="margin:0 0 10px 0;font-size:13px;'
                        f'color:#555;">{member["bio"]}</p>'
                        f'<a href="{member["linkedin_url"]}" target="_blank" '
                        f'style="font-size:13px;color:#2563eb;text-decoration:none;">'
                        f'LinkedIn &rarr;</a>'
                        f'</div>',
                        unsafe_allow_html=True
                    )

    # ============================================
    # TAB 1: FRAMEWORK MAP
    # ============================================
    with tab1:
        st.header("Climate & Sustainability Framework Adoption")
        st.markdown(
            "Explore global adoption and compare similarity between "
            "regulatory frameworks"
        )

        # --- Controls ---
        ctrl_col1, ctrl_col2, ctrl_col3 = st.columns([1, 1, 2])

        with ctrl_col1:
            framework_options = ["ALL"] + list(FRAMEWORK_COLORS.keys())
            selected_framework = st.selectbox(
                "Select Framework",
                options=framework_options,
                help=(
                    "Choose a framework to see its similarity to others, "
                    "or ALL for the full map"
                )
            )

        with ctrl_col2:
            available_metrics = (
                list(similarity_data.keys())
                if similarity_data
                else SIMILARITY_METRIC_TYPES
            )
            metric_type = st.selectbox(
                "Select Metric Type",
                options=available_metrics,
                format_func=lambda x: x.replace("_", " ").title(),
                help="Filter similarity scores by topic area"
            )

        # --- Main content: Similarity table (prominent) + Legend ---
        content_col, legend_col = st.columns([3, 1])

        with legend_col:
            st.markdown("#### Framework Legend")
            for fw, color in FRAMEWORK_COLORS.items():
                full_name = FRAMEWORK_FULL_NAMES.get(fw, fw)
                count = len(ADOPTION_DICT.get(fw, []))
                st.markdown(
                    f'<div style="display:flex;align-items:center;gap:8px;'
                    f'margin:4px 0;" title="{full_name}">'
                    f'<div style="width:14px;height:14px;background:{color};'
                    f'border-radius:3px;flex-shrink:0;"></div>'
                    f'<span style="color:#1a1a1a;font-size:13px;">{fw}</span>'
                    f'<span style="color:#888888;font-size:12px;">({count})</span>'
                    f'</div>',
                    unsafe_allow_html=True
                )

        with content_col:
            if selected_framework == "ALL":
                st.markdown(
                    '<div style="background:#f5f5f5;border:1px solid #e0e0e0;'
                    'border-radius:8px;padding:40px;text-align:center;'
                    'margin:16px 0;">'
                    '<p style="color:#555;font-size:15px;margin:0;">'
                    '&#x1F446; Select a framework from the dropdown above to '
                    'explore its similarity to other frameworks.</p>'
                    '</div>',
                    unsafe_allow_html=True
                )
            else:
                st.markdown(
                    f"#### Framework Similarity: {selected_framework}"
                )
                st.markdown(
                    f"*{FRAMEWORK_FULL_NAMES.get(selected_framework, selected_framework)}"
                    f" · Metric: {metric_type.replace('_', ' ').title()}*"
                )

                df_sim = similarity_data.get(metric_type)
                if df_sim is None:
                    st.info(
                        f"No similarity data available for "
                        f"{metric_type.replace('_', ' ').title()}. "
                        f"Check that the CSV file is present in the repository."
                    )
                    similarities = []
                else:
                    similarities = get_similarity_for_framework(
                        df_sim, selected_framework
                    )

                if similarities:
                    for item in similarities:
                        score = item['similarity']
                        pct = score * 100
                        other_fw = item['framework']
                        color = (
                            "#16a34a" if score >= 0.4
                            else "#2563eb" if score >= 0.3
                            else "#d97706" if score >= 0.2
                            else "#dc2626"
                        )
                        fw_color = FRAMEWORK_COLORS.get(other_fw, "#888888")
                        other_full = FRAMEWORK_FULL_NAMES.get(other_fw, other_fw)

                        st.markdown(
                            f'<div style="background:#f5f5f5;padding:12px;'
                            f'border-radius:8px;margin:8px 0;">'
                            f'<div style="display:flex;justify-content:space-between;'
                            f'align-items:center;">'
                            f'<div style="display:flex;align-items:center;gap:8px;">'
                            f'<div style="width:14px;height:14px;background:{fw_color};'
                            f'border-radius:3px;"></div>'
                            f'<span style="font-weight:600;color:#1a1a1a;" '
                            f'title="{other_full}">{other_fw}</span>'
                            f'</div>'
                            f'<span style="color:{color};font-weight:700;'
                            f'font-family:monospace;">{pct:.1f}%</span>'
                            f'</div>'
                            f'<div style="background:#e0e0e0;border-radius:4px;'
                            f'height:8px;margin-top:8px;overflow:hidden;">'
                            f'<div style="background:{color};height:100%;'
                            f'width:{pct}%;"></div>'
                            f'</div>'
                            f'</div>',
                            unsafe_allow_html=True
                        )

                        # Expandable requirement-level comparison
                        comparisons = compute_requirement_diffs(
                            selected_framework, other_fw, framework_requirements
                        )
                        if comparisons:
                            with st.expander(
                                f"View requirement-level comparison: "
                                f"{selected_framework} vs {other_fw} "
                                f"({len(comparisons)} requirement pairs)"
                            ):
                                current_topic = None
                                for comp in comparisons:
                                    if comp["topic"] != current_topic:
                                        current_topic = comp["topic"]
                                        st.markdown(f"**{prettify_topic_name(current_topic)}**")

                                    html_a, html_b = render_diff_html(
                                        comp["req_a"], comp["req_b"]
                                    )

                                    fw_sel_color = FRAMEWORK_COLORS.get(
                                        selected_framework, "#888"
                                    )
                                    st.markdown(
                                        f'<div style="display:flex;gap:12px;'
                                        f'margin:6px 0;font-size:12px;'
                                        f'line-height:1.5;">'
                                        f'<div style="flex:1;background:#f0f7ff;'
                                        f'padding:8px;border-radius:6px;'
                                        f'border-left:3px solid {fw_sel_color};">'
                                        f'<strong style="color:#1a1a1a;">'
                                        f'{selected_framework}</strong>'
                                        f'<br><span style="color:#333;">'
                                        f'{html_a}</span></div>'
                                        f'<div style="flex:1;background:#f0fff4;'
                                        f'padding:8px;border-radius:6px;'
                                        f'border-left:3px solid {fw_color};">'
                                        f'<strong style="color:#1a1a1a;">'
                                        f'{other_fw}</strong>'
                                        f'<br><span style="color:#333;">'
                                        f'{html_b}</span></div>'
                                        f'</div>',
                                        unsafe_allow_html=True
                                    )
                else:
                    st.info(
                        f"No similarity data available for "
                        f"{selected_framework} under "
                        f"{metric_type.replace('_', ' ').title()}"
                    )

        # --- Globe map below ---
        st.markdown("---")
        st.markdown("#### Global Adoption Map")

        map_data = []
        if selected_framework == "ALL":
            all_countries = set()
            for countries_list in ADOPTION_DICT.values():
                all_countries.update(countries_list)
            for country in all_countries:
                if country in COUNTRY_COORDS:
                    fws = [
                        fw for fw, ctrs in ADOPTION_DICT.items()
                        if country in ctrs
                    ]
                    map_data.append({
                        "country": country,
                        "lat": COUNTRY_COORDS[country]["lat"],
                        "lon": COUNTRY_COORDS[country]["lon"],
                        "frameworks": len(fws),
                        "framework_list": ", ".join(fws),
                        "size": 10 + len(fws) * 3
                    })
        else:
            for country in ADOPTION_DICT.get(selected_framework, []):
                if country in COUNTRY_COORDS:
                    map_data.append({
                        "country": country,
                        "lat": COUNTRY_COORDS[country]["lat"],
                        "lon": COUNTRY_COORDS[country]["lon"],
                        "frameworks": 1,
                        "framework_list": selected_framework,
                        "size": 15
                    })

        if map_data:
            df_map = pd.DataFrame(map_data)
            fig = px.scatter_geo(
                df_map, lat="lat", lon="lon",
                hover_name="country",
                hover_data={
                    "framework_list": True, "lat": False,
                    "lon": False, "frameworks": False, "size": False
                },
                size="size",
                color="frameworks" if selected_framework == "ALL" else None,
                color_continuous_scale=(
                    "Viridis" if selected_framework == "ALL" else None
                ),
                projection="orthographic"
            )

            if selected_framework != "ALL":
                fig.update_traces(marker=dict(
                    color=FRAMEWORK_COLORS.get(selected_framework, "#888")
                ))

            n_frames = 36
            frames = []
            for i in range(n_frames):
                lon_rot = -20 + (360 / n_frames) * i
                frames.append(go.Frame(
                    layout=dict(
                        geo=dict(projection_rotation=dict(lon=lon_rot, lat=15))
                    ),
                    name=str(i)
                ))
            fig.frames = frames

            fig.update_layout(
                geo=dict(
                    showland=True, landcolor="#d4e8d0",
                    showocean=True, oceancolor="#daeaf6",
                    showcoastlines=True, coastlinecolor="#aaaaaa",
                    showcountries=True, countrycolor="#cccccc",
                    showframe=False, bgcolor="#ffffff",
                    projection_rotation=dict(lon=-20, lat=15),
                ),
                paper_bgcolor="#ffffff", plot_bgcolor="#ffffff",
                font=dict(color="#1a1a1a"),
                margin=dict(l=0, r=0, t=0, b=0), height=500,
                updatemenus=[dict(
                    type="buttons", showactive=False,
                    x=0.02, y=0.02, xanchor="left", yanchor="bottom",
                    buttons=[
                        dict(
                            label="\u25b6 Spin", method="animate",
                            args=[None, dict(
                                frame=dict(duration=120, redraw=True),
                                fromcurrent=True,
                                transition=dict(duration=80),
                                mode="immediate",
                            )],
                        ),
                        dict(
                            label="\u23f8 Stop", method="animate",
                            args=[[None], dict(
                                frame=dict(duration=0, redraw=False),
                                mode="immediate",
                                transition=dict(duration=0),
                            )],
                        ),
                    ],
                )],
            )
            st.plotly_chart(fig, use_container_width=True)

    # ============================================
    # TAB 2: REPORT ANALYSER (single-column)
    # ============================================
    with tab2:
        st.header("ESG Report Analyser")
        st.markdown(
            "Upload your transition plan or ESG report PDF to analyse how "
            "well it aligns with sustainability frameworks. Uses "
            "**Claude Haiku 4.5** to classify your report "
            "requirement-by-requirement (falls back to **Sonnet 4** for "
            "large documents) \u2014 finding relevant text across the full "
            "document, classifying coverage, and providing a rationale "
            "for each."
        )

        # --- All controls on one row ---
        st.markdown("---")
        api_col, upload_col = st.columns([1, 1])

        with api_col:
            # Use Streamlit Secrets if configured, otherwise show input
            secrets_key = st.secrets.get("ANTHROPIC_API_KEY", "")
            if secrets_key:
                api_key = secrets_key
                st.markdown(
                    '<div style="background:#dcfce7;border:1px solid #bbf7d0;'
                    'border-radius:8px;padding:10px;font-size:13px;color:#166534;">'
                    '✓ API key configured</div>',
                    unsafe_allow_html=True
                )
            else:
                api_key = st.text_input(
                    "Anthropic API Key", type="password",
                    placeholder="sk-ant-...",
                    help=(
                        "Required for analysis. Your key is not stored. "
                        "Get one at console.anthropic.com"
                    )
                )

            st.markdown("**Select Frameworks**")
            available_frameworks = (
                list(framework_requirements.keys())
                if framework_requirements
                else list(FRAMEWORK_COLORS.keys())
            )

            btn_col1, btn_col2 = st.columns(2)
            with btn_col1:
                if st.button("Select All"):
                    st.session_state.selected_frameworks = (
                        available_frameworks.copy()
                    )
            with btn_col2:
                if st.button("Clear All"):
                    st.session_state.selected_frameworks = []

            if 'selected_frameworks' not in st.session_state:
                st.session_state.selected_frameworks = ["TCFD", "TNFD"]

            selected_frameworks = []
            fw_cols = st.columns(3)
            for i, fw in enumerate(available_frameworks):
                with fw_cols[i % 3]:
                    req_count = sum(
                        len(reqs)
                        for reqs in framework_requirements.get(fw, {}).values()
                    )
                    checked = st.checkbox(
                        f"{fw}",
                        value=fw in st.session_state.selected_frameworks,
                        key=f"fw_{fw}",
                        help=(
                            f"{FRAMEWORK_FULL_NAMES.get(fw, fw)} "
                            f"({req_count} requirements)"
                        )
                    )
                    if checked:
                        selected_frameworks.append(fw)

            st.session_state.selected_frameworks = selected_frameworks

            total_reqs = sum(
                sum(
                    len(reqs)
                    for reqs in framework_requirements.get(fw, {}).values()
                )
                for fw in selected_frameworks
            )
            st.markdown(
                f"**{len(selected_frameworks)}** framework(s) selected "
                f"\u00b7 **{total_reqs}** requirements"
            )
            if selected_frameworks:
                st.markdown(
                    f"*Estimated time: "
                    f"~{len(selected_frameworks) * 8} seconds "
                    f"(1 API call per framework)*"
                )

        with upload_col:
            st.markdown("**Upload Document**")
            uploaded_file = st.file_uploader(
                "Choose a PDF file", type="pdf",
                help="Upload your ESG report or transition plan PDF"
            )

            page_start = 1
            page_end = None
            if uploaded_file:
                import pymupdf
                pdf_bytes = uploaded_file.read()
                uploaded_file.seek(0)
                with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
                    total_pages = len(doc)

                st.markdown(
                    f"**PDF has {total_pages} pages.** "
                    f"Select the range to analyse:"
                )
                pr_col1, pr_col2 = st.columns(2)
                with pr_col1:
                    page_start = st.number_input(
                        "From page", min_value=1, max_value=total_pages,
                        value=1, step=1, key="page_start"
                    )
                with pr_col2:
                    page_end = st.number_input(
                        "To page", min_value=1, max_value=total_pages,
                        value=total_pages, step=1, key="page_end"
                    )
                if page_start > page_end:
                    st.warning("'From page' must be \u2264 'To page'.")

            st.markdown("**Or paste text:**")
            pasted_text = st.text_area(
                "Paste your report text here", height=120,
                placeholder="Paste your ESG report content..."
            )

        # Analyse button (full width)
        analyse_disabled = (
            (not uploaded_file and not pasted_text)
            or len(selected_frameworks) == 0
            or not api_key
        )

        if st.button(
            "Analyse Report", disabled=analyse_disabled, type="primary"
        ):
            if not api_key:
                st.error("Please enter your Anthropic API key")
            elif len(selected_frameworks) == 0:
                st.error("Please select at least one framework")
            elif not uploaded_file and not pasted_text:
                st.error("Please upload a PDF or paste text")
            else:
                if uploaded_file:
                    if page_end is not None and page_start > page_end:
                        st.error("'From page' must be \u2264 'To page'.")
                        st.stop()
                    with st.spinner("Extracting text from PDF..."):
                        try:
                            text_list = extract_text_from_pdf(uploaded_file)
                            total = len(text_list)
                            start_idx = max(0, page_start - 1)
                            end_idx = (
                                page_end if page_end is not None else total
                            )
                            text_list = text_list[start_idx:end_idx]
                            st.success(
                                f"Analysing pages {page_start}\u2013{end_idx} "
                                f"({len(text_list)} of {total} pages)"
                            )
                        except Exception as e:
                            st.error(f"Failed to extract PDF: {e}")
                            st.stop()
                else:
                    text_list = [
                        p.strip().replace('\n', ' ')
                        for p in pasted_text.split('\n\n') if p.strip()
                    ]
                    st.info(f"Processing {len(text_list)} paragraphs")

                report_text = "\n\n".join(text_list)

                st.markdown("### Analysing with Claude...")
                progress_bar = st.progress(0)

                try:
                    results, framework_summaries, token_usage = (
                        claude_analyze_report(
                            report_text, selected_frameworks,
                            api_key, framework_requirements, progress_bar
                        )
                    )
                    st.session_state.analysis_results = results
                    st.session_state.framework_summaries = (
                        framework_summaries
                    )
                    st.session_state.num_pages = len(text_list)
                    st.session_state.token_usage = token_usage
                    st.success("Analysis complete!")
                except anthropic.AuthenticationError:
                    st.error(
                        "Invalid API key. Please check your "
                        "Anthropic API key."
                    )
                except Exception as e:
                    st.error(f"Analysis failed: {e}")

        # --- Results (full width, below controls) ---
        st.markdown("---")

        if (
            'analysis_results' in st.session_state
            and st.session_state.analysis_results
        ):
            results = st.session_state.analysis_results
            framework_summaries = st.session_state.framework_summaries
            num_pages = st.session_state.num_pages
            token_usage = st.session_state.get('token_usage', {})

            total_results = len(results)
            covers_count = sum(
                1 for r in results
                if r['classification'] == CLASSIFICATION_COVERS
            )
            partly_count = sum(
                1 for r in results
                if r['classification'] == CLASSIFICATION_PARTLY
            )
            doesnt_count = sum(
                1 for r in results
                if r['classification'] == CLASSIFICATION_DOESNT
            )
            best_fw = (
                max(
                    framework_summaries.items(),
                    key=lambda x: x[1]['avg_score']
                )
                if framework_summaries else None
            )

            # Summary box
            summary_html = (
                '<div style="background:#f5f5f5;border:1px solid #e0e0e0;'
                'border-radius:8px;padding:16px;margin-bottom:16px;">'
                '<h4 style="margin:0 0 12px 0;color:#1a1a1a;">'
                'Analysis Summary</h4>'
                f'<p style="margin:0 0 8px 0;color:#333333;">'
                f'Analysed <strong>{num_pages}</strong> pages against '
                f'<strong>{len(framework_summaries)}</strong> frameworks '
                f'({total_results} requirements total).</p>'
                f'<div style="display:flex;gap:12px;flex-wrap:wrap;'
                f'margin:8px 0;">'
                f'<span class="badge-covers">{covers_count} Covered</span>'
                f'<span class="badge-partly">'
                f'{partly_count} Partly covered</span>'
                f'<span class="badge-doesnt">'
                f'{doesnt_count} Not covered</span>'
                '</div>'
            )
            if best_fw:
                summary_html += (
                    f'<p style="margin:8px 0 0 0;color:#333333;">'
                    f'Best alignment with '
                    f'<strong>{best_fw[0]}</strong>.</p>'
                )
            summary_html += '</div>'
            st.markdown(summary_html, unsafe_allow_html=True)

            # Cost estimate
            if token_usage:
                models_used = token_usage.get('models_used', set())
                used_sonnet = "claude-sonnet-4-20250514" in models_used
                used_haiku = "claude-haiku-4-5-20251001" in models_used

                if used_sonnet and used_haiku:
                    model_label = "Haiku 4.5 + Sonnet 4 (fallback)"
                    input_rate, output_rate = 3.0, 15.0
                elif used_sonnet:
                    model_label = "Sonnet 4 (fallback)"
                    input_rate, output_rate = 3.0, 15.0
                else:
                    model_label = "Haiku 4.5"
                    input_rate, output_rate = 1.0, 5.0

                input_cost = (
                    token_usage.get('input_tokens', 0)
                    / 1_000_000 * input_rate
                )
                output_cost = (
                    token_usage.get('output_tokens', 0)
                    / 1_000_000 * output_rate
                )
                cache_reads = token_usage.get('cache_read_tokens', 0)
                cache_savings = (
                    cache_reads / 1_000_000 * (input_rate * 0.9)
                )
                total_cost = input_cost + output_cost

                model_note = ""
                if used_sonnet and used_haiku:
                    model_note = (
                        "<br><em style='font-size:12px;color:#d97706;'>"
                        "\u26a0 Haiku hit rate limits \u2014 some frameworks "
                        "analysed with Sonnet. Cost shown is upper-bound "
                        "estimate.</em>"
                    )
                elif used_sonnet:
                    model_note = (
                        "<br><em style='font-size:12px;color:#d97706;'>"
                        "\u26a0 Haiku rate-limited \u2014 all frameworks "
                        "analysed with Sonnet.</em>"
                    )

                itok = token_usage.get("input_tokens", 0)
                otok = token_usage.get("output_tokens", 0)
                cache_str = (
                    f" \u00b7 Cache saved ~${cache_savings:.4f}"
                    if cache_reads > 0 else ""
                )
                st.markdown(
                    f'<div style="background:#f5f5f5;border:1px solid '
                    f'#e0e0e0;border-radius:8px;padding:12px;'
                    f'margin-bottom:16px;font-size:13px;color:#333333;">'
                    f'<strong>Model:</strong> {model_label} \u00b7 '
                    f'<strong>Estimated cost:</strong> ${total_cost:.4f} '
                    f'({itok:,} input / {otok:,} output tokens)'
                    f'{cache_str}{model_note}'
                    f'</div>',
                    unsafe_allow_html=True
                )

            # Export button
            excel_data = generate_results_excel(results, framework_summaries)
            st.download_button(
                label="\U0001f4e5 Download Results as Excel",
                data=excel_data,
                file_name="framework_analysis_results.xlsx",
                mime=(
                    "application/vnd.openxmlformats-officedocument"
                    ".spreadsheetml.sheet"
                ),
            )

            # == DETAILED ANALYSIS (first) ==
            st.markdown("---")
            st.subheader(
                "Detailed Analysis \u2014 How does your report perform "
                "against selected frameworks?"
            )

            for framework in st.session_state.selected_frameworks:
                fw_results = [
                    r for r in results if r['framework'] == framework
                ]
                if not fw_results:
                    continue

                summary = framework_summaries.get(framework, {})
                counts = summary.get("counts", {})
                c_count = counts.get(CLASSIFICATION_COVERS, 0)
                p_count = counts.get(CLASSIFICATION_PARTLY, 0)
                d_count = counts.get(CLASSIFICATION_DOESNT, 0)

                with st.expander(
                    f"**{framework}** \u2014 {c_count} covered \u00b7 "
                    f"{p_count} partly \u00b7 {d_count} not covered",
                    expanded=True
                ):
                    topics_seen = []
                    for r in fw_results:
                        if r["topic"] not in topics_seen:
                            topics_seen.append(r["topic"])

                    for topic in topics_seen:
                        topic_results = [
                            r for r in fw_results if r["topic"] == topic
                        ]
                        st.markdown(f"**{prettify_topic_name(topic)}**")

                        for r in topic_results:
                            classification = r['classification']
                            clr = CLASSIFICATION_COLORS.get(
                                classification, "#888"
                            )
                            badge_class = CLASSIFICATION_BADGES.get(
                                classification, "badge-doesnt"
                            )

                            extracts = r.get("relevant_extracts", [])
                            if extracts:
                                extracts_html = "".join(
                                    f'<div style="background:#fafafa;'
                                    f'border-left:3px solid {clr};'
                                    f'padding:6px 10px;margin:4px 0;'
                                    f'border-radius:0 4px 4px 0;'
                                    f'font-size:12px;color:#555555;'
                                    f'font-style:italic;">'
                                    f'"{ext}"</div>'
                                    for ext in extracts
                                )
                                extracts_section = (
                                    '<p style="margin:8px 0 4px 0;'
                                    'font-size:11px;color:#888888;'
                                    'text-transform:uppercase;'
                                    'letter-spacing:0.5px;">'
                                    'Relevant text found:</p>'
                                    f'{extracts_html}'
                                )
                            else:
                                extracts_section = (
                                    '<p style="margin:8px 0 4px 0;'
                                    'font-size:12px;color:#dc2626;'
                                    'font-style:italic;">'
                                    'No relevant text found in report</p>'
                                )

                            req_text = r.get("requirement", "")
                            if len(req_text) > 200:
                                req_text = req_text[:200] + "\u2026"

                            st.markdown(
                                f'<div style="background:#f5f5f5;'
                                f'padding:12px;border-radius:8px;'
                                f'margin:8px 0;border-left:4px solid '
                                f'{clr};">'
                                f'<div style="display:flex;'
                                f'justify-content:space-between;'
                                f'align-items:flex-start;gap:12px;">'
                                f'<span style="font-size:13px;'
                                f'color:#1a1a1a;flex:1;">'
                                f'{req_text}</span>'
                                f'<span class="{badge_class}" '
                                f'style="white-space:nowrap;">'
                                f'{classification}</span>'
                                f'</div>'
                                f'{extracts_section}'
                                f'<p style="margin:8px 0 0 0;'
                                f'font-size:12px;color:#222222;">'
                                f'<strong>Rationale:</strong> '
                                f'{r.get("rationale", "")}</p>'
                                f'</div>',
                                unsafe_allow_html=True
                            )

            # == GAP ANALYSIS (second) ==
            st.markdown("---")
            render_gap_analysis(results, framework_summaries)

        else:
            st.info(
                "Upload a document and click 'Analyse Report' "
                "to see results"
            )

    # ============================================
    # TAB 3: SIDE-BY-SIDE COMPARISON
    # ============================================
    with tab3:
        st.header("Side-by-Side Report Comparison")
        st.markdown(
            "Upload two ESG reports to compare how each covers the same "
            "framework requirements. Useful for benchmarking year-on-year "
            "progress or comparing two firms' disclosures."
        )

        # Use Streamlit Secrets if configured, otherwise show input
        secrets_key = st.secrets.get("ANTHROPIC_API_KEY", "")
        if secrets_key:
            cmp_api_key = secrets_key
            st.markdown(
                '<div style="background:#dcfce7;border:1px solid #bbf7d0;'
                'border-radius:8px;padding:10px;font-size:13px;color:#166534;">'
                '✓ API key configured</div>',
                unsafe_allow_html=True
            )
        else:
            cmp_api_key = st.text_input(
                "Anthropic API Key", type="password",
                placeholder="sk-ant-...",
                help="Required for analysis. Your key is not stored.",
                key="cmp_api_key"
            )

        available_frameworks = (
            list(framework_requirements.keys())
            if framework_requirements
            else list(FRAMEWORK_COLORS.keys())
        )

        st.subheader("Select Frameworks to Compare")

        cmp_col_sel1, cmp_col_sel2 = st.columns(2)
        with cmp_col_sel1:
            if st.button("Select All", key="cmp_select_all"):
                st.session_state.cmp_selected_frameworks = (
                    available_frameworks.copy()
                )
        with cmp_col_sel2:
            if st.button("Clear All", key="cmp_clear_all"):
                st.session_state.cmp_selected_frameworks = []

        if 'cmp_selected_frameworks' not in st.session_state:
            st.session_state.cmp_selected_frameworks = ["TCFD", "TNFD"]

        cmp_selected = []
        cmp_cols = st.columns(3)
        for i, fw in enumerate(available_frameworks):
            with cmp_cols[i % 3]:
                req_count = sum(
                    len(reqs)
                    for reqs in framework_requirements.get(fw, {}).values()
                )
                checked = st.checkbox(
                    f"{fw}",
                    value=fw in st.session_state.cmp_selected_frameworks,
                    key=f"cmp_fw_{fw}",
                    help=(
                        f"{FRAMEWORK_FULL_NAMES.get(fw, fw)} "
                        f"({req_count} requirements)"
                    )
                )
                if checked:
                    cmp_selected.append(fw)
        st.session_state.cmp_selected_frameworks = cmp_selected

        cmp_total_reqs = sum(
            sum(
                len(reqs)
                for reqs in framework_requirements.get(fw, {}).values()
            )
            for fw in cmp_selected
        )
        st.markdown(
            f"**{len(cmp_selected)}** framework(s) \u00b7 "
            f"**{cmp_total_reqs}** requirements each"
        )

        # Two-column upload
        st.subheader("Upload Two Reports")
        up_col1, up_col2 = st.columns(2)

        with up_col1:
            st.markdown("**Report A**")
            cmp_name_a = st.text_input(
                "Label for Report A", value="Report A", key="cmp_name_a"
            )
            cmp_file_a = st.file_uploader(
                "Upload PDF", type="pdf", key="cmp_file_a"
            )
            cmp_page_start_a, cmp_page_end_a = 1, None
            if cmp_file_a:
                import pymupdf
                bytes_a = cmp_file_a.read()
                cmp_file_a.seek(0)
                with pymupdf.open(stream=bytes_a, filetype="pdf") as doc:
                    total_a = len(doc)
                st.markdown(f"*{total_a} pages*")
                pa_c1, pa_c2 = st.columns(2)
                with pa_c1:
                    cmp_page_start_a = st.number_input(
                        "From page", 1, total_a, 1, key="cmp_ps_a"
                    )
                with pa_c2:
                    cmp_page_end_a = st.number_input(
                        "To page", 1, total_a, total_a, key="cmp_pe_a"
                    )

        with up_col2:
            st.markdown("**Report B**")
            cmp_name_b = st.text_input(
                "Label for Report B", value="Report B", key="cmp_name_b"
            )
            cmp_file_b = st.file_uploader(
                "Upload PDF", type="pdf", key="cmp_file_b"
            )
            cmp_page_start_b, cmp_page_end_b = 1, None
            if cmp_file_b:
                import pymupdf
                bytes_b = cmp_file_b.read()
                cmp_file_b.seek(0)
                with pymupdf.open(stream=bytes_b, filetype="pdf") as doc:
                    total_b = len(doc)
                st.markdown(f"*{total_b} pages*")
                pb_c1, pb_c2 = st.columns(2)
                with pb_c1:
                    cmp_page_start_b = st.number_input(
                        "From page", 1, total_b, 1, key="cmp_ps_b"
                    )
                with pb_c2:
                    cmp_page_end_b = st.number_input(
                        "To page", 1, total_b, total_b, key="cmp_pe_b"
                    )

        cmp_disabled = (
            (not cmp_file_a or not cmp_file_b)
            or len(cmp_selected) == 0
            or not cmp_api_key
        )
        if st.button(
            "Compare Reports", disabled=cmp_disabled,
            type="primary", key="cmp_run"
        ):
            if not cmp_api_key:
                st.error("Please enter your Anthropic API key")
            elif not cmp_file_a or not cmp_file_b:
                st.error("Please upload both PDFs")
            elif len(cmp_selected) == 0:
                st.error("Please select at least one framework")
            else:
                with st.spinner(f"Extracting text from {cmp_name_a}..."):
                    text_a = extract_text_from_pdf(cmp_file_a)
                    start_a = max(0, cmp_page_start_a - 1)
                    end_a = (
                        cmp_page_end_a
                        if cmp_page_end_a else len(text_a)
                    )
                    text_a = text_a[start_a:end_a]

                with st.spinner(f"Extracting text from {cmp_name_b}..."):
                    text_b = extract_text_from_pdf(cmp_file_b)
                    start_b = max(0, cmp_page_start_b - 1)
                    end_b = (
                        cmp_page_end_b
                        if cmp_page_end_b else len(text_b)
                    )
                    text_b = text_b[start_b:end_b]

                report_a = "\n\n".join(text_a)
                report_b = "\n\n".join(text_b)

                st.markdown(f"### Analysing {cmp_name_a}...")
                progress_a = st.progress(0)
                try:
                    results_a, summaries_a, usage_a = (
                        claude_analyze_report(
                            report_a, cmp_selected, cmp_api_key,
                            framework_requirements, progress_a
                        )
                    )
                except Exception as e:
                    st.error(f"Failed on {cmp_name_a}: {e}")
                    results_a, summaries_a = [], {}

                st.markdown(f"### Analysing {cmp_name_b}...")
                progress_b = st.progress(0)
                try:
                    results_b, summaries_b, usage_b = (
                        claude_analyze_report(
                            report_b, cmp_selected, cmp_api_key,
                            framework_requirements, progress_b
                        )
                    )
                except Exception as e:
                    st.error(f"Failed on {cmp_name_b}: {e}")
                    results_b, summaries_b = [], {}

                if results_a and results_b:
                    st.session_state.cmp_results_a = results_a
                    st.session_state.cmp_results_b = results_b
                    st.session_state.cmp_summaries_a = summaries_a
                    st.session_state.cmp_summaries_b = summaries_b
                    st.session_state.cmp_stored_name_a = cmp_name_a
                    st.session_state.cmp_stored_name_b = cmp_name_b
                    st.session_state.cmp_frameworks = cmp_selected
                    st.success("Comparison complete!")

        # --- Display comparison results ---
        if (
            'cmp_results_a' in st.session_state
            and st.session_state.cmp_results_a
        ):
            results_a = st.session_state.cmp_results_a
            results_b = st.session_state.cmp_results_b
            summaries_a = st.session_state.cmp_summaries_a
            summaries_b = st.session_state.cmp_summaries_b
            name_a = st.session_state.cmp_stored_name_a
            name_b = st.session_state.cmp_stored_name_b
            common_frameworks = st.session_state.cmp_frameworks

            st.markdown("---")
            st.subheader("Comparison Results")

            st.markdown(
                '<div style="background:#f5f5f5;border:1px solid #e0e0e0;'
                'border-radius:8px;padding:16px;margin-bottom:16px;">'
                '<h4 style="margin:0 0 12px 0;color:#1a1a1a;">'
                'Coverage Summary</h4>'
                '<table style="width:100%;border-collapse:collapse;'
                'font-size:13px;">'
                '<tr style="border-bottom:2px solid #e0e0e0;">'
                '<th style="text-align:left;padding:6px;color:#1a1a1a;">'
                'Framework</th>'
                f'<th style="text-align:center;padding:6px;color:#1a1a1a;"'
                f' colspan="3">{name_a}</th>'
                f'<th style="text-align:center;padding:6px;color:#1a1a1a;"'
                f' colspan="3">{name_b}</th>'
                '</tr>'
                '<tr style="border-bottom:1px solid #e0e0e0;'
                'font-size:11px;color:#888;">'
                '<td></td>'
                '<td style="text-align:center;padding:4px;">Covered</td>'
                '<td style="text-align:center;padding:4px;">Partly</td>'
                '<td style="text-align:center;padding:4px;">Not</td>'
                '<td style="text-align:center;padding:4px;">Covered</td>'
                '<td style="text-align:center;padding:4px;">Partly</td>'
                '<td style="text-align:center;padding:4px;">Not</td>'
                '</tr>',
                unsafe_allow_html=True
            )

            table_rows = ""
            for fw in common_frameworks:
                sa = summaries_a.get(fw, {}).get("counts", {})
                sb = summaries_b.get(fw, {}).get("counts", {})
                table_rows += (
                    '<tr style="border-bottom:1px solid #f0f0f0;">'
                    f'<td style="padding:6px;font-weight:600;'
                    f'color:#1a1a1a;">{fw}</td>'
                    f'<td style="text-align:center;padding:6px;'
                    f'background:#dcfce7;color:#166534;">'
                    f'{sa.get(CLASSIFICATION_COVERS, 0)}</td>'
                    f'<td style="text-align:center;padding:6px;'
                    f'background:#fef3c7;color:#92400e;">'
                    f'{sa.get(CLASSIFICATION_PARTLY, 0)}</td>'
                    f'<td style="text-align:center;padding:6px;'
                    f'background:#fee2e2;color:#991b1b;">'
                    f'{sa.get(CLASSIFICATION_DOESNT, 0)}</td>'
                    f'<td style="text-align:center;padding:6px;'
                    f'background:#dcfce7;color:#166534;">'
                    f'{sb.get(CLASSIFICATION_COVERS, 0)}</td>'
                    f'<td style="text-align:center;padding:6px;'
                    f'background:#fef3c7;color:#92400e;">'
                    f'{sb.get(CLASSIFICATION_PARTLY, 0)}</td>'
                    f'<td style="text-align:center;padding:6px;'
                    f'background:#fee2e2;color:#991b1b;">'
                    f'{sb.get(CLASSIFICATION_DOESNT, 0)}</td>'
                    '</tr>'
                )
            st.markdown(
                f'{table_rows}</table></div>', unsafe_allow_html=True
            )

            st.subheader("Requirement-by-Requirement")

            b_lookup = {}
            for r in results_b:
                key = (r["framework"], r["topic"], r["requirement"][:100])
                b_lookup[key] = r

            for fw in common_frameworks:
                fw_results_a = [
                    r for r in results_a if r["framework"] == fw
                ]
                if not fw_results_a:
                    continue

                better_a, better_b, same = 0, 0, 0
                for r_a in fw_results_a:
                    key = (
                        r_a["framework"], r_a["topic"],
                        r_a["requirement"][:100]
                    )
                    r_b = b_lookup.get(key)
                    if r_b:
                        s_a = classification_to_score(r_a["classification"])
                        s_b = classification_to_score(r_b["classification"])
                        if s_a > s_b:
                            better_a += 1
                        elif s_b > s_a:
                            better_b += 1
                        else:
                            same += 1

                with st.expander(
                    f"**{fw}** \u2014 {name_a} leads on {better_a} \u00b7 "
                    f"{name_b} leads on {better_b} \u00b7 {same} same"
                ):
                    topics_seen = []
                    for r in fw_results_a:
                        if r["topic"] not in topics_seen:
                            topics_seen.append(r["topic"])

                    for topic in topics_seen:
                        topic_results = [
                            r for r in fw_results_a if r["topic"] == topic
                        ]
                        st.markdown(f"**{prettify_topic_name(topic)}**")

                        for r_a in topic_results:
                            key = (
                                r_a["framework"], r_a["topic"],
                                r_a["requirement"][:100]
                            )
                            r_b = b_lookup.get(key)

                            class_a = r_a["classification"]
                            class_b = (
                                r_b["classification"]
                                if r_b else CLASSIFICATION_DOESNT
                            )
                            badge_a = CLASSIFICATION_BADGES.get(
                                class_a, "badge-doesnt"
                            )
                            badge_b = CLASSIFICATION_BADGES.get(
                                class_b, "badge-doesnt"
                            )

                            req_text = r_a["requirement"]
                            if len(req_text) > 180:
                                req_text = req_text[:180] + "\u2026"

                            st.markdown(
                                f'<div style="background:#f5f5f5;'
                                f'padding:12px;border-radius:8px;'
                                f'margin:8px 0;">'
                                f'<p style="margin:0 0 8px 0;'
                                f'font-size:13px;color:#1a1a1a;">'
                                f'{req_text}</p>'
                                f'<div style="display:flex;gap:16px;'
                                f'align-items:center;flex-wrap:wrap;">'
                                f'<div style="flex:1;min-width:200px;">'
                                f'<span style="font-size:11px;color:#888;'
                                f'text-transform:uppercase;">'
                                f'{name_a}</span><br>'
                                f'<span class="{badge_a}">'
                                f'{class_a}</span>'
                                f'</div>'
                                f'<div style="flex:1;min-width:200px;">'
                                f'<span style="font-size:11px;color:#888;'
                                f'text-transform:uppercase;">'
                                f'{name_b}</span><br>'
                                f'<span class="{badge_b}">'
                                f'{class_b}</span>'
                                f'</div>'
                                f'</div>'
                                f'</div>',
                                unsafe_allow_html=True
                            )

            st.markdown("---")
            cmp_excel = generate_comparison_excel(
                results_a, results_b, name_a, name_b, common_frameworks
            )
            st.download_button(
                label="\U0001f4e5 Download Comparison as Excel",
                data=cmp_excel,
                file_name="framework_comparison.xlsx",
                mime=(
                    "application/vnd.openxmlformats-officedocument"
                    ".spreadsheetml.sheet"
                ),
                key="cmp_download"
            )


if __name__ == "__main__":
    main()
