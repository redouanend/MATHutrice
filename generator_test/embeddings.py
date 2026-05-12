"""
Embeddings production — MATHutrice
====================================
Transforme les chunks texte en vecteurs numériques pour la BDD vectorielle.

3 backends disponibles selon l'environnement :
  - SentenceTransformerEmbedder  → local, gratuit, RECOMMANDÉ
      Modèle : OrdalieTech/Solon-embeddings-large-0.1
      Entraîné sur texte académique FR — idéal pour maths L1
  - OpenAIEmbedder               → cloud, qualité maximale, payant
      Modèle : text-embedding-3-small (~$0.02/million tokens)
  - TFIDFEmbedder                → fallback lexical, zéro dépendance
      Pas de compréhension sémantique — uniquement si ST indisponible

Usage :
  from embeddings import get_embedder, SemanticVectorStore
  embedder = get_embedder()                    # auto → Solon FR
  store    = SemanticVectorStore(embedder)
  store.add(chunks_enrichis)
  results  = store.search('simplifier fraction', k=5)
"""

import numpy as np
from pathlib import Path
from abc import ABC, abstractmethod


# ══════════════════════════════════════════════════════
# INTERFACE COMMUNE
# ══════════════════════════════════════════════════════

class BaseEmbedder(ABC):
    """Interface commune à tous les backends d'embedding."""

    @property
    @abstractmethod
    def dim(self) -> int:
        """Dimension des vecteurs produits."""

    @abstractmethod
    def embed(self, text: str) -> np.ndarray:
        """Vectorise un texte → vecteur numpy (dim,)"""

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> np.ndarray:
        """Vectorise une liste → matrice numpy (n, dim)"""

    def similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Similarité cosinus entre deux vecteurs."""
        na = np.linalg.norm(a); nb = np.linalg.norm(b)
        if na == 0 or nb == 0: return 0.0
        return float(np.dot(a, b) / (na * nb))

    def search(self, query: str, matrix: np.ndarray,
               top_k: int = 5) -> list[tuple[int, float]]:
        """
        Recherche les top_k vecteurs les plus similaires dans matrix.
        Retourne [(index, score), ...] trié par score décroissant.
        """
        q_vec = self.embed(query)
        # Normaliser
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1
        norm_mat  = matrix / norms
        q_norm    = q_vec / (np.linalg.norm(q_vec) + 1e-10)
        scores    = norm_mat @ q_norm
        top_idx   = np.argsort(scores)[::-1][:top_k]
        return [(int(i), float(scores[i])) for i in top_idx]


# ══════════════════════════════════════════════════════
# BACKEND 1 — Sentence Transformers (recommandé)
# ══════════════════════════════════════════════════════

class SentenceTransformerEmbedder(BaseEmbedder):
    """
    Embeddings sémantiques — FR natif spécialisé texte académique.
    Modèle par défaut : OrdalieTech/Solon-embeddings-large-0.1
      - 330 MB, tourne sur CPU, meilleure qualité FR académique
      - Entraîné sur du texte académique français — idéal maths L1
      - Comprend les synonymes : "fraction" ≈ "quotient" ≈ "rapport"

    Autres options disponibles :
      "paraphrase-multilingual-MiniLM-L12-v2"  → 118 MB, plus léger, FR+EN
      "dangvantuan/sentence-camembert-large"   → 330 MB, FR natif généraliste

    Installation :
      pip install sentence-transformers
    """

    DEFAULT_MODEL = "OrdalieTech/Solon-embeddings-large-0.1"

    def __init__(self, model_name: str = None, cache_dir: str = None):
        from sentence_transformers import SentenceTransformer
        model_name = model_name or self.DEFAULT_MODEL
        print(f"  Chargement du modèle : {model_name}")
        self.model = SentenceTransformer(
            model_name,
            cache_folder = cache_dir or str(Path.home() / '.cache' / 'sentence_transformers')
        )
        self._dim = self.model.get_sentence_embedding_dimension()
        print(f"  Dimension : {self._dim}")

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, text: str) -> np.ndarray:
        return self.model.encode(
            text,
            normalize_embeddings = True,
            show_progress_bar    = False
        )

    def embed_batch(self, texts: list[str],
                    batch_size: int = 32) -> np.ndarray:
        return self.model.encode(
            texts,
            batch_size           = batch_size,
            normalize_embeddings = True,
            show_progress_bar    = len(texts) > 10
        )


# ══════════════════════════════════════════════════════
# BACKEND 2 — OpenAI API
# ══════════════════════════════════════════════════════

class OpenAIEmbedder(BaseEmbedder):
    """
    Embeddings via l'API OpenAI.
    Modèle recommandé : text-embedding-3-small
      - $0.02 / million de tokens (très peu cher à l'indexation)
      - 1536 dimensions, meilleure qualité

    Installation :
      pip install openai
    """

    DEFAULT_MODEL = "text-embedding-3-small"

    def __init__(self, api_key: str = None, model: str = None):
        import openai, os
        self.client = openai.OpenAI(
            api_key = api_key or os.environ.get("OPENAI_API_KEY")
        )
        self.model_name = model or self.DEFAULT_MODEL
        self._dim = 1536 if "3-small" in self.model_name else 3072

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, text: str) -> np.ndarray:
        resp = self.client.embeddings.create(
            input = [text[:8000]],
            model = self.model_name
        )
        return np.array(resp.data[0].embedding, dtype=np.float32)

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        # OpenAI accepte jusqu'à 2048 inputs par appel
        all_vecs = []
        chunk_size = 100
        for i in range(0, len(texts), chunk_size):
            batch = [t[:8000] for t in texts[i:i+chunk_size]]
            resp  = self.client.embeddings.create(
                input = batch,
                model = self.model_name
            )
            vecs = [r.embedding for r in sorted(resp.data, key=lambda x: x.index)]
            all_vecs.extend(vecs)
        return np.array(all_vecs, dtype=np.float32)


# ══════════════════════════════════════════════════════
# BACKEND 3 — TF-IDF (fallback)
# ══════════════════════════════════════════════════════

class TFIDFEmbedder(BaseEmbedder):
    """
    Fallback lexical (pas de dépendance externe).
    À utiliser uniquement si sentence-transformers indisponible.
    Limitation : pas de compréhension sémantique.
    """

    def __init__(self, texts: list[str] = None):
        from sklearn.feature_extraction.text import TfidfVectorizer
        self.vectorizer = TfidfVectorizer(
            ngram_range    = (1, 2),
            sublinear_tf   = True,
            strip_accents  = 'unicode',
            min_df         = 1,
            token_pattern  = r'(?u)\b[a-zA-ZÀ-ÿ0-9_]{2,}\b'
        )
        self._dim  = 0
        self._fitted = False
        if texts:
            self.fit(texts)

    def fit(self, texts: list[str]):
        self.vectorizer.fit(texts)
        self._dim    = len(self.vectorizer.vocabulary_)
        self._fitted = True

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, text: str) -> np.ndarray:
        if not self._fitted:
            raise RuntimeError("TFIDFEmbedder : appeler fit(texts) avant embed()")
        v = self.vectorizer.transform([text]).toarray()[0]
        norm = np.linalg.norm(v)
        return v / norm if norm > 0 else v

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        if not self._fitted:
            self.fit(texts)
        mat  = self.vectorizer.transform(texts).toarray()
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        norms[norms == 0] = 1
        return mat / norms


# ══════════════════════════════════════════════════════
# INTÉGRATION DANS VECTORSTORE (ChromaDB-ready)
# ══════════════════════════════════════════════════════

class SemanticVectorStore:
    """
    BDD vectorielle sémantique.
    Remplace LocalVectorStore de step3_vectorstore.py
    avec de vrais embeddings.

    Compatible ChromaDB : pour migrer en prod, remplacer
    self._store par chromadb.Collection et adapter add/query.
    """

    def __init__(self, embedder: BaseEmbedder):
        self.embedder  = embedder
        self.chunks    = []
        self.ids       = []
        self.matrix    = None   # np.ndarray (n, dim)

    def add(self, chunks: list[dict]):
        """Indexe les chunks avec leurs embeddings sémantiques."""
        import time
        new_chunks = [c for c in chunks if c['id'] not in self.ids]
        if not new_chunks:
            print("  Aucun nouveau chunk à indexer.")
            return

        print(f"  Calcul des embeddings pour {len(new_chunks)} chunks...")
        t0    = time.perf_counter()
        texts = [_prepare_text(c) for c in new_chunks]
        vecs  = self.embedder.embed_batch(texts)
        dt    = time.perf_counter() - t0

        self.chunks.extend(new_chunks)
        self.ids.extend(c['id'] for c in new_chunks)

        if self.matrix is None:
            self.matrix = vecs
        else:
            self.matrix = np.vstack([self.matrix, vecs])

        print(f"  {len(self.chunks)} chunks indexés  "
              f"({dt:.2f}s, dim={self.embedder.dim})")

    def search(self, query: str, k: int = 5,
               filters: dict = None) -> list[dict]:
        """Recherche sémantique avec filtres optionnels."""
        if self.matrix is None or len(self.chunks) == 0:
            return []

        results = self.embedder.search(query, self.matrix, top_k=k * 3)

        output = []
        for idx, score in results:
            if len(output) >= k: break
            if score < 0.05: continue
            chunk = self.chunks[idx]
            if filters and not _apply_filters(chunk, filters):
                continue
            output.append({'chunk': chunk, 'score': score,
                           'chunk_id': chunk['id']})
        return output[:k]

    def save(self, path: Path):
        import pickle
        with open(path, 'wb') as f:
            pickle.dump({
                'chunks': self.chunks, 'ids': self.ids,
                'matrix': self.matrix, 'embedder': self.embedder
            }, f)

    @classmethod
    def load(cls, path: Path) -> 'SemanticVectorStore':
        import pickle
        with open(path, 'rb') as f:
            data = pickle.load(f)
        store = cls(data['embedder'])
        store.chunks = data['chunks']
        store.ids    = data['ids']
        store.matrix = data['matrix']
        return store


# ══════════════════════════════════════════════════════
# FACTORY
# ══════════════════════════════════════════════════════

def get_embedder(backend: str = 'auto', **kwargs) -> BaseEmbedder:
    """
    Retourne le meilleur embedder disponible.

    backend = 'auto'                  → essaie Solon FR (ST), sinon TF-IDF
    backend = 'sentence_transformers' → force Solon FR local (recommandé)
    backend = 'openai'                → force OpenAI API (payant, qualité max)
    backend = 'tfidf'                 → force TF-IDF (fallback sans dépendance)

    Exemple :
        get_embedder()                           # Solon FR automatique
        get_embedder('sentence_transformers')    # idem, explicite
        get_embedder('openai', api_key='sk-...') # OpenAI payant
        get_embedder('tfidf')                    # fallback minimal
    """
    if backend == 'openai':
        return OpenAIEmbedder(**kwargs)

    if backend == 'tfidf':
        return TFIDFEmbedder(**kwargs)

    # sentence_transformers ou auto
    try:
        import sentence_transformers  # noqa
        embedder = SentenceTransformerEmbedder(**kwargs)
        print(f"  Embedder : SentenceTransformer ✓")
        return embedder
    except ImportError:
        if backend == 'sentence_transformers':
            raise ImportError(
                "sentence-transformers non installé.\n"
                "Installer avec : pip install sentence-transformers"
            )
        print("  ⚠ sentence-transformers absent → fallback TF-IDF")
        print("  Pour la production : pip install sentence-transformers")
        return TFIDFEmbedder(**kwargs)


# ── Helpers ────────────────────────────────────────────

def _prepare_text(chunk: dict) -> str:
    """Texte enrichi avec métadonnées pour l'embedding."""
    import re
    parts = []
    m     = chunk.get('metadata', {})

    text = chunk.get('text', '')
    text = re.sub(r'\\frac\{([^}]*)\}\{([^}]*)\}', r'\1 sur \2', text)
    text = re.sub(r'\\sqrt\{([^}]*)\}', r'racine de \1', text)
    text = re.sub(r'\\[a-zA-Z]+', '', text)
    parts.append(text)

    for field in ('concept', 'type_exercice', 'notion', 'description_courte'):
        if m.get(field):
            parts.append(str(m[field]))

    if m.get('prerequis'):
        parts.append('prérequis ' + ' '.join(m['prerequis']))

    if m.get('lacunes_type'):
        parts.append('lacunes ' + ' '.join(m['lacunes_type']))

    return ' '.join(parts)


def _apply_filters(chunk: dict, filters: dict) -> bool:
    """Filtres MongoDB-style sur les métadonnées."""
    m = chunk.get('metadata', {})
    for field, cond in filters.items():
        val = m.get(field)
        if isinstance(cond, dict):
            for op, target in cond.items():
                if op == '$lte' and (val is None or val > target):  return False
                if op == '$gte' and (val is None or val < target):  return False
                if op == '$lt'  and (val is None or val >= target): return False
                if op == '$gt'  and (val is None or val <= target): return False
                if op == '$eq'  and val != target:                  return False
                if op == '$ne'  and val == target:                  return False
                if op == '$in':
                    v = val if isinstance(val, list) else [val]
                    if not any(x in target for x in v): return False
        elif val != cond:
            return False
    return True


# ══════════════════════════════════════════════════════
# DÉMO COMPARATIVE (TF-IDF vs Sentence Transformers)
# ══════════════════════════════════════════════════════

if __name__ == '__main__':
    print("=" * 60)
    print("  COMPARAISON TF-IDF vs Sentence Transformers")
    print("=" * 60 + "\n")

    # Phrases de test — montrent la différence sémantique
    corpus = [
        "Simplifier la fraction 6/15 en fraction irréductible",
        "Réduire le quotient 4/10 sous forme irréductible",
        "Calculer la somme 3/4 + 2/5",
        "Addition de deux fractions à dénominateurs différents",
        "Développer l'expression (a+b)²",
        "Calculer 3 puissance 4 fois 3 puissance -2",
        "Exposants entiers : simplifier 3^4 × 3^-2",
        "Extraire la racine carrée de 72",
        "Simplifier √72 + √32",
    ]

    queries = [
        "Comment additionner des fractions ?",
        "Simplifier avec des puissances négatives",
        "Exercice sur les radicaux",
    ]

    # ── TF-IDF ──────────────────────────────────────
    print("─ TF-IDF (lexical) ─────────────────────────────────")
    tfidf = TFIDFEmbedder()
    tfidf.fit(corpus)
    mat   = tfidf.embed_batch(corpus)

    for q in queries:
        results = tfidf.search(q, mat, top_k=2)
        print(f"\n  Requête : \"{q}\"")
        for idx, score in results:
            print(f"    [{score:.3f}] {corpus[idx][:60]}")

    # ── Solon FR (Sentence Transformers) ────────────────
    print("\n─ Solon FR — OrdalieTech (sémantique académique FR) ─")
    try:
        st  = SentenceTransformerEmbedder()
        mat = st.embed_batch(corpus)
        for q in queries:
            results = st.search(q, mat, top_k=2)
            print(f"\n  Requête : \"{q}\"")
            for idx, score in results:
                print(f"    [{score:.3f}] {corpus[idx][:60]}")
    except ImportError:
        print("  sentence-transformers non installé.")
        print("  pip install sentence-transformers")

    print("\n" + "=" * 60)
    print("  Pour utiliser dans ton projet :")
    print()
    print("  from embeddings import get_embedder, SemanticVectorStore")
    print("  embedder = get_embedder()  # Solon FR par défaut")
    print("  store    = SemanticVectorStore(embedder)")
    print("  store.add(chunks_enrichis)")
    print("  results  = store.search('simplifier fraction', k=5)")
    print("=" * 60)
