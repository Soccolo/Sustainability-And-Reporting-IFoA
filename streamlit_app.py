"""
Sustainability Framework Analyzer - Streamlit App
Deploy to Streamlit Cloud for free public access.

Uses spacy-universal-sentence-encoder with nlp.similarity() - 
the exact same method from the Jupyter notebook.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO

# Page config
st.set_page_config(
    page_title="Sustainability Framework Analyzer",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .stApp {
        background-color: #0f172a;
    }
    .main .block-container {
        padding-top: 2rem;
    }
    h1, h2, h3 {
        color: #f1f5f9 !important;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: #1e293b;
        border-radius: 8px;
        padding: 10px 20px;
        color: #94a3b8;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(to right, #10b981, #06b6d4);
        color: white;
    }
    .framework-card {
        background-color: #1e293b;
        border-radius: 8px;
        padding: 1rem;
        margin: 0.5rem 0;
    }
    .score-high { color: #10b981; }
    .score-medium { color: #06b6d4; }
    .score-low { color: #f59e0b; }
    .score-verylow { color: #ef4444; }
</style>
""", unsafe_allow_html=True)

# ============================================
# DATA
# ============================================

FRAMEWORK_COLORS = {
    "TCFD": "#3b82f6",
    "TNFD": "#10b981",
    "PRA": "#f59e0b",
    "IFRS": "#ef4444",
    "TPT": "#8b5cf6",
    "BMA": "#ec4899",
    "MAS": "#14b8a6",
    "ESRS": "#f97316",
    "OSFI": "#06b6d4",
    "SBTi": "#a855f7"
}

FRAMEWORK_FULL_NAMES = {
    "TCFD": "Task Force on Climate-related Financial Disclosures",
    "TNFD": "Taskforce on Nature-related Financial Disclosures",
    "PRA": "Prudential Regulation Authority",
    "IFRS": "International Financial Reporting Standards",
    "TPT": "Transition Plan Taskforce",
    "BMA": "Bermuda Monetary Authority",
    "MAS": "Monetary Authority of Singapore",
    "ESRS": "European Sustainability Reporting Standards",
    "OSFI": "Office of the Superintendent of Financial Institutions",
    "SBTi": "Science Based Targets initiative"
}

