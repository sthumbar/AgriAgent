# 🌿 Agri AI Multi-Agent Assistant

An AI-powered crop health analysis system built with **Google ADK**, **Gemini 2.5 Flash**, and **ChromaDB RAG**. Upload a crop image and receive instant disease detection, fertilizer recommendations, an irrigation schedule, and a downloadable PDF report.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Streamlit UI / CLI                    │
└───────────────────────┬─────────────────────────────────┘
                        │ image path
                        ▼
┌─────────────────────────────────────────────────────────┐
│                 Orchestrator Agent                      │
│  (google.adk.agents.Agent — coordinates pipeline)      │
└───────┬──────────────────────┬──────────────────────────┘
        │                      │                     │
        ▼                      ▼                     ▼
┌───────────────┐   ┌─────────────────────┐  ┌──────────────┐
│ Vision Agent  │   │ Recommendation Agent│  │ Report Agent │
│               │   │                     │  │              │
│ Gemini Vision │   │  RAG (ChromaDB)     │  │  ReportLab   │
│ identify_crop │   │  recommendations.md │  │  PDF + MD    │
│ .md skill     │   │  rag_tool.py        │  │  report.md   │
└───────┬───────┘   └──────────┬──────────┘  └──────┬───────┘
        │                      │                     │
        ▼                      ▼                     ▼
   {crop, disease,      {fertilizer,          {pdf_path,
    confidence,          irrigation,           md_path,
    severity}            treatment,            json_path}
                         prevention}
```

### The Four Agents

| Agent | Responsibility | Key Tool |
|-------|---------------|----------|
| **Orchestrator** | Coordinates the full pipeline; calls all sub-agents in sequence | — |
| **Vision Agent** | Identifies crop species and detects disease from the image | `analyze_crop_image` |
| **Recommendation Agent** | Generates fertilizer, irrigation, and treatment advice using RAG | `get_crop_recommendations` |
| **Report Agent** | Creates executive summary, action plan, PDF, and Markdown reports | `create_report_files` |

---

## Project Structure

```
agri-agent/
├── app.py                       ← CLI entry point
├── requirements.txt
├── .env.example
├── README.md
│
├── agents/
│   ├── orchestrator.py          ← Pipeline coordinator
│   ├── vision_agent.py          ← Gemini Vision crop/disease detection
│   ├── recommendation_agent.py  ← RAG-backed agronomic recommendations
│   └── report_agent.py          ← PDF + Markdown report generation
│
├── skills/                      ← Agent system prompts (markdown)
│   ├── identify_crop.md
│   ├── recommendations.md
│   └── report.md
│
├── tools/
│   ├── image_tool.py            ← Image loading, validation, resize
│   ├── rag_tool.py              ← ChromaDB retrieval
│   └── pdf_tool.py              ← ReportLab PDF generation
│
├── rag/
│   ├── documents/               ← Source knowledge base (.md, .txt, .pdf)
│   │   └── agricultural_knowledge.md
│   ├── vector_store/            ← ChromaDB persistent store (auto-created)
│   └── ingest.py                ← Build / rebuild vector store
│
├── ui/
│   └── streamlit_app.py         ← Streamlit web interface
│
├── reports/                     ← Generated PDF/MD/JSON reports
└── images/                      ← Uploaded images
```

---

## Installation

### 1. Clone / download the project

```bash
cd agri-agent
```

### 2. Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate        # macOS / Linux
.venv\Scripts\activate           # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and add your Gemini API key:

```
GOOGLE_API_KEY=your_actual_key_here
```

Get a free key at: [Google AI Studio](https://aistudio.google.com/app/apikey)

---

## Build the Knowledge Base (RAG)

Before running analyses, build the ChromaDB vector store from the included agricultural documents:

```bash
python rag/ingest.py
```

Output:

```
12:00:00 [INFO] rag.ingest — Loaded: agricultural_knowledge.md (8432 chars)
12:00:01 [INFO] rag.ingest — Split 1 documents into 18 chunks
12:00:05 [INFO] rag.ingest — Stored 18 chunks in ChromaDB collection 'agri_knowledge'
12:00:05 [INFO] rag.ingest — Ingestion complete. Collection count: 18
```

To add your own knowledge, drop `.md`, `.txt`, or `.pdf` files into `rag/documents/` and re-run.

---

## Running the Application

### Option A — Streamlit Web UI (recommended)

```bash
streamlit run ui/streamlit_app.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

