"""Streamlit UI for the Agri AI Multi-Agent Assistant."""

import json
import logging
import os
import sys
import time
from pathlib import Path

import streamlit as st

# ── Ensure project root on sys.path ─────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Page configuration ───────────────────────────────────────────────────────
st.set_page_config(
    page_title="Agri AI Assistant",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    /* ── Global ── */
    .stApp { background-color: #F9FBF7; }

    /* ── Header ── */
    .main-header {
        background: linear-gradient(135deg, #1B5E20 0%, #388E3C 60%, #66BB6A 100%);
        padding: 2rem 2.5rem;
        border-radius: 16px;
        margin-bottom: 1.5rem;
        color: white;
    }
    .main-header h1 { font-size: 2.4rem; margin: 0; font-weight: 800; color: white; }
    .main-header p  { font-size: 1.0rem; margin: 0.4rem 0 0; color: #C8E6C9; }

    /* ── Metric cards ── */
    .metric-card {
        background: white;
        border-radius: 12px;
        padding: 1.2rem 1.4rem;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        border-left: 4px solid #388E3C;
        margin-bottom: 0.8rem;
    }
    .metric-card.warning { border-left-color: #FF8F00; }
    .metric-card.danger  { border-left-color: #C62828; }
    .metric-card h3 { margin: 0 0 0.2rem; font-size: 0.78rem; color: #757575; text-transform: uppercase; letter-spacing: 0.05em; }
    .metric-card p  { margin: 0; font-size: 1.3rem; font-weight: 700; color: #1B5E20; }

    /* ── Section headers ── */
    .section-title {
        color: #1B5E20;
        font-size: 1.15rem;
        font-weight: 700;
        border-bottom: 2px solid #C8E6C9;
        padding-bottom: 0.4rem;
        margin: 1.2rem 0 0.8rem;
    }

    /* ── Urgency badges ── */
    .badge {
        display: inline-block;
        padding: 0.2rem 0.8rem;
        border-radius: 20px;
        font-size: 0.85rem;
        font-weight: 600;
    }
    .badge.low      { background: #C8E6C9; color: #1B5E20; }
    .badge.medium   { background: #FFE082; color: #E65100; }
    .badge.high     { background: #FFCC80; color: #BF360C; }
    .badge.critical { background: #FFCDD2; color: #B71C1C; }

    /* ── Upload area ── */
    .upload-box {
        background: white;
        border: 2px dashed #A5D6A7;
        border-radius: 12px;
        padding: 2rem;
        text-align: center;
        margin-bottom: 1rem;
    }

    /* ── Download button ── */
    .stDownloadButton > button {
        background-color: #1B5E20 !important;
        color: white !important;
        border-radius: 8px !important;
        border: none !important;
        padding: 0.5rem 1.5rem !important;
        font-weight: 600 !important;
    }
    .stDownloadButton > button:hover { background-color: #388E3C !important; }

    /* ── Analyse button ── */
    .stButton > button {
        background-color: #388E3C;
        color: white;
        border-radius: 8px;
        border: none;
        padding: 0.6rem 2rem;
        font-size: 1rem;
        font-weight: 600;
        width: 100%;
        transition: background 0.2s;
    }
    .stButton > button:hover { background-color: #1B5E20; }

    /* ── Confidence bar ── */
    .conf-bar-bg { background: #E8F5E9; border-radius: 8px; height: 12px; }
    .conf-bar-fill { background: linear-gradient(90deg, #388E3C, #66BB6A); border-radius: 8px; height: 12px; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _urgency_badge(urgency: str) -> str:
    cls = urgency.lower() if urgency.lower() in ("low", "medium", "high", "critical") else "medium"
    return f'<span class="badge {cls}">{urgency}</span>'


def _confidence_bar(pct: int) -> str:
    colour = "#388E3C" if pct >= 80 else "#FF8F00" if pct >= 50 else "#C62828"
    return (
        f'<div class="conf-bar-bg">'
        f'<div class="conf-bar-fill" style="width:{pct}%; background:{colour};"></div>'
        f"</div>"
        f"<small>{pct}% confidence</small>"
    )


def _card(title: str, value: str, variant: str = "") -> str:
    return (
        f'<div class="metric-card {variant}">'
        f"<h3>{title}</h3><p>{value}</p></div>"
    )


def _section(title: str) -> None:
    st.markdown(f'<div class="section-title">{title}</div>', unsafe_allow_html=True)


def _load_orchestrator():
    """Lazy-import the orchestrator to avoid import errors on missing .env."""
    from agents.orchestrator import OrchestratorAgent
    return OrchestratorAgent()


def _save_uploaded_file(uploaded_file) -> str:
    """Save Streamlit UploadedFile to the images directory, return path."""
    from tools.image_tool import save_uploaded_image

    images_dir = str(PROJECT_ROOT / os.getenv("IMAGES_DIR", "images"))
    return save_uploaded_image(
        file_bytes=uploaded_file.read(),
        filename=uploaded_file.name,
        dest_dir=images_dir,
    )


# ── Sidebar ───────────────────────────────────────────────────────────────────

def render_sidebar() -> None:
    with st.sidebar:
        st.markdown("### 🌿 Agri AI Assistant")
        st.markdown("---")

        st.markdown("**How it works**")
        st.markdown(
            """
1. Upload a crop photo
2. Click **Analyse Crop**
3. The AI identifies the crop & disease
4. Recommendations are generated
5. Download your PDF report
"""
        )
        st.markdown("---")

        api_key = os.getenv("GOOGLE_API_KEY", "")
        if api_key and len(api_key) > 10:
            st.success("✅ Gemini API Key detected")
        else:
            st.error("❌ GOOGLE_API_KEY not set in .env")

        rag_dir = PROJECT_ROOT / os.getenv("CHROMA_PERSIST_DIR", "rag/vector_store")
        if rag_dir.exists() and any(rag_dir.iterdir()):
            st.success("✅ Knowledge base ready")
        else:
            st.warning("⚠️ Knowledge base not built")
            st.caption("Run: `python rag/ingest.py`")

        st.markdown("---")
        st.markdown("**Supported crops**")
        st.markdown("Tomato · Wheat · Rice · Maize · Cotton · Potato · and more")
        st.markdown("---")
        st.caption("Powered by Google ADK · Gemini 2.5 Flash · ChromaDB")


# ── Main result display ───────────────────────────────────────────────────────

def render_results(result: dict) -> None:
    if not result.get("success"):
        st.error(f"Analysis failed: {result.get('error', 'Unknown error')}")
        return

    vision = result.get("vision_result", {})
    recs = result.get("recommendations", {})
    summary = result.get("report_summary", {})
    rag_context = result.get("rag_context", "")

    crop = vision.get("crop", "Unknown")
    disease = vision.get("disease", "Unknown")
    confidence = int(vision.get("confidence", 0))
    severity = vision.get("severity", "N/A")
    urgency = recs.get("urgency", "Medium")
    affected = vision.get("affected_parts", [])
    notes = vision.get("additional_notes", "")

    # ── Top metric cards ──────────────────────────────────────────────────────
    _section("Crop Analysis Results")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(_card("🌱 Crop Identified", crop), unsafe_allow_html=True)
    with c2:
        variant = "warning" if disease != "Healthy" else ""
        st.markdown(_card("🦠 Disease / Condition", disease, variant), unsafe_allow_html=True)
    with c3:
        st.markdown(_card("📊 Severity", severity), unsafe_allow_html=True)
    with c4:
        urgency_variant = "danger" if urgency in ("High", "Critical") else ("warning" if urgency == "Medium" else "")
        st.markdown(_card("⚡ Urgency", urgency, urgency_variant), unsafe_allow_html=True)

    st.markdown(_confidence_bar(confidence), unsafe_allow_html=True)

    if affected:
        st.caption(f"Affected parts: {', '.join(affected)}")
    if notes:
        st.info(f"💡 {notes}")

    # ── Executive Summary ─────────────────────────────────────────────────────
    exec_summary = summary.get("executive_summary", recs.get("disease_explanation", ""))
    if exec_summary:
        _section("Executive Summary")
        st.markdown(exec_summary)

    # ── Recommendations ───────────────────────────────────────────────────────
    _section("Agricultural Recommendations")

    tab_fert, tab_irr, tab_treat, tab_prev, tab_org = st.tabs(
        ["🧪 Fertilizer", "💧 Irrigation", "🩺 Treatment", "🛡️ Prevention", "🌱 Organic"]
    )

    fertilizer = recs.get("fertilizer", {})
    with tab_fert:
        if fertilizer:
            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown(f"**Primary Fertilizer:** {fertilizer.get('primary', 'N/A')}")
                st.markdown(f"**Application Rate:** {fertilizer.get('application_rate', 'N/A')}")
                st.markdown(f"**Frequency:** {fertilizer.get('frequency', 'N/A')}")
            with col_b:
                st.markdown(f"**Secondary Supplement:** {fertilizer.get('secondary', 'N/A')}")
                st.markdown(f"**Notes:** {fertilizer.get('notes', 'N/A')}")
        else:
            st.info("No fertilizer data available.")

    irrigation = recs.get("irrigation", {})
    with tab_irr:
        if irrigation:
            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown(f"**Frequency:** {irrigation.get('frequency', 'N/A')}")
                st.markdown(f"**Amount per Session:** {irrigation.get('amount', 'N/A')}")
            with col_b:
                st.markdown(f"**Timing:** {irrigation.get('timing', 'N/A')}")
                st.markdown(f"**Method:** {irrigation.get('method', 'N/A')}")
            if irrigation.get("notes"):
                st.caption(f"ℹ️ {irrigation['notes']}")
        else:
            st.info("No irrigation data available.")

    treatment_steps = recs.get("treatment_steps", [])
    with tab_treat:
        if treatment_steps:
            for i, step in enumerate(treatment_steps, 1):
                st.markdown(f"**{i}.** {step}")
        else:
            st.info("No treatment steps available.")

    prevention = recs.get("prevention", [])
    with tab_prev:
        if prevention:
            for item in prevention:
                st.markdown(f"• {item}")
        else:
            st.info("No prevention data available.")

    organics = recs.get("organic_alternatives", [])
    with tab_org:
        if organics:
            for item in organics:
                st.markdown(f"🌿 {item}")
        else:
            st.info("No organic alternatives available.")

    # ── Action Plan ───────────────────────────────────────────────────────────
    action_plan = summary.get("action_plan", [])
    if action_plan:
        _section("Prioritised Action Plan")
        for item in action_plan:
            u = item.get("urgency", "Medium")
            badge = _urgency_badge(u)
            st.markdown(
                f"**{item.get('priority', '')}. {item.get('action', '')}** "
                f"— _{item.get('timeline', 'ASAP')}_ {badge}",
                unsafe_allow_html=True,
            )

    # ── Yield Risk ────────────────────────────────────────────────────────────
    risk = summary.get("risk_summary", recs.get("estimated_yield_impact", ""))
    if risk:
        _section("Risk Assessment")
        st.warning(f"⚠️ **Yield Impact:** {risk}")

    # ── RAG Knowledge (expandable) ────────────────────────────────────────────
    if rag_context:
        with st.expander("📚 Agricultural Knowledge Retrieved (RAG)", expanded=False):
            st.markdown(
                "*The following information was retrieved from the knowledge base and informed this analysis:*"
            )
            st.markdown(rag_context)

    # ── Download section ──────────────────────────────────────────────────────
    _section("Download Reports")

    dl_col1, dl_col2, dl_col3 = st.columns(3)

    pdf_path = result.get("pdf_path", "")
    if pdf_path and Path(pdf_path).exists():
        with dl_col1:
            with open(pdf_path, "rb") as f:
                st.download_button(
                    label="📄 Download PDF Report",
                    data=f.read(),
                    file_name=Path(pdf_path).name,
                    mime="application/pdf",
                )

    md_path = result.get("markdown_path", "")
    if md_path and Path(md_path).exists():
        with dl_col2:
            md_text = Path(md_path).read_text(encoding="utf-8")
            st.download_button(
                label="📝 Download Markdown",
                data=md_text,
                file_name=Path(md_path).name,
                mime="text/markdown",
            )

    json_path = result.get("json_path", "")
    if json_path and Path(json_path).exists():
        with dl_col3:
            json_text = Path(json_path).read_text(encoding="utf-8")
            st.download_button(
                label="🗂️ Download JSON",
                data=json_text,
                file_name=Path(json_path).name,
                mime="application/json",
            )

    elapsed = result.get("elapsed_seconds")
    if elapsed:
        st.caption(f"⏱ Analysis completed in {elapsed}s")


# ── Main app ──────────────────────────────────────────────────────────────────

def main() -> None:
    render_sidebar()

    # ── Header ───────────────────────────────────────────────────────────────
    st.markdown(
        """
        <div class="main-header">
            <h1>🌿 Agri AI Assistant</h1>
            <p>AI-powered crop disease detection & agricultural recommendations · Powered by Google ADK & Gemini 2.5 Flash</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Layout ────────────────────────────────────────────────────────────────
    left_col, right_col = st.columns([1, 1.8], gap="large")

    with left_col:
        st.markdown("#### Upload Crop Image")

        uploaded_file = st.file_uploader(
            label="Drop an image here",
            type=["jpg", "jpeg", "png", "bmp", "webp"],
            label_visibility="collapsed",
            help="Supported: JPG, PNG, BMP, WebP · Max size: 200MB",
        )

        if uploaded_file:
            st.image(uploaded_file, caption=uploaded_file.name, use_container_width=True)
            st.caption(f"📁 {uploaded_file.name} · {uploaded_file.size / 1024:.1f} KB")

            analyse_clicked = st.button("🔍 Analyse Crop", type="primary", use_container_width=True)
        else:
            st.markdown(
                """
                <div class="upload-box">
                    <p style="font-size:2.5rem; margin:0">🌾</p>
                    <p style="color:#757575; margin:0.5rem 0 0">Upload a crop photo to begin</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            analyse_clicked = False

    with right_col:
        if "result" in st.session_state and st.session_state.result:
            render_results(st.session_state.result)
        elif not uploaded_file:
            st.markdown("#### How to use")
            steps = [
                ("1️⃣", "Upload a crop image on the left", "JPG, PNG, WebP — any photo from your field"),
                ("2️⃣", "Click **Analyse Crop**", "The AI agents will run the full analysis pipeline"),
                ("3️⃣", "Review results", "Crop ID, disease detection, recommendations & action plan"),
                ("4️⃣", "Download your report", "PDF, Markdown, or JSON — take it to the field"),
            ]
            for icon, title, desc in steps:
                with st.container():
                    st.markdown(f"**{icon} {title}**")
                    st.caption(desc)
                    st.markdown("")
        else:
            st.info("Click **Analyse Crop** to start the analysis.")

    # ── Analysis execution ────────────────────────────────────────────────────
    if analyse_clicked and uploaded_file:
        with right_col:
            progress_placeholder = st.empty()
            status_placeholder = st.empty()

            progress_bar = progress_placeholder.progress(0)
            status_text = status_placeholder.text("Initialising analysis pipeline...")

            def update_progress(msg: str, pct: int) -> None:
                progress_bar.progress(pct)
                status_text.text(msg)

            try:
                image_path = _save_uploaded_file(uploaded_file)
                update_progress("Image saved. Loading AI agents...", 10)

                orchestrator = _load_orchestrator()
                result = orchestrator.run_sync(image_path, progress_callback=update_progress)

                progress_placeholder.empty()
                status_placeholder.empty()

                st.session_state.result = result

                if result.get("success"):
                    st.success("✅ Analysis complete!")
                else:
                    st.error(f"Analysis encountered an error: {result.get('error')}")

                st.rerun()

            except Exception as exc:
                progress_placeholder.empty()
                status_placeholder.empty()
                st.error(f"Unexpected error: {exc}")
                logger.error("UI analysis error: %s", exc, exc_info=True)

    # ── Reset button ──────────────────────────────────────────────────────────
    if "result" in st.session_state and st.session_state.result:
        with left_col:
            if st.button("🔄 Analyse Another Image", use_container_width=True):
                del st.session_state["result"]
                st.rerun()


if __name__ == "__main__":
    main()
