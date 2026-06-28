# 🌿 Agri AI Multi-Agent Assistant

An AI-powered crop health analysis system built with **Google ADK**, **Gemini 2.5 Flash**, **ChromaDB RAG**, and a **Human-in-the-Loop (HITL) agronomist review** workflow via a custom MCP server.

Upload a crop image and receive instant disease detection, fertilizer recommendations, an irrigation schedule, and a downloadable PDF report — with automatic escalation to an agronomist when AI confidence is low.

---

## Table of Contents

1. [Architecture](#architecture)
2. [Project Structure](#project-structure)
3. [Prerequisites](#prerequisites)
4. [Installation](#installation)
5. [Configuration](#configuration)
6. [Build the Knowledge Base (RAG)](#build-the-knowledge-base-rag)
7. [Running the Application](#running-the-application)
8. [Human-in-the-Loop (HITL) Review](#human-in-the-loop-hitl-review)
9. [MCP Server](#mcp-server)
10. [ADK Skills](#adk-skills)
11. [Output Reports](#output-reports)
12. [Adding Custom Knowledge](#adding-custom-knowledge)
13. [Environment Variables Reference](#environment-variables-reference)
14. [Supported Crops & Diseases](#supported-crops--diseases)
15. [Tech Stack](#tech-stack)
16. [Troubleshooting](#troubleshooting)
17. [Future Improvements](#future-improvements)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Streamlit UI / CLI                           │
└─────────────────────────────┬───────────────────────────────────────┘
                              │ image path
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       Orchestrator Agent                            │
│           (google.adk — coordinates the full pipeline)             │
└────────┬───────────────────────┬──────────────────┬────────────────┘
         │                       │                  │
         ▼                       ▼                  ▼
┌─────────────────┐  ┌───────────────────────┐  ┌──────────────────┐
│  Vision Agent   │  │  Recommendation Agent │  │  Report Agent    │
│                 │  │                       │  │                  │
│  Gemini Vision  │  │  RAG (ChromaDB)       │  │  ReportLab PDF   │
│  identify_crop  │  │  recommendations.md   │  │  report.md skill │
│  .md skill      │  │  rag_tool.py          │  │                  │
└────────┬────────┘  └──────────┬────────────┘  └────────┬─────────┘
         │                      │                         │
         ▼                      ▼                         ▼
  {crop, disease,        {fertilizer,              {pdf_path,
   confidence,            irrigation,               md_path,
   severity}              treatment,                json_path}
                          prevention}
         │
         │ confidence < threshold?
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│            HITL Gate — Agronomist Review MCP Server                 │
│                                                                     │
│  submit_for_review()  →  SQLite queue  →  Streamlit Dashboard       │
│  add_expert_note()    →  approve / reject / needs_more_info         │
│  run_from_vision_result() resumes pipeline after approval           │
└─────────────────────────────────────────────────────────────────────┘
```

### Agents

| Agent | Responsibility | Key Tool |
|---|---|---|
| **Orchestrator** | Coordinates pipeline; enforces HITL confidence gate | `submit_for_review` |
| **Vision Agent** | Identifies crop species and detects disease from image | `analyze_crop_image` |
| **Recommendation Agent** | Generates fertilizer, irrigation, and treatment advice via RAG | `get_crop_recommendations` |
| **Report Agent** | Creates executive summary, action plan, PDF, and Markdown | `create_report_files` |

---

## Project Structure

```
AgriAgent/
├── app.py                            ← CLI entry point
├── requirements.txt
├── .env.example
├── README.md
│
├── agents/
│   ├── orchestrator.py               ← Pipeline coordinator + HITL confidence gate
│   ├── vision_agent.py               ← Gemini Vision crop/disease detection
│   ├── recommendation_agent.py       ← RAG-backed agronomic recommendations
│   └── report_agent.py               ← PDF + Markdown report generation
│
├── skills/                           ← Agent system prompts (markdown)
│   ├── identify_crop.md              ← Vision agent persona & output schema
│   ├── recommendations.md            ← Agronomist persona & recommendation schema
│   └── report.md                     ← Report writer persona & report schema
│
├── tools/
│   ├── image_tool.py                 ← Image loading, validation, resize
│   ├── rag_tool.py                   ← ChromaDB retrieval wrapper
│   ├── pdf_tool.py                   ← ReportLab PDF generation
│   └── review_tool.py                ← SQLite review queue (HITL backend)
│
├── mcp_servers/
│   └── agronomist_review_server.py   ← Custom MCP server for agronomist review
│
├── rag/
│   ├── documents/                    ← Source knowledge base (.md, .txt, .pdf)
│   │   └── agricultural_knowledge.md
│   ├── vector_store/                 ← ChromaDB persistent store (auto-created)
│   ├── review_queue.db               ← SQLite review queue (auto-created)
│   └── ingest.py                     ← Build / rebuild vector store
│
├── ui/
│   └── streamlit_app.py              ← Streamlit web interface + agronomist dashboard
│
├── reports/                          ← Generated PDF/MD/JSON reports (auto-created)
└── images/                           ← Uploaded crop images (auto-created)
```

---

## Prerequisites

- Python 3.10 or higher
- A Google Gemini API key — get one free at [Google AI Studio](https://aistudio.google.com/app/apikey)

---

## Installation

### Step 1 — Clone the repository

```bash
git clone https://github.com/your-username/AgriAgent.git
cd AgriAgent
```

### Step 2 — Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate        # macOS / Linux
.venv\Scripts\activate           # Windows
```

### Step 3 — Install dependencies

```bash
pip install -r requirements.txt
```

This installs all required packages including:
- `google-adk` — multi-agent orchestration framework
- `langchain-google-genai` — Gemini embeddings
- `chromadb` — vector store
- `streamlit` — web UI
- `reportlab` — PDF generation
- `mcp` — Model Context Protocol (custom MCP server)

---

## Configuration

### Step 4 — Create your `.env` file

```bash
cp .env.example .env
```

### Step 5 — Add your Gemini API key

Open `.env` and set:

```env
GOOGLE_API_KEY=your_actual_key_here
```

### Step 6 — (Optional) Adjust HITL confidence threshold

By default, any analysis with confidence below **60%** is automatically flagged for agronomist review. Adjust in `.env`:

```env
LOW_CONFIDENCE_THRESHOLD=60
```

To test the HITL review flow with a normal image, temporarily set this to `99` so every analysis is flagged.

---

## Build the Knowledge Base (RAG)

### Step 7 — Ingest agricultural documents into ChromaDB

Before running analyses, build the vector store from the included knowledge base:

```bash
python rag/ingest.py
```

Expected output:

```
15:14:37 [INFO] rag.ingest — Agri AI RAG Ingestion Pipeline
15:14:37 [INFO] rag.ingest — Loaded: agricultural_knowledge.md (12879 chars)
15:14:37 [INFO] rag.ingest — Split 1 documents into 27 chunks (size=800, overlap=100)
15:14:38 [INFO] rag.ingest — Embedded batch 1/1 (27 chunks)
15:14:38 [INFO] rag.ingest — Stored 27 chunks in ChromaDB collection 'agri_knowledge'
15:14:38 [INFO] rag.ingest — Ingestion complete. Collection count: 27
```

To add your own knowledge, drop `.md`, `.txt`, or `.pdf` files into `rag/documents/` and re-run `python rag/ingest.py`.

---

## Running the Application

### Step 8 — Launch the Streamlit web UI (recommended)

```bash
streamlit run ui/streamlit_app.py
```

Open **http://localhost:8501** in your browser.

**Standard analysis flow:**
1. Upload a crop photo (JPG, PNG, WebP, BMP)
2. Click **Analyse Crop**
3. View crop ID, disease detection, recommendations, and action plan
4. Download the PDF / Markdown / JSON report

### Alternative — Command-line interface

**Analyse a single image:**
```bash
python app.py --image path/to/crop.jpg
```

**Get raw JSON output:**
```bash
python app.py --image crop.jpg --json
```

**Launch UI via app.py:**
```bash
python app.py --ui
```

---

## Human-in-the-Loop (HITL) Review

When the Vision Agent's confidence falls below `LOW_CONFIDENCE_THRESHOLD` (default 60%), the pipeline automatically pauses and routes the case to the agronomist review queue instead of generating potentially incorrect recommendations.

### How it works

```
Low-confidence image uploaded
         ↓
Vision Agent → confidence = 42%
         ↓
Orchestrator detects confidence < 60%
         ↓
submit_for_review() → review_id = "A3F2B1C9"  (stored in SQLite)
         ↓
UI shows: ⚠️ "Flagged for Review — ID: A3F2B1C9"
         ↓
Sidebar shows: 👨‍🌾 Agronomist Dashboard (1)
         ↓
Agronomist opens dashboard → views pending case
         ↓
Corrects crop/disease if needed → adds expert note → clicks Approve
         ↓
Pipeline resumes: RAG → Recommendations → PDF
         ↓
Full report shown in main UI
```

### Step-by-step: reviewing a flagged case

1. After analysis, if you see the yellow **"Flagged for Review"** panel, note the Review ID
2. In the sidebar, click **👨‍🌾 Agronomist Dashboard** — a badge shows pending count
3. In the **Pending Reviews** tab, expand the case
4. Optionally correct the **Crop** and **Disease** fields (the AI's best guess is pre-filled)
5. Add an **Expert Note** (required) describing your observations
6. Choose an action:
   - **Approve & Generate Report** — resumes the pipeline with your corrections
   - **Reject** — marks the case as rejected (farmer will need to re-submit)
   - **Needs More Info** — requests a clearer image or additional context
7. On approval, the full recommendations and PDF report are generated and displayed immediately

### Review history

The **All Reviews** tab in the dashboard shows every review ever submitted with its final status.

---

## MCP Server

The agronomist review system is implemented as a **custom MCP (Model Context Protocol) server**, making it accessible to any MCP-compatible client — not just the Streamlit UI.

### Running the MCP server standalone

```bash
python mcp_servers/agronomist_review_server.py
```

The server communicates over stdio and exposes six tools:

| Tool | Description |
|---|---|
| `submit_for_review` | Queue a low-confidence analysis for expert review |
| `get_review_status` | Check status of a review by ID |
| `add_expert_note` | Record agronomist decision (approved / rejected / needs_more_info) |
| `get_full_analysis` | Retrieve the full stored analysis JSON (used to resume pipeline) |
| `list_pending_reviews` | List all cases awaiting review |
| `list_all_reviews` | Full history of all reviews |

### Connecting via Google ADK `MCPToolset`

```python
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, StdioServerParameters

review_tools = MCPToolset(
    connection_params=StdioServerParameters(
        command="python",
        args=["mcp_servers/agronomist_review_server.py"],
    )
)
```

### Using from Claude Code

With the MCP server running, Claude Code (or any MCP client) can call tools directly:

```bash
# List all pending reviews
python mcp_servers/agronomist_review_server.py
# then call: list_pending_reviews

# Approve a review
# call: add_expert_note with review_id, note, action="approved"
```

---

## ADK Skills

Skills are markdown files in `skills/` that serve as the system prompt for each agent. Editing a skill file changes agent behaviour without touching Python code.

| File | Agent | Purpose |
|---|---|---|
| `skills/identify_crop.md` | Vision Agent | Instructs Gemini Vision what to look for; enforces JSON output schema with crop, disease, confidence, severity, affected\_parts |
| `skills/recommendations.md` | Recommendation Agent | Senior agronomist persona; defines IPM principles, fertilizer/irrigation/treatment JSON schema, chemical safety rules |
| `skills/report.md` | Report Agent | Report writer persona; enforces executive summary, action plan, risk assessment, farmer-friendly language |

---

## Output Reports

Each successful analysis generates three files in `reports/`:

| File | Format | Contents |
|---|---|---|
| `agri_report_<crop>_<timestamp>.pdf` | PDF (A4) | Full formatted report with tables and prioritized action plan |
| `agri_report_<crop>_<timestamp>.md` | Markdown | Same content in text format |
| `agri_report_<crop>_<timestamp>.json` | JSON | Raw structured data from all agents |

---

## Adding Custom Knowledge

1. Add `.md`, `.txt`, or `.pdf` files to `rag/documents/`
2. Re-run ingestion:
   ```bash
   python rag/ingest.py
   ```
3. The new content is immediately available to the Recommendation Agent

**Useful sources to add:**
- Local agricultural extension service guides
- Crop-specific disease management handbooks
- Regional fertilizer recommendations
- Local pest calendars
- Organic farming certification guidelines

---

## Environment Variables Reference

| Variable | Default | Description |
|---|---|---|
| `GOOGLE_API_KEY` | _(required)_ | Your Gemini API key |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model for all agents |
| `CHROMA_PERSIST_DIR` | `./rag/vector_store` | ChromaDB storage path |
| `RAG_DOCUMENTS_DIR` | `./rag/documents` | Source knowledge documents |
| `RAG_COLLECTION_NAME` | `agri_knowledge` | ChromaDB collection name |
| `RAG_TOP_K` | `3` | Number of RAG chunks retrieved per query |
| `CHUNK_SIZE` | `800` | Text chunk size for document splitting |
| `CHUNK_OVERLAP` | `100` | Overlap between chunks |
| `REPORTS_DIR` | `./reports` | Output directory for generated reports |
| `IMAGES_DIR` | `./images` | Directory for saved uploaded images |
| `MAX_IMAGE_WIDTH` | `1024` | Max image width before resize |
| `MAX_IMAGE_HEIGHT` | `1024` | Max image height before resize |
| `LOW_CONFIDENCE_THRESHOLD` | `60` | Confidence % below which HITL review is triggered |
| `REVIEW_DB_PATH` | `rag/review_queue.db` | SQLite database for the review queue |

---

## Supported Crops & Diseases

**Crops:** Tomato, Wheat, Rice, Maize/Corn, Cotton, Potato, and more

**Diseases detected:**
- **Fungal:** Early Blight, Late Blight, Powdery Mildew, Downy Mildew, Rust, Fusarium Wilt
- **Bacterial:** Bacterial Leaf Blight, Bacterial Wilt, Crown Gall
- **Viral:** Mosaic Virus, Leaf Curl, Yellows Disease
- **Abiotic:** Nitrogen/Phosphorus/Potassium deficiency, drought stress, overwatering

---

## Tech Stack

| Component | Technology |
|---|---|
| Agent Framework | Google ADK (`google-adk`) |
| LLM / Vision | Gemini 2.5 Flash |
| Embeddings | `models/gemini-embedding-001` (Google Generative AI) |
| Vector Store | ChromaDB |
| Document Processing | LangChain (`langchain-core`, `langchain-text-splitters`) |
| PDF Generation | ReportLab |
| Web UI | Streamlit |
| Image Processing | Pillow |
| HITL Queue | SQLite (via `tools/review_tool.py`) |
| MCP Server | `mcp` Python package (stdio transport) |

---

## Troubleshooting

### `ModuleNotFoundError: No module named 'langchain.schema'`

`langchain.schema` was removed in newer LangChain versions. The import has been updated to:

```python
from langchain_core.documents import Document
```

If you see this error in your own code, apply the same fix.

---

### `404 NOT_FOUND: models/embedding-001 is not found`

Google deprecated `models/embedding-001` and `models/text-embedding-004`. This project now uses:

```python
model="models/gemini-embedding-001"
```

If the embedding step fails, run:

```bash
python -c "
import os; from dotenv import load_dotenv; load_dotenv('.env')
import google.genai as genai
client = genai.Client(api_key=os.getenv('GOOGLE_API_KEY'))
for m in client.models.list():
    if 'embed' in m.name.lower():
        print(m.name)
"
```

Copy the model name from the output and set it in `rag/ingest.py` and `agents/recommendation_agent.py`.

---

### HITL review does not trigger

Check that `LOW_CONFIDENCE_THRESHOLD` is set correctly in `.env`. To force the review flow for testing, set it to `99` so every analysis is flagged.

---

### Streamlit app shows a blank page

Make sure the knowledge base has been built before starting the UI:

```bash
python rag/ingest.py
streamlit run ui/streamlit_app.py
```

---

### `mcp` package not found

```bash
pip install "mcp>=1.0.0"
```

---

## Future Improvements

- [x] Human-in-the-Loop agronomist review via custom MCP server
- [ ] Real-time weather integration for dynamic irrigation scheduling
- [ ] Soil sensor data input for precision fertilizer recommendations
- [ ] Multi-image batch processing
- [ ] Mobile app via Streamlit Cloud
- [ ] Multi-language support (Hindi, Spanish, Swahili, etc.)
- [ ] Satellite NDVI integration for field-level health mapping
- [ ] Historical analysis tracking per farm/field via SQLite MCP server
- [ ] SMS/WhatsApp report delivery via notification MCP server
- [ ] Market price integration for yield-loss cost estimates
- [ ] Audio output for low-literacy farmers
- [ ] Pest calendar MCP server for seasonal disease alerts

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

*Built with care for farmers worldwide. AI recommendations should always be verified by a certified agronomist before applying chemical treatments.*
