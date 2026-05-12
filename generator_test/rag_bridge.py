"""
rag_bridge.py — Pont entre ChromaDB et les générateurs Mistral
==============================================================
Charge ChromaDB une seule fois au démarrage FastAPI,
puis injecte le contexte RAG dans chaque prompt Mistral.

Usage dans app.py :
    from rag_bridge import get_bridge

    @app.on_event("startup")
    async def startup():
        get_bridge()   # précharge ChromaDB au démarrage

    @app.post("/generate_exo")
    async def generate_exo(data: Data, bridge=Depends(get_bridge)):
        eleve   = EleveContext(niveau=2)
        questions = bridge.generate_qcm(data.notion, data.niveau, n=3, eleve=eleve)
        return {"questions": questions}
"""

import re
import sys
import json
import logging
from pathlib import Path
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ── Chemins ────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent
_RAG_DIR      = _PROJECT_ROOT / "rag"
sys.path.insert(0, str(_RAG_DIR))


# ══════════════════════════════════════════════════════════
# PROFIL ÉLÈVE
# ══════════════════════════════════════════════════════════

@dataclass
class EleveContext:
    """
    Profil élève transmis au bridge pour adapter le contexte RAG.
    Alimenté depuis PostgreSQL dans la version complète.
    """
    eleve_id    : str   = "anonymous"
    nom         : str   = "Étudiant"
    niveau      : int   = 2          # 1-5  (1-2=débutant, 3=inter, 4-5=avancé)
    lacunes     : list  = field(default_factory=list)
    score_moyen : float = 0.0

    @classmethod
    def from_db_row(cls, row: dict) -> "EleveContext":
        """Construit le profil depuis une ligne PostgreSQL."""
        return cls(
            eleve_id    = str(row.get("id", "anonymous")),
            nom         = row.get("nom", "Étudiant"),
            niveau      = int(row.get("niveau", 2)),
            lacunes     = row.get("lacunes", []) or [],
            score_moyen = float(row.get("score_moyen", 0.0)),
        )

    def niveau_label(self) -> str:
        """Convertit le niveau numérique en label textuel."""
        return {
            1: "débutant", 2: "débutant",
            3: "intermédiaire",
            4: "avancé",   5: "avancé",
        }.get(self.niveau, "intermédiaire")

    def diff_max(self) -> int:
        """Difficulté maximale des exercices pour cet élève (filtre ChromaDB)."""
        return min(self.niveau + 1, 5)


# ══════════════════════════════════════════════════════════
# FORMATAGE DU CONTEXTE RAG POUR LES PROMPTS
# ══════════════════════════════════════════════════════════

def _format_rag_context(chunks: list[dict], max_chars: int = 1400) -> str:
    """
    Formate les chunks ChromaDB en bloc de texte insérable dans un prompt Mistral.

    - Nettoie le LaTeX pour le rendre lisible par le LLM
    - Limite la taille totale pour ne pas dépasser le context window
    - Ajoute des métadonnées pédagogiques en header de chaque chunk
    """
    if not chunks:
        return ""

    parts = ["### Exercices de référence (extraits du cours) :\n"]
    total = 0

    for i, chunk in enumerate(chunks, 1):
        m    = chunk.get("metadata", {})
        diff = m.get("difficulte", "?")
        typ  = m.get("type_exercice", "") or ""
        conc = m.get("concept", "") or ""

        header = f"[Ref {i} | {conc or 'exercice'} | diff {diff}/5 | {typ}]\n"
        text   = chunk.get("text", "")[:450]

        # Rendre le LaTeX lisible pour Mistral
        text = re.sub(r'\\frac\{([^}]*)\}\{([^}]*)\}', r'(\1)/(\2)', text)
        text = re.sub(r'\\sqrt\{([^}]*)\}',             r'√(\1)',     text)
        text = re.sub(r'\$\$([^$]+)\$\$',               r'\1',        text)
        text = re.sub(r'\$([^$]+)\$',                    r'\1',        text)
        text = re.sub(r'\\[a-zA-Z]+',                    '',           text)

        entry = header + text.strip() + "\n\n"
        if total + len(entry) > max_chars:
            break

        parts.append(entry)
        total += len(entry)

    return "".join(parts) if len(parts) > 1 else ""


# ══════════════════════════════════════════════════════════
# PROMPTS ENRICHIS PAR LE RAG
# ══════════════════════════════════════════════════════════

