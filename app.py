"""
Agri AI Multi-Agent Assistant — main entry point.

Run modes:
    python app.py                        # interactive CLI
    python app.py --image path/to/img   # analyse a single image
    streamlit run ui/streamlit_app.py   # launch the Streamlit UI
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("agri_ai")


# ── Validation ────────────────────────────────────────────────────────────────

def _validate_environment() -> None:
    """Check required environment variables are set."""
    api_key = os.getenv("GOOGLE_API_KEY", "")
    if not api_key or api_key == "your_gemini_api_key_here":
        logger.error(
            "GOOGLE_API_KEY is not set. Copy .env.example to .env and add your key."
        )
        sys.exit(1)
    logger.info("Environment OK · model=%s", os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))


def _check_vector_store() -> bool:
    """Return True if the ChromaDB vector store has been built."""
    persist_dir = Path(os.getenv("CHROMA_PERSIST_DIR", "./rag/vector_store"))
    if not persist_dir.exists():
        return False
    return any(persist_dir.iterdir())


# ── CLI analysis ──────────────────────────────────────────────────────────────

async def analyse_image_async(image_path: str) -> dict:
    """Run the full orchestrator pipeline on a single image."""
    from agents.orchestrator import OrchestratorAgent

    orchestrator = OrchestratorAgent()

    def progress(msg: str, pct: int) -> None:
        logger.info("[%3d%%] %s", pct, msg)

    return await orchestrator.run(image_path, progress_callback=progress)


def analyse_image(image_path: str) -> dict:
    """Synchronous wrapper for analyse_image_async."""
    return asyncio.run(analyse_image_async(image_path))


# ── Interactive CLI ───────────────────────────────────────────────────────────

def interactive_cli() -> None:
    """Run the assistant in interactive mode, prompting for an image path."""
    print("\n" + "=" * 60)
    print("  🌿 Agri AI Multi-Agent Assistant")
    print("=" * 60)
    print("  Powered by Google ADK · Gemini 2.5 Flash · ChromaDB RAG")
    print("=" * 60 + "\n")

    if not _check_vector_store():
        print("⚠️  Knowledge base not found.")
        print("   Run first: python rag/ingest.py\n")

    while True:
        image_path = input("Enter crop image path (or 'quit' to exit): ").strip()

        if image_path.lower() in ("quit", "q", "exit"):
            print("Goodbye! 🌾")
            break

        if not image_path:
            continue

        path = Path(image_path)
        if not path.exists():
            print(f"❌ File not found: {image_path}\n")
            continue

        print(f"\n🔍 Analysing: {path.name}")
        print("-" * 40)

        result = analyse_image(str(path))

        if result.get("success"):
            vision = result.get("vision_result", {})
            recs = result.get("recommendations", {})

            print(f"\n✅ Analysis Complete")
            print(f"   Crop      : {vision.get('crop', 'Unknown')}")
            print(f"   Disease   : {vision.get('disease', 'Unknown')}")
            print(f"   Confidence: {vision.get('confidence', 0)}%")
            print(f"   Severity  : {vision.get('severity', 'N/A')}")
            print(f"   Urgency   : {recs.get('urgency', 'N/A')}")

            fertilizer = recs.get("fertilizer", {})
            if fertilizer:
                print(f"\n   Fertilizer: {fertilizer.get('primary', 'N/A')}")

            irrigation = recs.get("irrigation", {})
            if irrigation:
                print(f"   Irrigation: {irrigation.get('frequency', 'N/A')}")

            if result.get("pdf_path"):
                print(f"\n   📄 PDF Report: {result['pdf_path']}")
            if result.get("markdown_path"):
                print(f"   📝 Markdown : {result['markdown_path']}")
            if result.get("json_path"):
                print(f"   🗂️ JSON     : {result['json_path']}")

            elapsed = result.get("elapsed_seconds", 0)
            print(f"\n   ⏱ Completed in {elapsed}s\n")
        else:
            print(f"\n❌ Analysis failed: {result.get('error', 'Unknown error')}\n")

        print("-" * 40 + "\n")


# ── Argument parsing ──────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="agri-ai",
        description="Agri AI Multi-Agent Assistant — crop analysis powered by Google ADK",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python app.py                              # interactive mode
  python app.py --image photos/tomato.jpg   # single image analysis
  python app.py --image crop.png --json     # output raw JSON
  streamlit run ui/streamlit_app.py         # launch Streamlit UI
""",
    )
    parser.add_argument(
        "--image", "-i",
        metavar="PATH",
        help="Path to the crop image to analyse",
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Print the full result as JSON (implies --image)",
    )
    parser.add_argument(
        "--ingest",
        action="store_true",
        help="Build / rebuild the RAG vector store and exit",
    )
    parser.add_argument(
        "--ui",
        action="store_true",
        help="Launch the Streamlit UI (equivalent to: streamlit run ui/streamlit_app.py)",
    )
    return parser.parse_args()


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    args = parse_args()
    _validate_environment()

    if args.ingest:
        from rag.ingest import run_ingestion
        run_ingestion()
        return

    if args.ui:
        import subprocess
        ui_path = Path(__file__).parent / "ui" / "streamlit_app.py"
        subprocess.run([sys.executable, "-m", "streamlit", "run", str(ui_path)], check=True)
        return

    if args.image:
        image_path = args.image
        if not Path(image_path).exists():
            logger.error("Image not found: %s", image_path)
            sys.exit(1)

        logger.info("Analysing: %s", image_path)
        result = analyse_image(image_path)

        if args.json:
            print(json.dumps(result, indent=2))
        else:
            if result.get("success"):
                vision = result.get("vision_result", {})
                recs = result.get("recommendations", {})
                print(f"\n✅ Analysis complete")
                print(f"   Crop    : {vision.get('crop')}")
                print(f"   Disease : {vision.get('disease')}")
                print(f"   PDF     : {result.get('pdf_path', 'N/A')}")
            else:
                print(f"❌ Failed: {result.get('error')}")
                sys.exit(1)
        return

    interactive_cli()


if __name__ == "__main__":
    main()
