"""
Sustainability Framework Analyzer - Streamlit App
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
    page_title="Sustainability Framework Analyzer",
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

SIMILARITY_DATA = {
    'all_metrics': """Framework 1,Framework 2,Similarity
TCFD,TNFD,0.5839409060203112
TCFD,PRA,0.2730686519708898
TCFD,IFRS,0.2609125928445296
TCFD,TPT,0.1371060654404573
TCFD,BMA,0.23608424584381282
TCFD,MAS,0.23776556043462319
TCFD,ESRS,0.15567206435121042
TCFD,OSFI,0.23439122204269683
TCFD,SBTi,0.07999969971376235
TNFD,PRA,0.26212777422430616
TNFD,IFRS,0.24842039945006772
TNFD,TPT,0.17511612896553494
TNFD,BMA,0.2187226692920709
TNFD,MAS,0.21794932497044403
TNFD,ESRS,0.15590236308338765
TNFD,OSFI,0.20535417050123214
TNFD,SBTi,0.07007073858424241
PRA,IFRS,0.2995363886926382
PRA,TPT,0.23302435825268428
PRA,BMA,0.4032735864873286
PRA,MAS,0.3784382710369622
PRA,ESRS,0.2269684903028034
PRA,OSFI,0.27517913434749997
PRA,SBTi,0.17912637955612606
IFRS,TPT,0.2874849606305361
IFRS,BMA,0.26682314644681243
IFRS,MAS,0.2500543958740309
IFRS,ESRS,0.22721959570720437
IFRS,OSFI,0.1684209586431583
IFRS,SBTi,0.14948693523183465
TPT,BMA,0.21122716888785362
TPT,MAS,0.1905254645156674
TPT,ESRS,0.2575311665149296
TPT,OSFI,0.21526032388210298
TPT,SBTi,0.25215436905622485
BMA,MAS,0.44722233104086156
BMA,ESRS,0.22502909949008787
BMA,OSFI,0.31030812229101473
BMA,SBTi,0.21081559400666844
MAS,ESRS,0.21739759569646364
MAS,OSFI,0.3005068784481601
MAS,SBTi,0.19532913667090396
ESRS,OSFI,0.19031452880257607
ESRS,SBTi,0.12993192649909902
OSFI,SBTi,0.14086035046784673""",
    'governance': """Framework 1,Framework 2,Similarity
TCFD,TNFD,0.6521318356196085
TCFD,IFRS,0.223162354901433
TCFD,TPT,0.08889173832722008
TCFD,BMA,0.19514061798426238
TCFD,MAS,0.2784103788435459
TCFD,ESRS,0.2051142305135727
TCFD,OSFI,0.1666110996156931
TCFD,SBTi,0.0358133009634912
TNFD,IFRS,0.21374623167018095
TNFD,TPT,0.07678758837282658
TNFD,BMA,0.20086695002674154
TNFD,MAS,0.2799379726250966
TNFD,ESRS,0.19106648862361908
TNFD,OSFI,0.18155286461114883
TNFD,SBTi,0.051613214922448
IFRS,TPT,0.2583204656839371
IFRS,BMA,0.24816494265740568
IFRS,MAS,0.3169849095866084
IFRS,ESRS,0.1901303119957447
IFRS,OSFI,0.1601065108552575
IFRS,SBTi,0.14948693523183465
TPT,BMA,0.21122716888785362
TPT,MAS,0.1905254645156674
TPT,ESRS,0.15190743803977966
TPT,OSFI,0.21526032388210298
TPT,SBTi,0.25215436905622485
BMA,MAS,0.4620742628520185
BMA,ESRS,0.338406809351661
BMA,OSFI,0.3808234611695463
BMA,SBTi,0.21081559400666844
MAS,ESRS,0.30484993010759354
MAS,OSFI,0.2966248672455549
MAS,SBTi,0.20165940895676612
ESRS,OSFI,0.23870150744915009
ESRS,SBTi,0.17281209528446198
OSFI,SBTi,0.2669262558221817""",
    'strategy': """Framework 1,Framework 2,Similarity