Or via `app.py`:

```bash
python app.py --ui
```

### Option B — Command-line Interface

**Analyse a single image:**

```bash
python app.py --image path/to/crop.jpg
```

**Get raw JSON output:**

```bash
python app.py --image crop.jpg --json
```

**Interactive mode:**

```bash
python app.py
```

---

## Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `GOOGLE_API_KEY` | _(required)_ | Your Gemini API key |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model to use |
| `CHROMA_PERSIST_DIR` | `./rag/vector_store` | ChromaDB storage path |
| `RAG_DOCUMENTS_DIR` | `./rag/documents` | Source documents directory |
| `RAG_COLLECTION_NAME` | `agri_knowledge` | ChromaDB collection name |
| `RAG_TOP_K` | `3` | Number of RAG chunks to retrieve |
| `CHUNK_SIZE` | `800` | Text chunk size for splitting |
| `CHUNK_OVERLAP` | `100` | Overlap between chunks |
| `REPORTS_DIR` | `./reports` | Output directory for reports |
| `IMAGES_DIR` | `./images` | Saved uploaded images |

---

## Supported Crops & Diseases

The knowledge base covers:

**Crops:** Tomato, Wheat, Rice, Maize/Corn, Cotton, Potato, and more

**Diseases detected:**
- Fungal: Early Blight, Late Blight, Powdery Mildew, Rust, Fusarium Wilt
- Bacterial: Bacterial Leaf Blight, Bacterial Wilt
- Viral: Mosaic Virus, Leaf Curl
- Abiotic: Nutrient deficiencies, drought/water stress

---

## Output Reports

Each analysis generates three files in `reports/`:

| File | Format | Contents |
|------|--------|----------|
| `agri_report_<crop>_<timestamp>.pdf` | PDF (A4) | Full formatted report with tables, action plan |
| `agri_report_<crop>_<timestamp>.md` | Markdown | Same content, text format |
| `agri_report_<crop>_<timestamp>.json` | JSON | Raw structured data from all agents |

---

## Adding Custom Knowledge

1. Add `.md`, `.txt`, or `.pdf` files to `rag/documents/`
2. Re-run the ingestion: `python rag/ingest.py`
3. The new content will be available immediately

Example sources to add:
- Local extension service guides
- Crop-specific disease management handbooks
- Fertilizer recommendations for your region
- Local pest calendars

---

## Future Improvements

- [ ] Real-time weather integration for dynamic irrigation scheduling
- [ ] Soil sensor data input for precision fertilizer recommendations
- [ ] Multi-image batch processing
- [ ] Mobile app via Streamlit Cloud
- [ ] Multi-language support (Hindi, Spanish, Swahili, etc.)
- [ ] Satellite NDVI integration for field-level health mapping
- [ ] Historical analysis tracking per farm/field
- [ ] SMS/WhatsApp report delivery
- [ ] Audio output for low-literacy farmers

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Agent Framework | Google ADK (`google-adk`) |
| LLM | Gemini 2.5 Flash |
| Vision | Gemini Vision API |
| Embeddings | Google Generative AI `embedding-001` |
| Vector Store | ChromaDB |
| Document Processing | LangChain + langchain-text-splitters |
| PDF Generation | ReportLab |
| Web UI | Streamlit |
| Image Processing | Pillow |

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

*Built with ❤️ for farmers worldwide. AI recommendations should be verified by a certified agronomist before applying chemical treatments.*
