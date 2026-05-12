"""
step3_vectorstore.py — BDD vectorielle ChromaDB + LangChain
============================================================
Remplace le SemanticVectorStore (pickle) par ChromaDB persisté.

Avantages vs pickle :
  - Filtres natifs sur les métadonnées (notion, difficulte, niveau...)
  - Ajout/suppression de chunks sans tout recharger
  - Intégration LangChain native (as_retriever(), MMR, etc.)
  - Persistance automatique sur disque

Installation :
    pip install chromadb langchain-chroma langchain-huggingface sentence-transformers

Structure générée :
    rag/output/chromadb/     ← dossier persisté automatiquement
"""

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Chemins ────────────────────────────────────────────────
_THIS_DIR  = Path(__file__).resolve().parent
OUT_DIR    = _THIS_DIR.parent / "rag" / "output"
CHROMA_DIR = OUT_DIR / "chromadb"
OUT_DIR.mkdir(parents=True, exist_ok=True)
CHROMA_DIR.mkdir(parents=True, exist_ok=True)

# Conservé pour compatibilité avec l'ancien code
STORE_PATH = OUT_DIR / "vectorstore.pkl"

# Nom de la collection ChromaDB
COLLECTION_NAME = "mathutrice_chunks"


# ══════════════════════════════════════════════════════════
# WRAPPER EMBEDDINGS → LangChain
# ══════════════════════════════════════════════════════════

def _get_langchain_embeddings():
    """
    Retourne un objet embeddings compatible LangChain.
    Priorité : Solon FR (sentence-transformers) → fallback HuggingFace défaut
    """
    try:
        from langchain_huggingface import HuggingFaceEmbeddings
        embeddings = HuggingFaceEmbeddings(
            model_name   = "OrdalieTech/Solon-embeddings-large-0.1",
            model_kwargs = {"device": "cpu"},
            encode_kwargs= {"normalize_embeddings": True},
        )
        logger.info("Embeddings : Solon FR (OrdalieTech)")
        return embeddings
    except Exception as e:
        logger.warning(f"Solon FR indisponible ({e}) → MiniLM fallback")
        from langchain_huggingface import HuggingFaceEmbeddings
        return HuggingFaceEmbeddings(
            model_name="paraphrase-multilingual-MiniLM-L12-v2"
        )


# ══════════════════════════════════════════════════════════
# CONVERSION chunks → LangChain Documents
# ══════════════════════════════════════════════════════════

def _chunks_to_documents(chunks: list[dict]):
    """
    Convertit nos chunks internes en Documents LangChain.
    Les métadonnées sont aplaties (ChromaDB n'accepte pas les listes/dicts imbriqués).
    """
    from langchain_core.documents import Document

    docs = []
    for c in chunks:
        m = c.get("metadata", {})

        # ChromaDB n'accepte que str/int/float/bool → sérialiser les listes
        flat_meta = {
            "chunk_id"      : str(c.get("id", "")),
            "notion"        : str(m.get("notion", "")),
            "niveau"        : str(m.get("niveau", "")),
            "doc_type"      : str(m.get("doc_type", "exercices")),
            "pdf_source"    : str(m.get("pdf_source", "")),
            "pdf_rel_path"  : str(m.get("pdf_rel_path", "")),
            "page"          : int(m.get("page", 1)),
            "difficulte"    : int(m.get("difficulte", 3)),
            "type_exercice" : str(m.get("type_exercice", "")),
            "concept"       : str(m.get("concept", "") or ""),
            "has_latex"     : bool(m.get("has_latex", False)),
            "has_formula"   : bool(m.get("has_formula", False)),
            "char_count"    : int(m.get("char_count", len(c.get("text", "")))),
            "llm_enriched"  : bool(m.get("llm_enriched", False)),
            # Listes → JSON string (pour filtres complexes)
            "prerequis"     : json.dumps(m.get("prerequis", []), ensure_ascii=False),
            "lacunes_type"  : json.dumps(m.get("lacunes_type", []), ensure_ascii=False),
        }

        docs.append(Document(
            page_content = c.get("text", ""),
            metadata     = flat_meta,
        ))
    return docs


def _document_to_chunk(doc) -> dict:
    """Reconvertit un Document LangChain en chunk interne."""
    m = doc.metadata
    return {
        "id"  : m.get("chunk_id", ""),
        "text": doc.page_content,
        "metadata": {
            **m,
            "prerequis"   : json.loads(m.get("prerequis", "[]")),
            "lacunes_type": json.loads(m.get("lacunes_type", "[]")),
        }
    }


# ══════════════════════════════════════════════════════════
# CLASSE PRINCIPALE — ChromaVectorStore
# ══════════════════════════════════════════════════════════