def _build_prompt_qcm(notion: str, niveau_label: str, rag_context: str) -> str:
    rag_section = f"""
Tu as accès aux exercices réels du cours de l'étudiant :

{rag_context}
Inspire-toi de ces exercices pour créer une question QCM du MÊME TYPE.
Utilise des valeurs numériques différentes.
---
""" if rag_context else ""

    return f"""Tu es un tuteur de mathématiques pour des étudiants de L1.
{rag_section}
Génère UNE question QCM.
- Notion : {notion}
- Niveau : {niveau_label}

Contraintes : 4 options, une seule correcte, distracteurs plausibles, calculs corrects.

Réponds UNIQUEMENT avec ce JSON valide (pas de texte autour, pas de ```json) :
{{
  "question": "...",
  "options": ["rép1", "rép2", "rép3", "rép4"],
  "answer": "la bonne réponse exacte"
}}"""


def _build_prompt_qro(notion: str, niveau_label: str, rag_context: str) -> str:
    rag_section = f"""
Tu as accès aux exercices réels du cours de l'étudiant :

{rag_context}
Inspire-toi de ces exercices pour une question à réponse courte du MÊME TYPE.
---
""" if rag_context else ""

    return f"""Tu es un tuteur de mathématiques pour des étudiants de L1.
{rag_section}
Génère UNE question à réponse ouverte courte (QRO).
- Notion : {notion}
- Niveau : {niveau_label}

La réponse attendue doit être courte : un résultat, une expression, une valeur.

Réponds UNIQUEMENT avec ce JSON valide (pas de texte autour, pas de ```json) :
{{
  "question": "...",
  "correct_answer": "..."
}}"""


def _build_prompt_steps(notion: str, niveau_label: str, rag_context: str) -> str:
    rag_section = f"""
Tu as accès aux exercices réels du cours de l'étudiant :

{rag_context}
Prends un exercice de référence et décompose-le en étapes.
Utilise des valeurs différentes.
---
""" if rag_context else ""

    return f"""Tu es un tuteur de mathématiques pour des étudiants de L1.
{rag_section}
Génère UN exercice de résolution étape par étape.
- Notion : {notion}
- Niveau : {niveau_label}

3 à 5 étapes dans l'ordre logique. "questions" et "correct_answers" même longueur.

Réponds UNIQUEMENT avec ce JSON valide (pas de texte autour, pas de ```json) :
{{
  "enonce": "...",
  "questions": ["Étape 1 : ...", "Étape 2 : ..."],
  "correct_answers": ["rép 1", "rép 2"]
}}"""


def _build_prompt_trous(notion: str, niveau_label: str, rag_context: str) -> str:
    rag_section = f"""
Tu as accès aux exercices réels du cours de l'étudiant :

{rag_context}
Transforme un exercice de référence en phrases à trous.
---
""" if rag_context else ""

    return f"""Tu es un tuteur de mathématiques pour des étudiants de L1.
{rag_section}
Génère UN exercice de phrases à trous.
- Notion : {notion}
- Niveau : {niveau_label}

3 à 5 phrases, chacune avec exactement un trou noté ___. "phrases" et "correct_answers" même longueur.

Réponds UNIQUEMENT avec ce JSON valide (pas de texte autour, pas de ```json) :
{{
  "enonce": "...",
  "phrases": ["Phrase avec ___."],
  "correct_answers": ["réponse"]
}}"""


# ══════════════════════════════════════════════════════════
# CLASSE PRINCIPALE
# ══════════════════════════════════════════════════════════