TCFD,TNFD,0.48580174272259075
TCFD,PRA,0.23524054884910583
TCFD,IFRS,0.2523530203435156
TCFD,TPT,0.15317750781153638
TCFD,ESRS,0.22506307589355856
TNFD,PRA,0.22991521190851927
TNFD,IFRS,0.23779052236738304
TNFD,TPT,0.2119893316878006
TNFD,ESRS,0.22413806741315057
PRA,IFRS,0.2953542077292999
PRA,TPT,0.23302435825268428
PRA,ESRS,0.3269041081269582
IFRS,TPT,0.2894292602936427
IFRS,ESRS,0.2316846524370097
TPT,ESRS,0.26413264954462645""",
    'risk': """Framework 1,Framework 2,Similarity
TCFD,TNFD,0.7013311435778936
TCFD,PRA,0.28567801967815115
TCFD,IFRS,0.35027621189753216
TCFD,BMA,0.24609268820948071
TCFD,MAS,0.2287333785659737
TCFD,ESRS,0.15295727507866644
TCFD,OSFI,0.3247647186120351
TNFD,PRA,0.27286529499623513
TNFD,IFRS,0.354150103405118
TNFD,BMA,0.22363299209003648
TNFD,MAS,0.2024521630567809
TNFD,ESRS,0.19946823917174092
TNFD,OSFI,0.24105612933635712
PRA,IFRS,0.30999184110098416
PRA,BMA,0.4032735864873286
PRA,MAS,0.38699578797375717
PRA,ESRS,0.25300263944599366
PRA,OSFI,0.30415812300311196
IFRS,BMA,0.27366448783626157
IFRS,MAS,0.22774422463650504
IFRS,ESRS,0.21439658903626777
IFRS,OSFI,0.1850498542189598
BMA,MAS,0.4454070949306091
BMA,ESRS,0.22271955354846323
BMA,OSFI,0.2585968737800916
MAS,ESRS,0.23263172574634491
MAS,OSFI,0.31769876678784686
ESRS,OSFI,0.1823627275104324""",
    'metrics': """Framework 1,Framework 2,Similarity
TCFD,TNFD,0.5128121872742971
TCFD,ESRS,0.14568644713748385
TCFD,SBTi,0.08165462101527063
TNFD,ESRS,0.12240990633317442
TNFD,SBTi,0.0711076781158039
ESRS,SBTi,0.13019893129793814""",
    'disclosure': """Framework 1,Framework 2,Similarity