class ChromaVectorStore:
    """
    BDD vectorielle ChromaDB avec LangChain.
    Interface identique à l'ancien SemanticVectorStore pour
    compatibilité avec step4_retriever et rag_bridge.

    Utilisation :
        store = ChromaVectorStore()
        store.add(chunks)                          # indexation
        results = store.search("simplifier fraction", k=5)
        lc_ret  = store.as_langchain_retriever()   # LangChain natif
    """

    def __init__(self, chroma_dir: Path = CHROMA_DIR,
                 collection_name: str = COLLECTION_NAME):
        self.chroma_dir      = chroma_dir
        self.collection_name = collection_name
        self._store          = None   # Chroma LangChain instance
        self._embeddings     = None

    def _init_store(self, embeddings=None):
        """Initialise ou charge le store ChromaDB."""
        from langchain_chroma import Chroma

        self._embeddings = embeddings or _get_langchain_embeddings()
        self._store = Chroma(
            collection_name    = self.collection_name,
            embedding_function = self._embeddings,
            persist_directory  = str(self.chroma_dir),
        )
        return self._store

    # ── Propriété chunks (compatibilité avec l'ancien code) ──
    @property
    def chunks(self) -> list[dict]:
        """Retourne tous les chunks comme liste de dicts."""
        if self._store is None:
            self._init_store()
        try:
            results = self._store.get(include=["documents", "metadatas"])
            chunks  = []
            for text, meta in zip(results["documents"], results["metadatas"]):
                chunks.append({
                    "id"      : meta.get("chunk_id", ""),
                    "text"    : text,
                    "metadata": {
                        **meta,
                        "prerequis"   : json.loads(meta.get("prerequis", "[]")),
                        "lacunes_type": json.loads(meta.get("lacunes_type", "[]")),
                    }
                })
            return chunks
        except Exception:
            return []

    def __len__(self) -> int:
        return len(self.chunks)

    # ── Ajout de chunks ──────────────────────────────────────
    def add(self, chunks: list[dict], embeddings=None):
        """
        Indexe les chunks dans ChromaDB.
        Déduplique automatiquement par chunk_id.
        """
        import time
        if not chunks:
            return

        if self._store is None:
            self._init_store(embeddings)

        # Récupérer les IDs déjà indexés
        try:
            existing = set(self._store.get()["ids"])
        except Exception:
            existing = set()

        # Filtrer les nouveaux chunks
        new_chunks = [c for c in chunks if str(c.get("id", "")) not in existing]
        if not new_chunks:
            print(f"  ChromaDB : tous les chunks déjà indexés.")
            return

        print(f"  ChromaDB : indexation de {len(new_chunks)} chunks...")
        t0   = time.perf_counter()
        docs = _chunks_to_documents(new_chunks)
        ids  = [str(c.get("id", f"chunk_{i}")) for i, c in enumerate(new_chunks)]

        self._store.add_documents(documents=docs, ids=ids)
        dt = time.perf_counter() - t0
        print(f"  ChromaDB : ✓ {len(new_chunks)} chunks indexés en {dt:.1f}s")

    # ── Recherche ────────────────────────────────────────────
    def search(self, query: str, k: int = 5,
               filters: dict = None) -> list[dict]:
        """
        Recherche sémantique avec filtres optionnels sur les métadonnées.

        Filtres supportés (syntaxe ChromaDB) :
            {"notion": "trigonométrie"}
            {"difficulte": {"$lte": 3}}
            {"$and": [{"notion": "..."}, {"difficulte": {"$lte": 3}}]}
        """
        if self._store is None:
            self._init_store()

        try:
            # Convertir nos filtres internes vers la syntaxe ChromaDB
            where = _convert_filters(filters) if filters else None

            if where:
                docs_scores = self._store.similarity_search_with_score(
                    query, k=k, filter=where
                )
            else:
                docs_scores = self._store.similarity_search_with_score(
                    query, k=k
                )

            results = []
            for doc, score in docs_scores:
                chunk = _document_to_chunk(doc)
                # ChromaDB retourne distance L2 → convertir en similarité
                similarity = max(0.0, 1.0 - score)
                results.append({"chunk": chunk, "score": similarity})

            return results

        except Exception as e:
            logger.error(f"ChromaDB search error: {e}")
            return []

    def get_by_id(self, chunk_id: str) -> Optional[dict]:
        """Récupère un chunk par son ID."""
        if self._store is None:
            self._init_store()
        try:
            result = self._store.get(ids=[chunk_id],
                                     include=["documents", "metadatas"])
            if result["documents"]:
                return {
                    "id"  : chunk_id,
                    "text": result["documents"][0],
                    "metadata": result["metadatas"][0],
                }
        except Exception:
            pass
        return None

    # ── LangChain natif ──────────────────────────────────────
    def as_langchain_retriever(self, k: int = 4,
                                search_type: str = "mmr",
                                filters: dict = None):
        """
        Retourne un retriever LangChain natif.
        Utilisable directement dans une LangChain chain.

        search_type :
            "similarity" → top-k similarité cosinus
            "mmr"        → Maximal Marginal Relevance (diversité)

        Exemple :
            retriever = store.as_langchain_retriever(k=4)
            chain = ConversationalRetrievalChain.from_llm(llm, retriever)
        """
        if self._store is None:
            self._init_store()

        kwargs = {"k": k}
        if filters:
            kwargs["filter"] = _convert_filters(filters)

        return self._store.as_retriever(
            search_type         = search_type,
            search_kwargs       = kwargs,
        )

    # ── Sauvegarde / Chargement ──────────────────────────────
    def save(self, path: Path = None):
        """
        ChromaDB est persisté automatiquement.
        Cette méthode existe pour compatibilité avec l'ancien code.
        """
        # ChromaDB persiste automatiquement à chaque add_documents
        logger.debug(f"ChromaDB persisté dans : {self.chroma_dir}")

    @classmethod
    def load(cls, path: Path = None,
             chroma_dir: Path = CHROMA_DIR) -> "ChromaVectorStore":
        """
        Charge le store ChromaDB existant.
        path est ignoré (compatibilité ancien code pkl).
        """
        store = cls(chroma_dir=chroma_dir)
        store._init_store()
        try:
            count = len(store._store.get()["ids"])
            logger.info(f"ChromaDB chargé : {count} chunks")
            print(f"  ChromaDB chargé : {count} chunks dans '{chroma_dir}'")
        except Exception as e:
            logger.warning(f"ChromaDB vide ou erreur : {e}")
        return store

    # ── Stats ────────────────────────────────────────────────
    def stats(self) -> dict:
        """Stats de la collection pour le dashboard admin."""
        import json
        from collections import Counter
        chunks = self.chunks
        if not chunks:
            return {"status": "empty", "total": 0}

        return {
            "status"           : "ready",
            "total_chunks"     : len(chunks),
            "notions"          : list(set(c["metadata"].get("notion","") for c in chunks)),
            "difficulte_dist"  : dict(Counter(c["metadata"].get("difficulte") for c in chunks)),
            "types"            : dict(Counter(c["metadata"].get("type_exercice","") for c in chunks)),
            "llm_enriched_pct" : round(sum(1 for c in chunks if c["metadata"].get("llm_enriched")) / len(chunks) * 100),
            "chroma_dir"       : str(self.chroma_dir),
        }