class RAGBridge:
    """
    Pont entre ChromaDB et les générateurs Mistral.

    Chargé une seule fois au démarrage FastAPI via get_bridge().
    Expose les mêmes interfaces que les anciens générateurs,
    avec contexte RAG injecté automatiquement dans chaque prompt.
    """

    def __init__(self, store=None):
        self.store   = store
        self._ready  = store is not None
        self._no_rag = store is None

        if self._no_rag:
            logger.warning(
                "RAGBridge sans ChromaDB — génération sans contexte RAG. "
                "Lancer run_pipeline_batch.py pour construire la BDD."
            )
        else:
            logger.info(f"RAGBridge prêt — ChromaDB chargé")

    # ── Chargement ─────────────────────────────────────────
    @classmethod
    def load(cls) -> "RAGBridge":
        """
        Charge ChromaDB depuis le disque.
        Fallback sans RAG si la BDD est vide ou indisponible.
        """
        try:
            from step3_vectorstore import ChromaVectorStore, CHROMA_DIR
            store = ChromaVectorStore.load(chroma_dir=CHROMA_DIR)
            count = len(store)
            if count == 0:
                logger.warning("ChromaDB vide — mode dégradé sans RAG")
                return cls(store=None)
            logger.info(f"ChromaDB chargé : {count} chunks")
            print(f"  [RAGBridge] ChromaDB chargé — {count} chunks")
            return cls(store=store)
        except Exception as e:
            logger.error(f"Impossible de charger ChromaDB : {e}")
            return cls(store=None)

    # ── Récupération du contexte RAG depuis ChromaDB ────────
    def _get_rag_context(self, notion: str,
                          eleve: EleveContext,
                          k: int = 3) -> tuple[str, list[dict]]:
        """
        Interroge ChromaDB avec filtres sur notion + difficulté.
        Retourne (texte_formaté_pour_prompt, chunks_bruts).
        """
        if self._no_rag or self.store is None:
            return "", []

        try:
            # Requête sémantique : notion + lacunes de l'élève
            query_parts = [notion]
            if eleve.lacunes:
                query_parts.extend(eleve.lacunes[:2])
            query = " ".join(query_parts)

            # Filtre ChromaDB : exercices adaptés au niveau de l'élève
            filters = {
                "$and": [
                    {"notion"    : {"$eq" : notion}},
                    {"difficulte": {"$lte": eleve.diff_max()}},
                    {"doc_type"  : {"$eq" : "exercices"}},
                ]
            }

            results = self.store.search(query, k=k, filters=filters)

            # Fallback sans filtre si pas assez de résultats
            if len(results) < 2:
                results = self.store.search(query, k=k)

            # Normaliser : dict {chunk, score} (ChromaDB)
            chunks = []
            for r in results:
                chunk = r['chunk'] if isinstance(r, dict) else r.get('chunk', r)
                chunks.append(chunk)

            context = _format_rag_context(chunks)
            return context, chunks

        except Exception as e:
            logger.warning(f"Erreur récupération ChromaDB : {e}")
            return "", []

    # ── Générateur interne ──────────────────────────────────
    def _generate(self, format_label: str, notion: str, niveau: str,
                  n: int, eleve: EleveContext,
                  prompt_fn, parse_fn, post_fn=None) -> list[dict]:
        """
        Méthode générique : récupère le contexte RAG, construit le prompt,
        appelle Mistral, valide le JSON.
        """
        from base_generator import call_mistral, generate_test

        eleve        = eleve or EleveContext()
        ctx, chunks  = self._get_rag_context(notion, eleve)
        niveau_label = eleve.niveau_label()

        def _gen(notion, niveau):
            prompt = prompt_fn(notion, niveau_label, ctx)
            return call_mistral(prompt, notion, parse_fn, post_fn)

        questions = generate_test(notion, niveau, n, _gen)

        status = f"RAG={'oui' if ctx else 'non'} | {len(questions)}/{n}"
        logger.info(f"{format_label} — {status}")
        print(f"  [{format_label}] {status}")

        return questions

    # ── API publique — 4 formats ────────────────────────────

    def generate_qcm(self, notion: str, niveau: str,
                     n: int, eleve: EleveContext = None) -> list[dict]:
        """Génère n QCM ancrés dans les exercices réels du cours."""
        from type_questions.qcm_generator import parse_and_validate, post_process
        return self._generate(
            "QCM", notion, niveau, n, eleve,
            _build_prompt_qcm, parse_and_validate, post_process
        )

    def generate_qro(self, notion: str, niveau: str,
                     n: int, eleve: EleveContext = None) -> list[dict]:
        """Génère n QRO ancrés dans les exercices réels du cours."""
        from type_questions.qro_generator import parse_and_validate
        return self._generate(
            "QRO", notion, niveau, n, eleve,
            _build_prompt_qro, parse_and_validate
        )

    def generate_steps(self, notion: str, niveau: str,
                       n: int, eleve: EleveContext = None) -> list[dict]:
        """Génère n exercices step-by-step ancrés dans les exercices réels."""
        from type_questions.steps_generator import parse_and_validate
        return self._generate(
            "Steps", notion, niveau, n, eleve,
            _build_prompt_steps, parse_and_validate
        )

    def generate_trous(self, notion: str, niveau: str,
                       n: int, eleve: EleveContext = None) -> list[dict]:
        """Génère n exercices à trous ancrés dans les exercices réels."""
        from type_questions.trous_generator import parse_and_validate
        return self._generate(
            "Trous", notion, niveau, n, eleve,
            _build_prompt_trous, parse_and_validate
        )

    # ── Retriever LangChain natif (pour chaînes LangChain) ──
    def as_langchain_retriever(self, notion: str = None,
                                diff_max: int = 5,
                                k: int = 4,
                                search_type: str = "mmr"):
        """
        Retourne un retriever LangChain natif depuis ChromaDB.
        Utilisable directement dans une ConversationalRetrievalChain.

        Exemple :
            retriever = bridge.as_langchain_retriever(notion="trigonométrie", diff_max=3)
            chain = ConversationalRetrievalChain.from_llm(llm, retriever)
        """
        if self._no_rag or self.store is None:
            raise RuntimeError("ChromaDB non chargé — appeler RAGBridge.load() d'abord")

        filters = {}
        conditions = [{"doc_type": {"$eq": "exercices"}}]
        if notion:
            conditions.append({"notion": {"$eq": notion}})
        if diff_max < 5:
            conditions.append({"difficulte": {"$lte": diff_max}})
        if len(conditions) > 1:
            filters = {"$and": conditions}
        elif conditions:
            filters = conditions[0]

        return self.store.as_langchain_retriever(
            k           = k,
            search_type = search_type,
            filters     = filters if filters else None,
        )

    # ── Détection de lacunes ────────────────────────────────
    def detect_lacunes(self, resultats: list[dict]) -> list[str]:
        """
        Identifie les lacunes d'un élève depuis ses résultats.

        resultats = [
            {"chunk_id": "Bases_Trig_exercice_1_00", "score": 35, "notion": "trigonométrie"},
            {"chunk_id": "Bases_Trig_exercice_2_01", "score": 80, "notion": "trigonométrie"},
        ]
        Retourne les 3 lacunes les plus fréquentes, triées par fréquence.
        """
        if self._no_rag or not self.store:
            return []

        lacunes: dict[str, float] = {}

        for r in resultats:
            if r.get("score", 100) >= 70:
                continue  # exercice réussi → pas une lacune

            # Récupérer le chunk depuis ChromaDB par son ID
            chunk_id = r.get("chunk_id")
            chunk    = self.store.get_by_id(chunk_id) if chunk_id else None

            if chunk:
                m = chunk.get("metadata", {})
                # Lacunes explicites renseignées par le LLM enrichisseur
                for lac in json.loads(m.get("lacunes_type", "[]")):
                    lacunes[lac] = lacunes.get(lac, 0) + 1
                # Concept de l'exercice raté → lacune probable
                concept = m.get("concept", "")
                if concept:
                    lacunes[concept] = lacunes.get(concept, 0) + 0.5
            else:
                # Pas de chunk_id → inférer depuis la notion
                notion_q = r.get("notion", "")
                if notion_q:
                    lacunes[notion_q] = lacunes.get(notion_q, 0) + 1

        return [k for k, _ in sorted(lacunes.items(), key=lambda x: -x[1])[:3]]

    # ── Stats ChromaDB ──────────────────────────────────────
    def stats(self) -> dict:
        """Stats de la BDD vectorielle pour le dashboard admin."""
        if self._no_rag or self.store is None:
            return {"status": "no_rag", "total_chunks": 0}

        try:
            # ChromaVectorStore.stats() est optimisé — pas de chargement complet
            return self.store.stats()
        except Exception as e:
            return {"status": "error", "message": str(e)}


# ══════════════════════════════════════════════════════════
# SINGLETON FASTAPI
# ══════════════════════════════════════════════════════════

_bridge_instance: Optional[RAGBridge] = None


def get_bridge() -> RAGBridge:
    """
    Singleton — ChromaDB chargé une seule fois au démarrage.

    Dans app.py :
        from contextlib import asynccontextmanager
        from rag_bridge import get_bridge

        @asynccontextmanager
        async def lifespan(app):
            get_bridge()   # précharge ChromaDB au démarrage
            yield

        app = FastAPI(lifespan=lifespan)

    Dans les routes :
        @app.post("/generate_exo")
        async def generate(data: Data, bridge=Depends(get_bridge)):
            eleve = EleveContext(niveau=data.niveau_int)
            return bridge.generate_qcm(data.notion, data.niveau, n=3, eleve=eleve)
    """
    global _bridge_instance
    if _bridge_instance is None:
        _bridge_instance = RAGBridge.load()
    return _bridge_instance


def reset_bridge():
    """Force le rechargement du bridge (utile après run_pipeline_batch)."""
    global _bridge_instance
    _bridge_instance = None
    logger.info("Bridge réinitialisé")