ADOPTION_DICT = {
    "TCFD": ["Canada", "France", "Germany", "Italy", "Japan", "United Kingdom", "USA", "New Zealand", "Switzerland", "Singapore", "Brazil", "China", "South Africa"],
    "TNFD": ["Brazil", "China", "Colombia", "Costa Rica", "Egypt", "India", "Indonesia", "Kenya", "Malaysia", "Mexico", "Morocco", "Nigeria", "Peru", "Philippines", "South Africa"],
    "PRA": ["United Kingdom"],
    "IFRS": ["Turkey", "Bangladesh", "Brazil", "Australia", "Japan", "United Kingdom", "Canada", "Singapore", "New Zealand", "Nigeria", "South Africa", "Malaysia", "China"],
    "TPT": ["United Kingdom"],
    "BMA": ["Bermuda"],
    "MAS": ["Singapore"],
    "ESRS": ["Austria", "Belgium", "Bulgaria", "Croatia", "Cyprus", "Czech Republic", "Denmark", "Estonia", "Finland", "France", "Germany", "Greece", "Hungary", "Ireland", "Italy", "Latvia", "Lithuania", "Luxembourg", "Malta", "Netherlands", "Poland", "Portugal", "Romania", "Slovakia", "Slovenia", "Spain", "Sweden"],
    "OSFI": ["Canada"],
    "SBTi": ["Japan", "United Kingdom", "USA", "China", "Germany", "France", "India", "Italy", "Canada", "South Korea", "Mexico", "Brazil", "Australia", "South Africa", "Turkey", "Romania", "Malta"]
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

FRAMEWORK_REQUIREMENTS = {
    "TCFD": {
        "Governance": [
            "Describe the board's oversight of climate-related risks and opportunities",
            "Describe management's role in assessing and managing climate-related risks and opportunities"
        ],
        "Strategy": [
            "Describe the climate-related risks and opportunities the organization has identified over the short, medium, and long term",
            "Describe the impact of climate-related risks and opportunities on the organization's businesses, strategy, and financial planning",
            "Describe the resilience of the organization's strategy, taking into consideration different climate-related scenarios"
        ],
        "RiskManagement": [
            "Describe the organization's processes for identifying and assessing climate-related risks",
            "Describe the organization's processes for managing climate-related risks",
            "Describe how processes for identifying, assessing, and managing climate-related risks are integrated into the organization's overall risk management"
        ],
        "MetricsandTargets": [
            "Disclose the metrics used by the organization to assess climate-related risks and opportunities",
            "Disclose Scope 1, Scope 2, and, if appropriate, Scope 3 greenhouse gas (GHG) emissions",
            "Describe the targets used by the organization to manage climate-related risks and opportunities and performance against targets"
        ]
    },
    "TNFD": {
        "Governance": [
            "Describe the board's oversight of nature-related dependencies, impacts, risks and opportunities",
            "Describe management's role in assessing and managing nature-related dependencies, impacts, risks and opportunities"
        ],
        "Strategy": [
            "Describe the nature-related dependencies, impacts, risks and opportunities the organisation has identified",
            "Describe the effect nature-related dependencies, impacts, risks and opportunities have had on the organisation's business model, value chain, strategy, and financial planning",
            "Describe the resilience of the organisation's strategy to nature-related risks and opportunities"
        ],
        "RiskManagement": [
            "Describe the organisation's processes for identifying, assessing and prioritising nature-related dependencies, impacts, risks and opportunities",
            "Describe the organisation's processes for managing nature-related dependencies, impacts, risks and opportunities"
        ],
        "MetricsandTargets": [
            "Disclose the metrics used by the organisation to assess and manage material nature-related risks and opportunities",
            "Describe the targets and goals used by the organisation to manage nature-related dependencies, impacts, risks and opportunities"
        ]
    },
    "ESRS": {
        "Governance": [
            "Disclose information about the governance structure and its composition including committees responsible for decision-making on sustainability matters",
            "Disclose information about the role of the administrative, management and supervisory bodies with regard to sustainability matters"
        ],
        "Strategy": [
            "Disclose the undertaking's strategy and business model in relation to sustainability matters",
            "Describe how the undertaking's strategy and business model interact with its material impacts, risks and opportunities"
        ],
        "RiskManagement": [
            "Describe the processes by which sustainability-related risks are identified, assessed and managed",
            "Describe how sustainability-related risks are integrated into the undertaking's overall risk management"
        ],
        "MetricsandTargets": [
            "Disclose the metrics used to assess performance in relation to each material sustainability matter",
            "Disclose Scope 1, Scope 2 and Scope 3 greenhouse gas emissions",
            "Describe the targets the undertaking has adopted and the progress made towards achieving those targets"
        ],
        "Disclosure": [
            "Prepare sustainability statements in accordance with ESRS",
            "Disclose policies adopted to manage material sustainability matters"
        ]
    },
    "IFRS": {
        "Governance": [
            "Disclose information about the governance body or bodies responsible for oversight of sustainability-related risks and opportunities"
        ],
        "Strategy": [
            "Disclose sustainability-related risks and opportunities that could reasonably be expected to affect the entity's prospects",
            "Disclose how sustainability-related risks and opportunities affect the entity's strategy and decision-making"
        ],
        "RiskManagement": [
            "Describe the processes the entity uses to identify, assess and manage sustainability-related risks"
        ],
        "MetricsandTargets": [
            "Disclose information relevant to the cross-industry metric categories",
            "Disclose targets set by the entity to mitigate or adapt to sustainability-related risks"
        ]
    },
    "PRA": {
        "Strategy": [
            "Develop a strategic approach to managing climate-related financial risks",
            "Consider how climate-related scenarios could affect the firm's business model and strategy"
        ],
        "RiskManagement": [
            "Embed climate-related financial risks within the firm's overall risk management framework",
            "Develop appropriate key risk indicators and limits for climate-related financial risks"
        ],
        "ScenarioAnalysis": [
            "Develop capabilities and tools to assess climate-related risks using scenario analysis",
            "Consider a range of scenarios, including those consistent with the Paris Agreement"
        ],
        "Disclosure": [
            "Disclose how climate-related financial risks are governed and managed",
            "Disclose metrics and targets used to assess and manage climate-related financial risks"
        ]
    },
    "TPT": {
        "Strategy": [
            "Articulate the entity's climate transition plan and how it aligns with achieving net zero",
            "Describe the entity's strategic ambition and priorities for addressing climate change"
        ],
        "MetricsandTargets": [
            "Set and disclose targets for reducing greenhouse gas emissions",
            "Disclose metrics to measure progress against the transition plan"
        ],
        "Governance": [
            "Describe board-level oversight of climate transition planning and implementation"
        ]
    },
    "BMA": {
        "MaterialityAssessment": [
            "Conduct an assessment of the materiality of climate-related risks",
            "Consider both physical and transition risks in the materiality assessment"
        ],
        "Governance": [
            "Establish appropriate governance structures for managing climate-related risks"
        ],
        "RiskManagement": [
            "Integrate climate-related risks into the insurer's risk management framework",
            "Develop stress testing and scenario analysis capabilities for climate risks"
        ],
        "ORSA": [
            "Include climate-related risks in the Own Risk and Solvency Assessment"
        ]
    },
    "MAS": {
        "Governance": [
            "Establish board and senior management oversight of environmental risk management"
        ],
        "RiskManagement": [
            "Integrate environmental risk into the institution's risk management framework",
            "Develop tools and metrics to assess and monitor environmental risk"
        ],
        "Underwriting": [
            "Consider environmental risk factors in underwriting and investment decisions"
        ],
        "Disclosure": [
            "Disclose environmental risk exposures and management approach"
        ]
    },
    "OSFI": {
        "Governance": [
            "Establish governance structures for oversight of climate-related risks"
        ],
        "RiskManagement": [
            "Integrate climate-related risks into the institution's risk management framework"
        ],
        "ScenarioAnalysis": [
            "Conduct climate scenario analysis to assess potential impacts"
        ],
        "Disclosure": [
            "Disclose climate-related risks in accordance with regulatory requirements"
        ]
    },
    "SBTi": {
        "MetricsandTargets": [
            "Set science-based targets aligned with 1.5°C or well-below 2°C pathways",
            "Include Scope 1, 2 and relevant Scope 3 emissions in target boundary",
            "Report progress against targets annually"
        ],
        "Governance": [
            "Obtain board-level approval for science-based targets"
        ],
        "Disclosure": [
            "Publicly announce commitment to set science-based targets"
        ]
    }
}


# ============================================
# HELPER FUNCTIONS
# ============================================

@st.cache_resource
def load_nlp_model():
    """Load the spacy universal sentence encoder model (cached)"""
    import spacy_universal_sentence_encoder
    return spacy_universal_sentence_encoder.load_model('en_use_lg')


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


def document_similarity(text_list, selected_frameworks, progress_bar=None):
    """
    Calculate similarity using spacy nlp.similarity() - 
    the exact same method from the Jupyter notebook.
    """
    nlp = load_nlp_model()
    
    results = []
    
    # Pre-compute document embeddings
    doc_nlps = [nlp(text) for text in text_list]
    
    # Count total steps for progress
    total_steps = sum(
        len(topics) 
        for fw in selected_frameworks 
        if fw in FRAMEWORK_REQUIREMENTS
        for topics in [FRAMEWORK_REQUIREMENTS[fw]]
    )
    current_step = 0
    
    for framework in selected_frameworks:
        if framework not in FRAMEWORK_REQUIREMENTS:
            continue
            
        topics = FRAMEWORK_REQUIREMENTS[framework]
        
        for topic, requirements in topics.items():
            similarities = []
            
            for requirement in requirements:
                # Create spacy doc for requirement (same as notebook)
                curr_nlp = nlp(requirement)
                
                for doc_nlp in doc_nlps:
                    # Use nlp.similarity() - the exact method from the notebook
                    similarity = curr_nlp.similarity(doc_nlp)
                    similarities.append(similarity)
            
            # Calculate mean similarity for this topic
            avg_similarity = sum(similarities) / len(similarities) if similarities else 0
            
            results.append({
                "framework": framework,
                "topic": topic,
                "score": float(avg_similarity),
                "explanation": get_explanation(avg_similarity)
            })
            
            current_step += 1
            if progress_bar:
                progress_bar.progress(current_step / total_steps)
    
    # Calculate framework-level averages
    framework_averages = {}
    for framework in selected_frameworks:
        framework_results = [r for r in results if r["framework"] == framework]
        if framework_results:
            avg = sum(r["score"] for r in framework_results) / len(framework_results)
            framework_averages[framework] = avg
    
    return results, framework_averages


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
    """Get similarity scores for a specific framework"""
    mask = (df['Framework 1'] == framework) | (df['Framework 2'] == framework)
    filtered = df[mask].copy()
    
    result = []
    for _, row in filtered.iterrows():
        other = row['Framework 2'] if row['Framework 1'] == framework else row['Framework 1']
        result.append({
            'framework': other,
            'similarity': row['Similarity']
        })
    
    return sorted(result, key=lambda x: x['similarity'], reverse=True)


# ============================================
# MAIN APP
# ============================================

def main():
    st.title("🌍 Sustainability Framework Analyzer")
    st.markdown("Compare & analyze ESG reporting frameworks")
    
    tab1, tab2 = st.tabs(["🗺️ Framework Map", "📊 Report Analyzer"])
    
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
                    f'<span>{fw}</span>'
                    f'<span style="color:#64748b;">({count} countries)</span>'
                    f'</div>',
                    unsafe_allow_html=True
                )
        
        with col2:
            # Create map data
            map_data = []
            
            if selected_framework == "ALL":
                # Show all countries with framework counts
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
                # Show countries for selected framework
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
                    fig.update_traces(marker=dict(color=FRAMEWORK_COLORS[selected_framework]))
                
                fig.update_layout(
                    geo=dict(
                        showland=True,
                        landcolor="#1e293b",
                        showocean=True,
                        oceancolor="#0f172a",
                        showcoastlines=True,
                        coastlinecolor="#334155",
                        showframe=False,
                        bgcolor="#0f172a"
                    ),
                    paper_bgcolor="#0f172a",
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
                        color = "#10b981" if score >= 0.4 else "#06b6d4" if score >= 0.3 else "#f59e0b" if score >= 0.2 else "#ef4444"
                        
                        st.markdown(
                            f'<div style="background:#1e293b;padding:12px;border-radius:8px;margin:8px 0;">'
                            f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                            f'<div style="display:flex;align-items:center;gap:8px;">'
                            f'<div style="width:16px;height:16px;background:{FRAMEWORK_COLORS.get(item["framework"], "#64748b")};border-radius:4px;"></div>'
                            f'<span style="font-weight:600;">{item["framework"]}</span>'
                            f'</div>'
                            f'<span style="color:{color};font-weight:700;font-family:monospace;">{pct:.1f}%</span>'
                            f'</div>'
                            f'<div style="background:#334155;border-radius:4px;height:8px;margin-top:8px;overflow:hidden;">'
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
            "Uses **spacy-universal-sentence-encoder** with `nlp.similarity()` - the exact same method from the Jupyter notebook."
        )
        
        col1, col2 = st.columns([1, 1])
        
        with col1:
            # Framework selection
            st.subheader("Select Frameworks")
            st.markdown("⚡ *Tip: Select fewer frameworks for faster analysis*")
            
            col_sel1, col_sel2 = st.columns(2)
            with col_sel1:
                if st.button("Select All"):
                    st.session_state.selected_frameworks = list(FRAMEWORK_COLORS.keys())
            with col_sel2:
                if st.button("Clear All"):
                    st.session_state.selected_frameworks = []
            
            # Initialize session state
            if 'selected_frameworks' not in st.session_state:
                st.session_state.selected_frameworks = ["TCFD", "TNFD"]
            
            # Framework checkboxes
            selected_frameworks = []
            cols = st.columns(2)
            for i, (fw, color) in enumerate(FRAMEWORK_COLORS.items()):
                with cols[i % 2]:
                    checked = st.checkbox(
                        f"{fw}",
                        value=fw in st.session_state.selected_frameworks,
                        key=f"fw_{fw}",
                        help=FRAMEWORK_FULL_NAMES[fw]
                    )
                    if checked:
                        selected_frameworks.append(fw)
            
            st.session_state.selected_frameworks = selected_frameworks
            
            st.markdown(f"**{len(selected_frameworks)}** framework(s) selected")
            if selected_frameworks:
                st.markdown(f"*Estimated time: ~{len(selected_frameworks) * 15} seconds*")
            
            # File upload
            st.subheader("Upload Document")
            uploaded_file = st.file_uploader(
                "Choose a PDF file",
                type="pdf",
                help="Upload your ESG report or transition plan PDF"
            )
            
            # Or paste text
            st.markdown("**Or paste text:**")
            pasted_text = st.text_area(
                "Paste your report text here",
                height=150,
                placeholder="Paste your ESG report content..."
            )
            
            # Analyze button
            analyze_disabled = (not uploaded_file and not pasted_text) or len(selected_frameworks) == 0
            
            if st.button("🔍 Analyze Report", disabled=analyze_disabled, type="primary"):
                if len(selected_frameworks) == 0:
                    st.error("Please select at least one framework")
                elif not uploaded_file and not pasted_text:
                    st.error("Please upload a PDF or paste text")
                else:
                    with st.spinner("Loading model..."):
                        try:
                            nlp = load_nlp_model()
                            st.success("Model loaded!")
                        except Exception as e:
                            st.error(f"Failed to load model: {e}")
                            st.stop()
                    
                    # Extract text
                    if uploaded_file:
                        with st.spinner("Extracting text from PDF..."):
                            try:
                                text_list = extract_text_from_pdf(uploaded_file)
                                st.success(f"Extracted {len(text_list)} pages")
                            except Exception as e:
                                st.error(f"Failed to extract PDF: {e}")
                                st.stop()
                    else:
                        # Split pasted text into paragraphs
                        text_list = [p.strip().replace('\n', ' ') for p in pasted_text.split('\n\n') if p.strip()]
                        st.info(f"Processing {len(text_list)} paragraphs")
                    
                    # Run analysis
                    st.markdown("### Analyzing...")
                    progress_bar = st.progress(0)
                    
                    try:
                        results, framework_averages = document_similarity(
                            text_list, 
                            selected_frameworks,
                            progress_bar
                        )
                        
                        # Store results in session state
                        st.session_state.analysis_results = results
                        st.session_state.framework_averages = framework_averages
                        st.session_state.num_pages = len(text_list)
                        
                        st.success("Analysis complete!")
                    except Exception as e:
                        st.error(f"Analysis failed: {e}")
        
        with col2:
            st.subheader("Results")
            
            if 'analysis_results' in st.session_state and st.session_state.analysis_results:
                results = st.session_state.analysis_results
                framework_averages = st.session_state.framework_averages
                num_pages = st.session_state.num_pages
                
                # Summary
                avg_score = sum(r['score'] for r in results) / len(results)
                top_fw = max(framework_averages.items(), key=lambda x: x[1])
                
                st.markdown(
                    f'<div style="background:linear-gradient(to right, rgba(16,185,129,0.2), rgba(6,182,212,0.2));'
                    f'border:1px solid rgba(16,185,129,0.3);border-radius:8px;padding:16px;margin-bottom:16px;">'
                    f'<h4 style="margin:0 0 8px 0;">📊 Analysis Summary</h4>'
                    f'<p style="margin:0;color:#cbd5e1;">Analyzed {num_pages} pages. '
                    f'Average similarity: <strong>{avg_score*100:.1f}%</strong>. '
                    f'Best alignment with <strong>{top_fw[0]}</strong> ({top_fw[1]*100:.1f}%).</p>'
                    f'</div>',
                    unsafe_allow_html=True
                )
                
                # Results by framework
                for framework in st.session_state.selected_frameworks:
                    fw_results = [r for r in results if r['framework'] == framework]
                    if not fw_results:
                        continue
                    
                    avg = sum(r['score'] for r in fw_results) / len(fw_results)
                    
                    with st.expander(f"**{framework}** - Avg: {avg*100:.1f}%", expanded=True):
                        for r in fw_results:
                            score = r['score']
                            pct = score * 100
                            color = "#10b981" if score >= 0.4 else "#06b6d4" if score >= 0.3 else "#f59e0b" if score >= 0.2 else "#ef4444"
                            
                            st.markdown(
                                f'<div style="background:#1e293b;padding:12px;border-radius:8px;margin:8px 0;">'
                                f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                                f'<span style="font-weight:500;">{r["topic"]}</span>'
                                f'<span style="color:{color};font-weight:700;font-family:monospace;">{pct:.1f}%</span>'
                                f'</div>'
                                f'<div style="background:#334155;border-radius:4px;height:6px;margin:8px 0;overflow:hidden;">'
                                f'<div style="background:{color};height:100%;width:{pct}%;"></div>'
                                f'</div>'
                                f'<p style="margin:0;font-size:12px;color:#64748b;">{r["explanation"]}</p>'
                                f'</div>',
                                unsafe_allow_html=True
                            )
            else:
                st.info("Upload a document and click 'Analyze Report' to see results")


if __name__ == "__main__":
    main()
