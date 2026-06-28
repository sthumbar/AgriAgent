"""
RAG ingestion pipeline — loads documents from rag/documents/, splits them,
embeds with Google Generative AI, and stores vectors in ChromaDB.

Usage:
    python rag/ingest.py
"""

import logging
import os
import sys
from pathlib import Path

# ── Ensure project root is on sys.path ───────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

import chromadb
from chromadb.config import Settings
from langchain.schema import Document
from langchain_community.document_loaders import (
    DirectoryLoader,
    TextLoader,
    UnstructuredMarkdownLoader,
)
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("rag.ingest")

# ── Configuration ────────────────────────────────────────────────────────────
DOCUMENTS_DIR = Path(os.getenv("RAG_DOCUMENTS_DIR", str(PROJECT_ROOT / "rag" / "documents")))
PERSIST_DIR = Path(os.getenv("CHROMA_PERSIST_DIR", str(PROJECT_ROOT / "rag" / "vector_store")))
COLLECTION_NAME = os.getenv("RAG_COLLECTION_NAME", "agri_knowledge")
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "800"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "100"))


# ── Document loading ─────────────────────────────────────────────────────────

def load_documents() -> list[Document]:
    """
    Load all supported documents from the documents directory.

    Supports: .md, .txt, .pdf
    """
    if not DOCUMENTS_DIR.exists():
        raise FileNotFoundError(f"Documents directory not found: {DOCUMENTS_DIR}")

    documents: list[Document] = []

    md_files = list(DOCUMENTS_DIR.glob("**/*.md"))
    txt_files = list(DOCUMENTS_DIR.glob("**/*.txt"))

    for filepath in md_files + txt_files:
        try:
            loader = TextLoader(str(filepath), encoding="utf-8")
            docs = loader.load()
            for doc in docs:
                doc.metadata["source"] = filepath.name
                doc.metadata["type"] = filepath.suffix.lstrip(".")
            documents.extend(docs)
            logger.info("Loaded: %s (%d chars)", filepath.name, sum(len(d.page_content) for d in docs))
        except Exception as exc:
            logger.warning("Failed to load %s: %s", filepath.name, exc)

    try:
        from langchain_community.document_loaders import PyPDFLoader

        pdf_files = list(DOCUMENTS_DIR.glob("**/*.pdf"))
        for filepath in pdf_files:
            try:
                loader = PyPDFLoader(str(filepath))
                docs = loader.load()
                for doc in docs:
                    doc.metadata["source"] = filepath.name
                    doc.metadata["type"] = "pdf"
                documents.extend(docs)
                logger.info("Loaded PDF: %s (%d pages)", filepath.name, len(docs))
            except Exception as exc:
                logger.warning("Failed to load PDF %s: %s", filepath.name, exc)
    except ImportError:
        logger.debug("pypdf not installed — PDF loading skipped")

    return documents


# ── Text splitting ───────────────────────────────────────────────────────────

def split_documents(documents: list[Document]) -> list[Document]:
    """Split documents into smaller chunks for embedding."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n---\n\n", "\n\n### ", "\n\n## ", "\n\n# ", "\n\n", "\n", " ", ""],
        length_function=len,
    )
    chunks = splitter.split_documents(documents)
    logger.info("Split %d documents into %d chunks (size=%d, overlap=%d)",
                len(documents), len(chunks), CHUNK_SIZE, CHUNK_OVERLAP)
    return chunks


# ── Embedding & storage ──────────────────────────────────────────────────────

def get_embeddings() -> GoogleGenerativeAIEmbeddings:
    """Return Google Generative AI embeddings model."""
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise EnvironmentError("GOOGLE_API_KEY environment variable is not set.")

    return GoogleGenerativeAIEmbeddings(
        model="models/embedding-001",
        google_api_key=api_key,
        task_type="retrieval_document",
    )


def store_in_chromadb(chunks: list[Document]) -> chromadb.Collection:
    """Embed documents and store them in ChromaDB."""
    PERSIST_DIR.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(
        path=str(PERSIST_DIR),
        settings=Settings(anonymized_telemetry=False),
    )

    # Delete existing collection for a clean rebuild
    existing = [c.name for c in client.list_collections()]
    if COLLECTION_NAME in existing:
        client.delete_collection(COLLECTION_NAME)
        logger.info("Deleted existing collection '%s'", COLLECTION_NAME)

    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    embeddings_model = get_embeddings()

    logger.info("Embedding %d chunks with Google Generative AI...", len(chunks))
    texts = [chunk.page_content for chunk in chunks]
    metadatas = [chunk.metadata for chunk in chunks]

    # Embed in batches to avoid rate limits
    batch_size = 50
    all_embeddings: list[list[float]] = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        batch_embeddings = embeddings_model.embed_documents(batch)
        all_embeddings.extend(batch_embeddings)
        logger.info(
            "Embedded batch %d/%d (%d chunks)",
            i // batch_size + 1,
            (len(texts) - 1) // batch_size + 1,
            len(batch),
        )

    ids = [f"chunk_{i}" for i in range(len(texts))]
    collection.add(
        ids=ids,
        documents=texts,
        embeddings=all_embeddings,
        metadatas=metadatas,
    )

    logger.info(
        "Stored %d chunks in ChromaDB collection '%s' at %s",
        len(texts),
        COLLECTION_NAME,
        PERSIST_DIR,
    )
    return collection


# ── Main ─────────────────────────────────────────────────────────────────────

def run_ingestion() -> None:
    """Execute the full ingestion pipeline."""
    logger.info("=" * 60)
    logger.info("Agri AI RAG Ingestion Pipeline")
    logger.info("Documents dir : %s", DOCUMENTS_DIR)
    logger.info("Vector store  : %s", PERSIST_DIR)
    logger.info("Collection    : %s", COLLECTION_NAME)
    logger.info("=" * 60)

    documents = load_documents()
    if not documents:
        logger.error(
            "No documents found in %s. "
            "Add .md, .txt, or .pdf files and re-run.",
            DOCUMENTS_DIR,
        )
        sys.exit(1)

    logger.info("Total document content: %d chars", sum(len(d.page_content) for d in documents))

    chunks = split_documents(documents)
    collection = store_in_chromadb(chunks)

    logger.info("Ingestion complete. Collection count: %d", collection.count())
    logger.info("Run `python app.py` or `streamlit run ui/streamlit_app.py` to start the app.")


if __name__ == "__main__":
    run_ingestion()
