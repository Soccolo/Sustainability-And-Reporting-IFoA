# 🌍 Sustainability Framework Analyzer

A public web app for comparing ESG reports and transition plans against major sustainability frameworks using semantic similarity analysis.

**Live Demo**: [Deploy to Streamlit Cloud to get your URL]

## Features

### 🗺️ Framework Map
- Interactive world map showing global adoption of 10 sustainability frameworks
- Compare similarity between frameworks across different metrics (Governance, Strategy, Risk, etc.)
- View which countries have adopted each framework

### 📊 Report Analyzer
- Upload your PDF or paste text to analyze alignment with frameworks
- Uses **spacy-universal-sentence-encoder** with `nlp.similarity()` - the exact same method from the Jupyter notebook
- Select which frameworks to compare against (fewer = faster)
- Get detailed scores by topic with explanations

## Frameworks Supported

| Framework | Full Name |
|-----------|-----------|
| TCFD | Task Force on Climate-related Financial Disclosures |
| TNFD | Taskforce on Nature-related Financial Disclosures |
| PRA | Prudential Regulation Authority |
| IFRS | International Financial Reporting Standards |
| TPT | Transition Plan Taskforce |
| BMA | Bermuda Monetary Authority |
| MAS | Monetary Authority of Singapore |
| ESRS | European Sustainability Reporting Standards |
| OSFI | Office of the Superintendent of Financial Institutions |
| SBTi | Science Based Targets initiative |

## 🚀 Deploy to Streamlit Cloud (Free)

### Step 1: Create a GitHub Repository

1. Create a new repository on GitHub
2. Upload these files to the repository:
   ```
   your-repo/
   ├── streamlit_app.py
   ├── requirements.txt
   ├── packages.txt
   └── .streamlit/
       └── config.toml
   ```

### Step 2: Deploy on Streamlit Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Sign in with GitHub
3. Click "New app"
4. Select your repository, branch, and `streamlit_app.py` as the main file
5. Click "Deploy"

The app will be live at: `https://your-app-name.streamlit.app`

### Step 3: Wait for Initial Load

The first time the app loads, it will download the Universal Sentence Encoder model (~1GB). This may take a few minutes. Subsequent loads will be faster due to caching.

## 🖥️ Run Locally

```bash
# Clone or download the files
cd sustainability-framework-analyzer

# Install dependencies
pip install -r requirements.txt

# Run the app
streamlit run streamlit_app.py
```

The app will open at `http://localhost:8501`

## Technical Details

### Similarity Calculation

The Report Analyzer uses the exact same methodology as the Jupyter notebook:

```python
import spacy_universal_sentence_encoder

# Load the model
nlp = spacy_universal_sentence_encoder.load_model('en_use_lg')

# For each requirement and document page:
curr_nlp = nlp(requirement_text)
doc_nlp = nlp(document_page_text)
similarity = curr_nlp.similarity(doc_nlp)  # Cosine similarity
```

### PDF Extraction

PDF text extraction uses `pymupdf` (same as notebook):

```python
import pymupdf

doc = pymupdf.open(pdf_path)
for page in doc:
    text = page.get_text().replace('\n', ' ')
```

### Performance Tips

- **Select fewer frameworks** for faster analysis (each adds ~10-20 seconds)
- The model is cached after first load, so subsequent analyses are faster
- Shorter documents analyze faster than longer ones

## File Structure

```
├── streamlit_app.py      # Main Streamlit application
├── requirements.txt      # Python dependencies
├── packages.txt          # System dependencies for Streamlit Cloud
├── .streamlit/
│   └── config.toml       # Streamlit theme configuration
└── README.md             # This file
```

## Requirements

- Python 3.9+
- ~2GB RAM for model loading
- Dependencies listed in `requirements.txt`

## License

MIT License - feel free to use and modify!