# ══════════════════════════════════════════════════════════
# HELPER — conversion filtres
# ══════════════════════════════════════════════════════════

def _convert_filters(filters: dict) -> dict:
    """
    Convertit nos filtres internes vers la syntaxe ChromaDB.

    Entrée  : {"difficulte": {"$lte": 3}, "notion": "trigonométrie"}
    Sortie  : {"$and": [{"difficulte": {"$lte": 3}}, {"notion": {"$eq": "trigonométrie"}}]}
    """
    if not filters:
        return {}

    conditions = []
    for field, cond in filters.items():
        if isinstance(cond, dict):
            # Opérateurs : $lte, $gte, $lt, $gt, $eq, $ne, $in
            conditions.append({field: cond})
        elif isinstance(cond, list):
            conditions.append({field: {"$in": cond}})
        else:
            conditions.append({field: {"$eq": cond}})

    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


# ══════════════════════════════════════════════════════════
# COMPATIBILITÉ — alias pour l'ancien code
# ══════════════════════════════════════════════════════════

# Alias pour que run_pipeline_batch.py et rag_bridge.py
# n'aient pas à changer leurs imports
LocalVectorStore   = ChromaVectorStore
SemanticVectorStore = ChromaVectorStore


# ══════════════════════════════════════════════════════════
# FONCTION run() — point d'entrée step3
# ══════════════════════════════════════════════════════════

def run(chunks: list[dict], chroma_dir: Path = CHROMA_DIR) -> ChromaVectorStore:
    """
    Indexe les chunks dans ChromaDB et retourne le store.
    Appelé par run_pipeline_batch.py après step2.
    """
    store = ChromaVectorStore(chroma_dir=chroma_dir)
    store.add(chunks)
    return store


if __name__ == "__main__":
    print("ChromaDB store — test rapide")
    store = ChromaVectorStore.load()
    print(store.stats())
