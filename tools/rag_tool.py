"""RAG retrieval tool — queries ChromaDB for agricultural knowledge."""

import logging
import os
from typing import List, Optional

import chromadb
from chromadb.config import Settings
from langchain_google_genai import GoogleGenerativeAIEmbeddings

logger = logging.getLogger(__name__)

_DEFAULT_COLLECTION = os.getenv("RAG_COLLECTION_NAME", "agri_knowledge")
_DEFAULT_TOP_K = int(os.getenv("RAG_TOP_K", "3"))
_DEFAULT_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./rag/vector_store")


class RAGRetriever:
    """Thread-safe wrapper around a ChromaDB collection for agricultural knowledge retrieval."""

    def __init__(
        self,
        persist_dir: str = _DEFAULT_PERSIST_DIR,
        collection_name: str = _DEFAULT_COLLECTION,
    ) -> None:
        self._persist_dir = persist_dir
        self._collection_name = collection_name
        self._client: Optional[chromadb.PersistentClient] = None
        self._collection: Optional[chromadb.Collection] = None
        self._embeddings: Optional[GoogleGenerativeAIEmbeddings] = None

    # ── Lazy initialisation ──────────────────────────────────────────────────

    def _get_embeddings(self) -> GoogleGenerativeAIEmbeddings:
        if self._embeddings is None:
            self._embeddings = GoogleGenerativeAIEmbeddings(
                model="models/embedding-001",
                google_api_key=os.getenv("GOOGLE_API_KEY"),
            )
        return self._embeddings

    def _get_collection(self) -> chromadb.Collection:
        if self._client is None:
            self._client = chromadb.PersistentClient(
                path=self._persist_dir,
                settings=Settings(anonymized_telemetry=False),
            )
        if self._collection is None:
            try:
                self._collection = self._client.get_collection(self._collection_name)
                logger.debug("Loaded ChromaDB collection '%s'", self._collection_name)
            except Exception as exc:
                raise RuntimeError(
                    f"ChromaDB collection '{self._collection_name}' not found. "
                    "Run `python rag/ingest.py` to build the vector store."
                ) from exc
        return self._collection

    # ── Public API ───────────────────────────────────────────────────────────

    def is_available(self) -> bool:
        """Return True if the vector store exists and has documents."""
        try:
            col = self._get_collection()
            return col.count() > 0
        except Exception:
            return False

    def retrieve(self, query: str, top_k: int = _DEFAULT_TOP_K) -> List[str]:
        """
        Retrieve the top-k most relevant text chunks for the given query.

        Args:
            query: Free-text query describing what knowledge is needed.
            top_k: Number of chunks to return.

        Returns:
            List of relevant text chunks; empty list if store is unavailable.
        """
        if not self.is_available():
            logger.warning("Vector store unavailable — skipping RAG retrieval")
            return []

        try:
            embeddings = self._get_embeddings()
            query_embedding = embeddings.embed_query(query)

            collection = self._get_collection()
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=min(top_k, collection.count()),
                include=["documents", "distances"],
            )

            documents: List[str] = results.get("documents", [[]])[0]
            distances: List[float] = results.get("distances", [[]])[0]

            logger.info(
                "RAG retrieved %d chunks for query '%s...' (distances: %s)",
                len(documents),
                query[:60],
                [round(d, 3) for d in distances],
            )
            return documents

        except Exception as exc:
            logger.error("RAG retrieval failed: %s", exc)
            return []

    def retrieve_as_context(self, query: str, top_k: int = _DEFAULT_TOP_K) -> str:
        """
        Retrieve chunks and format them as a single context string.

        Returns an empty string if the store is unavailable.
        """
        chunks = self.retrieve(query, top_k)
        if not chunks:
            return ""

        sections = []
        for i, chunk in enumerate(chunks, 1):
            sections.append(f"[Knowledge Chunk {i}]\n{chunk.strip()}")

        return "\n\n".join(sections)


# Module-level singleton — shared across agents
_retriever = RAGRetriever()


def retrieve_agricultural_knowledge(query: str) -> str:
    """
    ADK-compatible tool: retrieve relevant agricultural knowledge from the vector store.

    Args:
        query: What agricultural information to look up (disease, crop, treatment, etc.).

    Returns:
        Formatted context string with the top matching knowledge chunks,
        or a fallback message if the vector store is not yet built.
    """
    context = _retriever.retrieve_as_context(query)
    if not context:
        return (
            "No knowledge base context available. "
            "Run `python rag/ingest.py` to build the vector store, "
            "or proceed with general agronomic knowledge."
        )
    return context


def get_retriever() -> RAGRetriever:
    """Return the shared RAGRetriever singleton."""
    return _retriever