PRA,MAS,0.3168241490920385
PRA,ESRS,0.18805091977941202
PRA,OSFI,0.26648543775081635
PRA,SBTi,0.17912637955612606
MAS,ESRS,0.18170758169235698
MAS,OSFI,0.2907709578673045
MAS,SBTi,0.19064004608878382
ESRS,OSFI,0.1905417761847596
ESRS,SBTi,0.12503772418815917
OSFI,SBTi,0.11751481243926618"""
}


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
    Use Claude Haiku 4.5 to assess a report requirement-by-requirement.

    For each framework requirement, Claude:
    1. Searches the full report for all relevant passages
    2. Classifies how well the requirement is addressed:
       - "Covers the framework"
       - "Partly covers the framework"
       - "Doesn't cover the framework"
    3. Provides a rationale referencing the specific text found

    Cost optimisation:
    - Uses claude-haiku-4-5-20251001 (cheapest model: $1/$5 per MTok)
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

        try:
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=8192,
                system=system_message,
                messages=[{"role": "user", "content": requirements_text}]
            )

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
        except anthropic.APIError as e:
            st.error(f"API error for {framework}: {e}")

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


def parse_similarity_csv(csv_string):
    """Parse similarity CSV data"""
    from io import StringIO
    df = pd.read_csv(StringIO(csv_string))
    return df


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


# ============================================
# MAIN APP
# ============================================

def main():
    st.title("Sustainability Framework Analyzer")
    st.markdown("Compare & analyze ESG reporting frameworks")

    # Load requirements from Excel once
    framework_requirements = load_framework_requirements()

    tab1, tab2 = st.tabs(["Framework Map", "Report Analyzer"])

    # ============================================
    # TAB 1: FRAMEWORK MAP
    # ============================================
    with tab1:
        st.header("Climate & Sustainability Framework Adoption")
        st.markdown("Interactive map showing global adoption of regulatory frameworks")

        col1, col2 = st.columns([1, 3])

        with col1:
            # Metric selector
            metric_type = st.selectbox(
                "Select Metric Type",
                options=["all_metrics", "governance", "strategy", "risk", "metrics", "disclosure"],
                format_func=lambda x: x.replace("_", " ").title()
            )

            # Framework selector
            framework_options = ["ALL"] + list(FRAMEWORK_COLORS.keys())
            selected_framework = st.selectbox(
                "Select Framework",
                options=framework_options
            )

            # Legend
            st.markdown("### Framework Legend")
            for fw, color in FRAMEWORK_COLORS.items():
                count = len(ADOPTION_DICT.get(fw, []))
                st.markdown(
                    f'<div style="display:flex;align-items:center;gap:8px;margin:4px 0;">'
                    f'<div style="width:16px;height:16px;background:{color};border-radius:4px;"></div>'
                    f'<span style="color:#1a1a1a;">{fw}</span>'
                    f'<span style="color:#888888;">({count} countries)</span>'
                    f'</div>',
                    unsafe_allow_html=True
                )

        with col2:
            # Create map data
            map_data = []

            if selected_framework == "ALL":
                all_countries = set()
                for countries in ADOPTION_DICT.values():
                    all_countries.update(countries)

                for country in all_countries:
                    if country in COUNTRY_COORDS:
                        frameworks = [fw for fw, countries in ADOPTION_DICT.items() if country in countries]
                        map_data.append({
                            "country": country,
                            "lat": COUNTRY_COORDS[country]["lat"],
                            "lon": COUNTRY_COORDS[country]["lon"],
                            "frameworks": len(frameworks),
                            "framework_list": ", ".join(frameworks),
                            "size": 10 + len(frameworks) * 3
                        })
            else:
                countries = ADOPTION_DICT.get(selected_framework, [])
                for country in countries:
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
                    df_map,
                    lat="lat",
                    lon="lon",
                    hover_name="country",
                    hover_data={"framework_list": True, "lat": False, "lon": False, "frameworks": False, "size": False},
                    size="size",
                    color="frameworks" if selected_framework == "ALL" else None,
                    color_continuous_scale="Viridis" if selected_framework == "ALL" else None,
                    projection="natural earth"
                )

                if selected_framework != "ALL":
                    fig.update_traces(marker=dict(color=FRAMEWORK_COLORS.get(selected_framework, "#888")))

                fig.update_layout(
                    geo=dict(
                        showland=True,
                        landcolor="#e8e8e8",
                        showocean=True,
                        oceancolor="#f8f8f8",
                        showcoastlines=True,
                        coastlinecolor="#cccccc",
                        showframe=False,
                        bgcolor="#ffffff"
                    ),
                    paper_bgcolor="#ffffff",
                    plot_bgcolor="#ffffff",
                    font=dict(color="#1a1a1a"),
                    coloraxis_colorbar=dict(
                        tickfont=dict(color="#1a1a1a"),
                        titlefont=dict(color="#1a1a1a"),
                    ),
                    margin=dict(l=0, r=0, t=0, b=0),
                    height=500
                )

                st.plotly_chart(fig, use_container_width=True)

            # Similarity table
            if selected_framework != "ALL":
                st.markdown(f"### Framework Similarity: {selected_framework}")
                st.markdown(f"*Metric: {metric_type.replace('_', ' ').title()}*")

                df_sim = parse_similarity_csv(SIMILARITY_DATA[metric_type])
                similarities = get_similarity_for_framework(df_sim, selected_framework)

                if similarities:
                    for item in similarities:
                        score = item['similarity']
                        pct = score * 100
                        color = "#16a34a" if score >= 0.4 else "#2563eb" if score >= 0.3 else "#d97706" if score >= 0.2 else "#dc2626"

                        st.markdown(
                            f'<div style="background:#f5f5f5;padding:12px;border-radius:8px;margin:8px 0;">'
                            f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                            f'<div style="display:flex;align-items:center;gap:8px;">'
                            f'<div style="width:16px;height:16px;background:{FRAMEWORK_COLORS.get(item["framework"], "#888888")};border-radius:4px;"></div>'
                            f'<span style="font-weight:600;color:#1a1a1a;">{item["framework"]}</span>'
                            f'</div>'
                            f'<span style="color:{color};font-weight:700;font-family:monospace;">{pct:.1f}%</span>'
                            f'</div>'
                            f'<div style="background:#e0e0e0;border-radius:4px;height:8px;margin-top:8px;overflow:hidden;">'
                            f'<div style="background:{color};height:100%;width:{pct}%;"></div>'
                            f'</div>'
                            f'</div>',
                            unsafe_allow_html=True
                        )
                else:
                    st.info(f"No similarity data available for {selected_framework} under {metric_type}")

        # About section
        with st.expander("About the Frameworks"):
            for fw, name in FRAMEWORK_FULL_NAMES.items():
                st.markdown(f"**{fw}** - {name}")

    # ============================================
    # TAB 2: REPORT ANALYZER
    # ============================================
    with tab2:
        st.header("ESG Report Comparison Tool")
        st.markdown(
            "Upload your transition plan or ESG report PDF to analyze how well it aligns with sustainability frameworks. "
            "Uses **Claude Haiku 4.5** to classify your report requirement-by-requirement — finding relevant text across the "
            "full document, classifying coverage, and providing a rationale for each."
        )

        # API key input
        api_key = st.text_input(
            "Anthropic API Key",
            type="password",
            placeholder="sk-ant-...",
            help="Required for analysis. Your key is not stored. Get one at console.anthropic.com"
        )

        col1, col2 = st.columns([1, 1])

        with col1:
            # Framework selection
            st.subheader("Select Frameworks")
            st.markdown("*Tip: Select fewer frameworks for faster analysis*")

            # Use frameworks available in the loaded Excel
            available_frameworks = list(framework_requirements.keys()) if framework_requirements else list(FRAMEWORK_COLORS.keys())

            col_sel1, col_sel2 = st.columns(2)
            with col_sel1:
                if st.button("Select All"):
                    st.session_state.selected_frameworks = available_frameworks.copy()
            with col_sel2:
                if st.button("Clear All"):
                    st.session_state.selected_frameworks = []

            # Initialize session state
            if 'selected_frameworks' not in st.session_state:
                st.session_state.selected_frameworks = ["TCFD", "TNFD"]

            # Framework checkboxes
            selected_frameworks = []
            cols = st.columns(2)
            for i, fw in enumerate(available_frameworks):
                color = FRAMEWORK_COLORS.get(fw, "#888888")
                with cols[i % 2]:
                    # Count requirements for this framework
                    req_count = sum(len(reqs) for reqs in framework_requirements.get(fw, {}).values())
                    checked = st.checkbox(
                        f"{fw}",
                        value=fw in st.session_state.selected_frameworks,
                        key=f"fw_{fw}",
                        help=f"{FRAMEWORK_FULL_NAMES.get(fw, fw)} ({req_count} requirements)"
                    )
                    if checked:
                        selected_frameworks.append(fw)

            st.session_state.selected_frameworks = selected_frameworks

            total_reqs = sum(
                sum(len(reqs) for reqs in framework_requirements.get(fw, {}).values())
                for fw in selected_frameworks
            )
            st.markdown(f"**{len(selected_frameworks)}** framework(s) selected · **{total_reqs}** requirements")
            if selected_frameworks:
                st.markdown(f"*Estimated time: ~{len(selected_frameworks) * 8} seconds (1 API call per framework)*")

            # File upload
            st.subheader("Upload Document")
            uploaded_file = st.file_uploader(
                "Choose a PDF file",
                type="pdf",
                help="Upload your ESG report or transition plan PDF"
            )

            # Page range selection (only shown when a PDF is uploaded)
            page_start = 1
            page_end = None
            if uploaded_file:
                # Peek at total page count without consuming the file
                import pymupdf
                pdf_bytes = uploaded_file.read()
                uploaded_file.seek(0)  # reset so it can be read again later
                with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
                    total_pages = len(doc)

                st.markdown(f"**PDF has {total_pages} pages.** Select the range to analyse:")
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
                    st.warning("'From page' must be ≤ 'To page'.")

            # Or paste text
            st.markdown("**Or paste text:**")
            pasted_text = st.text_area(
                "Paste your report text here",
                height=150,
                placeholder="Paste your ESG report content..."
            )

            # Analyze button
            analyze_disabled = (not uploaded_file and not pasted_text) or len(selected_frameworks) == 0 or not api_key

            if st.button("Analyze Report", disabled=analyze_disabled, type="primary"):
                if not api_key:
                    st.error("Please enter your Anthropic API key")
                elif len(selected_frameworks) == 0:
                    st.error("Please select at least one framework")
                elif not uploaded_file and not pasted_text:
                    st.error("Please upload a PDF or paste text")
                else:
                    # Extract text
                    if uploaded_file:
                        # Validate page range
                        if page_end is not None and page_start > page_end:
                            st.error("'From page' must be ≤ 'To page'.")
                            st.stop()

                        with st.spinner("Extracting text from PDF..."):
                            try:
                                text_list = extract_text_from_pdf(uploaded_file)
                                total = len(text_list)
                                # Apply page range (convert 1-indexed to 0-indexed)
                                start_idx = max(0, page_start - 1)
                                end_idx = page_end if page_end is not None else total
                                text_list = text_list[start_idx:end_idx]
                                st.success(
                                    f"Analysing pages {page_start}–{end_idx} "
                                    f"({len(text_list)} of {total} pages)"
                                )
                            except Exception as e:
                                st.error(f"Failed to extract PDF: {e}")
                                st.stop()
                    else:
                        text_list = [p.strip().replace('\n', ' ') for p in pasted_text.split('\n\n') if p.strip()]
                        st.info(f"Processing {len(text_list)} paragraphs")

                    # Combine all pages into single report text for Claude
                    report_text = "\n\n".join(text_list)

                    # Run analysis
                    st.markdown("### Analyzing with Claude Haiku 4.5...")
                    progress_bar = st.progress(0)

                    try:
                        results, framework_summaries, token_usage = claude_analyze_report(
                            report_text,
                            selected_frameworks,
                            api_key,
                            framework_requirements,
                            progress_bar
                        )

                        # Store results in session state
                        st.session_state.analysis_results = results
                        st.session_state.framework_summaries = framework_summaries
                        st.session_state.num_pages = len(text_list)
                        st.session_state.token_usage = token_usage

                        st.success("Analysis complete!")
                    except anthropic.AuthenticationError:
                        st.error("Invalid API key. Please check your Anthropic API key.")
                    except Exception as e:
                        st.error(f"Analysis failed: {e}")

        with col2:
            st.subheader("Results")

            if 'analysis_results' in st.session_state and st.session_state.analysis_results:
                results = st.session_state.analysis_results
                framework_summaries = st.session_state.framework_summaries
                num_pages = st.session_state.num_pages
                token_usage = st.session_state.get('token_usage', {})

                # Overall summary
                total_results = len(results)
                covers_count = sum(1 for r in results if r['classification'] == CLASSIFICATION_COVERS)
                partly_count = sum(1 for r in results if r['classification'] == CLASSIFICATION_PARTLY)
                doesnt_count = sum(1 for r in results if r['classification'] == CLASSIFICATION_DOESNT)

                # Find best framework
                best_fw = max(framework_summaries.items(), key=lambda x: x[1]['avg_score']) if framework_summaries else None

                summary_html = (
                    f'<div style="background:#f5f5f5;border:1px solid #e0e0e0;border-radius:8px;padding:16px;margin-bottom:16px;">'
                    f'<h4 style="margin:0 0 12px 0;color:#1a1a1a;">Analysis Summary</h4>'
                    f'<p style="margin:0 0 8px 0;color:#333333;">Analyzed <strong>{num_pages}</strong> pages against '
                    f'<strong>{len(framework_summaries)}</strong> frameworks '
                    f'({total_results} requirements total).</p>'
                    f'<div style="display:flex;gap:12px;flex-wrap:wrap;margin:8px 0;">'
                    f'<span class="badge-covers">{covers_count} Covers</span>'
                    f'<span class="badge-partly">{partly_count} Partly covers</span>'
                    f'<span class="badge-doesnt">{doesnt_count} Doesn\'t cover</span>'
                    f'</div>'
                )
                if best_fw:
                    summary_html += (
                        f'<p style="margin:8px 0 0 0;color:#333333;">Best alignment with '
                        f'<strong>{best_fw[0]}</strong>.</p>'
                    )
                summary_html += '</div>'
                st.markdown(summary_html, unsafe_allow_html=True)

                # Cost estimate
                if token_usage:
                    input_cost = token_usage.get('input_tokens', 0) / 1_000_000 * 1.0
                    output_cost = token_usage.get('output_tokens', 0) / 1_000_000 * 5.0
                    cache_reads = token_usage.get('cache_read_tokens', 0)
                    cache_savings = cache_reads / 1_000_000 * 0.9
                    total_cost = input_cost + output_cost

                    st.markdown(
                        f'<div style="background:#f5f5f5;border:1px solid #e0e0e0;border-radius:8px;padding:12px;margin-bottom:16px;font-size:13px;color:#333333;">'
                        f'<strong>Estimated cost:</strong> ${total_cost:.4f} '
                        f'({token_usage.get("input_tokens", 0):,} input / {token_usage.get("output_tokens", 0):,} output tokens) '
                        f'{"· Cache saved ~$" + f"{cache_savings:.4f}" if cache_reads > 0 else ""}'
                        f'</div>',
                        unsafe_allow_html=True
                    )

                # Results by framework
                for framework in st.session_state.selected_frameworks:
                    fw_results = [r for r in results if r['framework'] == framework]
                    if not fw_results:
                        continue

                    summary = framework_summaries.get(framework, {})
                    counts = summary.get("counts", {})
                    c_count = counts.get(CLASSIFICATION_COVERS, 0)
                    p_count = counts.get(CLASSIFICATION_PARTLY, 0)
                    d_count = counts.get(CLASSIFICATION_DOESNT, 0)

                    with st.expander(
                        f"**{framework}** — {c_count} cover · {p_count} partly · {d_count} don't cover",
                        expanded=True
                    ):
                        # Group results by topic
                        topics_seen = []
                        for r in fw_results:
                            if r["topic"] not in topics_seen:
                                topics_seen.append(r["topic"])

                        for topic in topics_seen:
                            topic_results = [r for r in fw_results if r["topic"] == topic]
                            st.markdown(f"**{topic}**")

                            for r in topic_results:
                                classification = r['classification']
                                color = CLASSIFICATION_COLORS.get(classification, "#888")
                                badge_class = CLASSIFICATION_BADGES.get(classification, "badge-doesnt")

                                # Build extracts HTML
                                extracts = r.get("relevant_extracts", [])
                                if extracts:
                                    extracts_html = "".join(
                                        f'<div style="background:#fafafa;border-left:3px solid {color};'
                                        f'padding:6px 10px;margin:4px 0;border-radius:0 4px 4px 0;'
                                        f'font-size:12px;color:#555555;font-style:italic;">'
                                        f'"{extract}"</div>'
                                        for extract in extracts
                                    )
                                    extracts_section = (
                                        f'<p style="margin:8px 0 4px 0;font-size:11px;color:#888888;'
                                        f'text-transform:uppercase;letter-spacing:0.5px;">Relevant text found:</p>'
                                        f'{extracts_html}'
                                    )
                                else:
                                    extracts_section = (
                                        f'<p style="margin:8px 0 4px 0;font-size:12px;color:#dc2626;'
                                        f'font-style:italic;">No relevant text found in report</p>'
                                    )

                                # Truncate long requirements for display
                                req_text = r.get("requirement", "")
                                if len(req_text) > 200:
                                    req_text = req_text[:200] + "…"

                                st.markdown(
                                    f'<div style="background:#f5f5f5;padding:12px;border-radius:8px;margin:8px 0;'
                                    f'border-left:4px solid {color};">'
                                    # Classification badge + requirement
                                    f'<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;">'
                                    f'<span style="font-size:13px;color:#1a1a1a;flex:1;">{req_text}</span>'
                                    f'<span class="{badge_class}" style="white-space:nowrap;">{classification}</span>'
                                    f'</div>'
                                    # Extracts
                                    f'{extracts_section}'
                                    # Rationale
                                    f'<p style="margin:8px 0 0 0;font-size:12px;color:#222222;">'
                                    f'<strong>Rationale:</strong> {r.get("rationale", "")}</p>'
                                    f'</div>',
                                    unsafe_allow_html=True
                                )
            else:
                st.info("Upload a document and click 'Analyze Report' to see results")


if __name__ == "__main__":
    main()
