"""
ÉTAPE 4 — Retriever RAG + Enrichissement des prompts
=====================================================
Interface LangChain-compatible qui :
  1. Reçoit une requête + profil élève
  2. Récupère les chunks les plus pertinents (hybride dense + filtre)
  3. Construit le contexte enrichi pour le LLM
  4. Fournit des méthodes pour : tuteur, évaluation, entraînement, lacunes

Usage dans LangChain :
    retriever = PedagoRetriever(store, eleve_profil)
    context   = retriever.get_context_for_question("Comment simplifier 3/6 + 2/4 ?")
    prompt    = retriever.build_tutor_prompt(question, context)

Ou avec LangChain natif :
    langchain_retriever = retriever.as_langchain_retriever()
    chain = ConversationalRetrievalChain.from_llm(llm, langchain_retriever)
"""

import json
import re
import logging
from pathlib import Path
from dataclasses import dataclass, field

_THIS_DIR = Path(__file__).resolve().parent
OUT_DIR = _THIS_DIR.parent / "output"
OUT_DIR.mkdir(parents=True, exist_ok=True)
logger = logging.getLogger(__name__)


def _get_chunk(r):
    """Normalise un résultat search : dict {chunk,score} ou objet → chunk."""
    if isinstance(r, dict):
        return r.get('chunk', r)
    return r.chunk


def _get_score(r):
    """Normalise un résultat search : dict {chunk,score} ou objet → score."""
    if isinstance(r, dict):
        return r.get('score', 0.0)
    return r.score


# ══════════════════════════════════════════════════════
# PROFIL ÉLÈVE
# ══════════════════════════════════════════════════════

@dataclass
class EleveProfil:
    """
    Représente le profil pédagogique d'un élève.
    Stocké en PostgreSQL, chargé à chaque session.
    """
    eleve_id        : str
    nom             : str
    niveau          : int   = 2        # 1-5, niveau global estimé
    notions_maitrisees : list = field(default_factory=list)
    lacunes         : list  = field(default_factory=list)
    score_moyen     : float = 0.0
    nb_exercices    : int   = 0
    derniere_notion : str   = ""

    def can_attempt(self, difficulte: int) -> bool:
        """Un élève peut tenter un exercice si difficulté ≤ niveau + 1."""
        return difficulte <= self.niveau + 1

    def to_context_str(self) -> str:
        """Résumé textuel du profil pour injecter dans le prompt."""
        lacunes_str = ", ".join(self.lacunes) if self.lacunes else "aucune identifiée"
        maitrise_str = ", ".join(self.notions_maitrisees) if self.notions_maitrisees else "en cours d'évaluation"
        return (
            f"Élève : {self.nom} | Niveau estimé : {self.niveau}/5\n"
            f"Notions maîtrisées : {maitrise_str}\n"
            f"Lacunes identifiées : {lacunes_str}\n"
            f"Score moyen : {self.score_moyen:.0%} ({self.nb_exercices} exercices)"
        )


# ══════════════════════════════════════════════════════
# RETRIEVER PÉDAGOGIQUE
# ══════════════════════════════════════════════════════

class PedagoRetriever:
    """
    Retriever RAG pédagogique adaptatif.
    Combine recherche vectorielle + filtres métadonnées + profil élève.
    """

    def __init__(self, store, eleve: EleveProfil = None):
        self.store  = store
        self.eleve  = eleve or EleveProfil(
            eleve_id="anonymous", nom="Étudiant",
            niveau=2, lacunes=[], notions_maitrisees=[]
        )

    # ── 1. Contexte pour question du tuteur ────────────
    def get_context_for_question(self, question: str, k: int = 4) -> list[dict]:
        """
        Récupère les chunks les plus pertinents pour répondre à une question.
        Adapte automatiquement au niveau de l'élève.
        """
        # Filtre adaptatif : ne pas dépasser le niveau + 1
        filters = {'difficulte': {'$lte': self.eleve.niveau + 1}}

        results = self.store.search(question, k=k, filters=filters)

        # Si pas assez de résultats filtrés, chercher sans filtre
        if len(results) < 2:
            results = self.store.search(question, k=k)

        return [_get_chunk(r) for r in results]

    # ── 2. Sélection d'exercices d'entraînement ────────
    def get_exercices_entrainement(self, notion: str = None,
                                   difficulte_cible: int = None,
                                   k: int = 5) -> list[dict]:
        """
        Sélectionne des exercices adaptés pour l'entraînement.
        Priorité aux lacunes détectées de l'élève.
        """
        if difficulte_cible is None:
            difficulte_cible = self.eleve.niveau

        query = notion or "exercice entraînement calcul"

        # Priorité 1 : exercices ciblant les lacunes
        if self.eleve.lacunes:
            lacune_query = " ".join(self.eleve.lacunes)
            results = self.store.search(
                lacune_query, k=k,
                filters={
                    'difficulte'   : {'$lte': difficulte_cible + 1},
                    'type_exercice': {'$in': ['simplification', 'calcul',
                                               'application', 'identite']}
                }
            )
            if len(results) >= 2:
                return [_get_chunk(r) for r in results]

        # Priorité 2 : exercices sur la notion demandée
        results = self.store.search(
            query, k=k,
            filters={'difficulte': {'$lte': difficulte_cible + 1}}
        )
        return [_get_chunk(r) for r in results]

    # ── 3. Sélection d'exercices d'évaluation ──────────
    def get_exercices_evaluation(self, nb_questions: int = 5,
                                  difficulte_min: int = None,
                                  difficulte_max: int = None) -> list[dict]:
        """
        Sélectionne un set d'évaluation équilibré.
        Couvre différents types et niveaux de difficulté.
        """
        if difficulte_min is None: difficulte_min = max(1, self.eleve.niveau - 1)
        if difficulte_max is None: difficulte_max = min(5, self.eleve.niveau + 1)

        selected = []
        types_voulus = ['calcul', 'simplification', 'application', 'qcm']

        for type_ex in types_voulus:
            if len(selected) >= nb_questions: break
            results = self.store.search(
                f"exercice {type_ex} mathématiques L1",
                k=2,
                filters={
                    'difficulte'   : {'$gte': difficulte_min, '$lte': difficulte_max},
                    'type_exercice': type_ex
                }
            )
            for r in results:
                if len(selected) < nb_questions:
                    selected.append(_get_chunk(r))

        # Compléter si besoin
        if len(selected) < nb_questions:
            extra = self.store.search(
                "exercice mathématiques L1",
                k=nb_questions - len(selected),
                filters={'difficulte': {'$lte': difficulte_max}}
            )
            ids_deja = {c['id'] for c in selected}
            for r in extra:
                if _get_chunk(r)['id'] not in ids_deja:
                    selected.append(_get_chunk(r))

        return selected[:nb_questions]

    # ── 4. Détection de lacunes ────────────────────────
    def detecter_lacunes(self, erreurs: list[dict]) -> list[str]:
        """
        Analyse les erreurs d'un élève et identifie les lacunes.
        erreurs = [{'chunk_id': ..., 'score': 0-100, 'reponse_eleve': ...}]
        """
        lacunes_detectees = {}

        for erreur in erreurs:
            if erreur.get('score', 100) >= 70:
                continue  # pas une erreur significative

            chunk = self.store.get_by_id(erreur['chunk_id'])
            if not chunk: continue

            m = chunk.get('metadata', {})
            concept = m.get('concept', '')
            lacunes = m.get('lacunes_type', [])
            prereqs = m.get('prerequis', [])

            # Comptabiliser la notion en difficulté
            if concept:
                lacunes_detectees[concept] = lacunes_detectees.get(concept, 0) + 1
            for lac in lacunes:
                lacunes_detectees[lac] = lacunes_detectees.get(lac, 0) + 1
            for pre in prereqs:
                lacunes_detectees[pre] = lacunes_detectees.get(pre, 0) + 0.5

        # Trier par fréquence et retourner les 3 principales
        sorted_lacunes = sorted(lacunes_detectees.items(),
                                key=lambda x: -x[1])
        return [k for k, v in sorted_lacunes[:3] if v >= 1]

    # ══════════════════════════════════════════════════
    # CONSTRUCTION DES PROMPTS
    # ══════════════════════════════════════════════════

    def build_tutor_prompt(self, question: str, context_chunks: list[dict]) -> str:
        """
        Construit le prompt complet pour le tuteur conversationnel.
        """
        context_str = _format_context(context_chunks)
        profil_str  = self.eleve.to_context_str()

        return f"""Tu es MATHutrice, un tuteur pédagogique bienveillant pour des étudiants de L1.

PROFIL DE L'ÉTUDIANT :
{profil_str}

CONTEXTE PÉDAGOGIQUE (extrait de la base de cours) :
{context_str}

QUESTION DE L'ÉTUDIANT :
{question}

INSTRUCTIONS :
- Adapte ton niveau de détail au profil de l'étudiant
- Si l'étudiant a des lacunes sur les prérequis, explique-les d'abord
- Utilise des exemples simples avant les cas généraux
- Encourage l'étudiant, reste positif
- Si la question dépasse son niveau actuel, propose une version plus simple
- Réponds en français, utilise la notation mathématique LaTeX quand nécessaire"""

    def build_evaluation_prompt(self, chunks: list[dict]) -> str:
        """
        Construit un prompt pour générer une évaluation à partir des chunks sélectionnés.
        """
        questions_str = _format_evaluation_questions(chunks)
        profil_str    = self.eleve.to_context_str()

        return f"""Tu es MATHutrice, un tuteur pédagogique.
Génère une évaluation formative pour cet étudiant.

PROFIL :
{profil_str}

QUESTIONS DE BASE (à utiliser comme inspiration) :
{questions_str}

INSTRUCTIONS :
- Génère {len(chunks)} questions adaptées au niveau {self.eleve.niveau}/5
- Varie les types : calcul direct, simplification, QCM, application
- Inclus la correction détaillée pour chaque question
- Ajoute des indices progressifs (3 niveaux d'aide possible)
- Format JSON : [{{"question": ..., "type": ..., "difficulte": ...,
  "correction": ..., "indices": [...]}}]"""

    def build_gap_analysis_prompt(self, erreurs: list[dict]) -> str:
        """
        Construit un prompt pour analyser les lacunes d'un élève.
        """
        lacunes = self.detecter_lacunes(erreurs)
        erreurs_str = "\n".join(
            f"- Question {e['chunk_id']} : score {e.get('score', '?')}%"
            for e in erreurs if e.get('score', 100) < 70
        )

        # Récupérer des exercices ciblés sur les lacunes
        remediation_chunks = []
        for lac in lacunes[:2]:
            chunks = self.get_exercices_entrainement(notion=lac, k=2)
            remediation_chunks.extend(chunks)

        remediation_str = _format_context(remediation_chunks[:4])

        return f"""Tu es MATHutrice. Analyse les résultats de cet étudiant et propose un plan de remédiation.

PROFIL :
{self.eleve.to_context_str()}

ERREURS DÉTECTÉES :
{erreurs_str if erreurs_str else "Aucune erreur significative"}

LACUNES IDENTIFIÉES :
{', '.join(lacunes) if lacunes else 'Aucune'}

EXERCICES DE REMÉDIATION DISPONIBLES :
{remediation_str}

Génère :
1. Un diagnostic clair des lacunes (2-3 phrases)
2. Un plan de révision en 3 étapes ordonnées
3. Les exercices prioritaires à faire (utilise ceux fournis en contexte)
4. Des conseils méthodologiques personnalisés"""

    # ── Interface LangChain native ─────────────────────
    def as_langchain_retriever(self, k: int = 4):
        """
        Retourne un retriever compatible LangChain BaseRetriever.
        Nécessite langchain installé en production.

        Exemple d'utilisation :
            from langchain.chains import ConversationalRetrievalChain
            chain = ConversationalRetrievalChain.from_llm(
                llm       = ChatOpenAI(model="gpt-4o"),
                retriever = pedagogo.as_langchain_retriever(k=4),
                memory    = ConversationBufferMemory(...)
            )
        """
        store   = self.store
        eleve   = self.eleve
        k_inner = k

        # Import tardif — pas disponible en local
        try:
            from langchain.schema import BaseRetriever, Document

            class _LCRetriever(BaseRetriever):
                def _get_relevant_documents(self, query: str):
                    results = store.search(
                        query, k=k_inner,
                        filters={'difficulte': {'$lte': eleve.niveau + 1}}
                    )
                    return [
                        Document(
                            page_content = _get_chunk(r)['text'],
                            metadata     = {
                                **_get_chunk(r).get('metadata', {}),
                                'chunk_id'       : _get_chunk(r)['id'],
                                'formula_images' : _get_chunk(r).get('formula_images', []),
                                'score'          : _get_score(r),
                            }
                        )
                        for r in results
                    ]

                async def _aget_relevant_documents(self, query):
                    return self._get_relevant_documents(query)

            return _LCRetriever()

        except ImportError:
            print("  ⚠ LangChain non installé — utilisez get_context_for_question() directement")
            return None


# ── Helpers de formatage ───────────────────────────────

def _format_context(chunks: list[dict]) -> str:
    if not chunks:
        return "Aucun contexte disponible."
    parts = []
    for i, c in enumerate(chunks, 1):
        m     = c.get('metadata', {})
        diff  = m.get('difficulte', '?')
        ctype = m.get('type_exercice', '')
        conc  = m.get('concept', '')
        imgs  = c.get('formula_images', [])
        img_note = f" [+{len(imgs)} image(s) de formule]" if imgs else ""
        parts.append(
            f"[{i}] {conc} — {ctype} (difficulté {diff}/5){img_note}\n"
            f"{c['text'][:400]}{'...' if len(c['text']) > 400 else ''}"
        )
    return "\n\n".join(parts)


def _format_evaluation_questions(chunks: list[dict]) -> str:
    parts = []
    for i, c in enumerate(chunks, 1):
        m = c.get('metadata', {})
        parts.append(
            f"Q{i} [{m.get('type_exercice','?')} | diff {m.get('difficulte','?')}/5] :\n"
            f"{c['text'][:300]}"
        )
    return "\n\n".join(parts)


# ══════════════════════════════════════════════════════
# DEMO / TEST
# ══════════════════════════════════════════════════════

def run_demo():
    """Démontre toutes les fonctionnalités du retriever."""
    from step3_vectorstore import LocalVectorStore, STORE_PATH  # même dossier rag/

    print("=" * 60)
    print("  ÉTAPE 4 — Démo du Retriever Pédagogique")
    print("=" * 60 + "\n")

    # Charger le store
    store = LocalVectorStore.load(STORE_PATH)

    # Créer un profil élève test
    eleve = EleveProfil(
        eleve_id           = "etudiant_42",
        nom                = "Alice",
        niveau             = 2,
        notions_maitrisees = ["fractions simples", "multiplication"],
        lacunes            = ["fractions algébriques", "puissances négatives"],
        score_moyen        = 0.61,
        nb_exercices       = 8
    )

    retriever = PedagoRetriever(store, eleve)

    # ── Test 1 : Tuteur conversationnel ────────────────
    print("─" * 60)
    print("TEST 1 — Contexte pour question tuteur")
    print("─" * 60)
    question = "Comment simplifier une fraction avec des exposants négatifs ?"
    ctx = retriever.get_context_for_question(question, k=3)
    print(f"  Question : {question}")
    print(f"  {len(ctx)} chunk(s) récupéré(s) :\n")
    for c in ctx:
        m = c['metadata']
        print(f"    [{m.get('difficulte','?')}/5] {c['id']:35s} | {m.get('concept','')}")
    prompt = retriever.build_tutor_prompt(question, ctx)
    print(f"\n  Prompt généré ({len(prompt)} chars) — début :")
    print("  " + prompt[:300].replace('\n', '\n  '))

    # ── Test 2 : Exercices d'entraînement ──────────────
    print(f"\n{'─' * 60}")
    print("TEST 2 — Exercices d'entraînement sur les lacunes")
    print("─" * 60)
    exos = retriever.get_exercices_entrainement(k=4)
    print(f"  {len(exos)} exercice(s) sélectionné(s) :\n")
    for e in exos:
        m = e['metadata']
        print(f"    [{m.get('difficulte','?')}/5] {e['id']:35s} | {m.get('concept','')[:35]}")

    # ── Test 3 : Évaluation ───────────────────────────
    print(f"\n{'─' * 60}")
    print("TEST 3 — Sélection d'exercices d'évaluation")
    print("─" * 60)
    eval_exos = retriever.get_exercices_evaluation(nb_questions=4)
    print(f"  {len(eval_exos)} question(s) pour l'évaluation :\n")
    for e in eval_exos:
        m = e['metadata']
        print(f"    [{m.get('difficulte','?')}/5] {m.get('type_exercice','?'):15s} "
              f"| {e['id']:30s} | {m.get('concept','')[:30]}")

    # ── Test 4 : Détection de lacunes ─────────────────
    print(f"\n{'─' * 60}")
    print("TEST 4 — Détection de lacunes à partir de résultats")
    print("─" * 60)
    faux_resultats = [
        {'chunk_id': eval_exos[0]['id'], 'score': 35} if eval_exos else {},
        {'chunk_id': eval_exos[1]['id'], 'score': 45} if len(eval_exos) > 1 else {},
        {'chunk_id': eval_exos[2]['id'], 'score': 80} if len(eval_exos) > 2 else {},
    ]
    faux_resultats = [r for r in faux_resultats if r]
    lacunes = retriever.detecter_lacunes(faux_resultats)
    print(f"  Résultats simulés : {[r.get('score') for r in faux_resultats]}%")
    print(f"  Lacunes détectées : {lacunes}")

    print(f"\n{'=' * 60}")
    print("  Démo terminée — Retriever opérationnel ✓")
    print(f"{'=' * 60}")

    return retriever


if __name__ == '__main__':
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    run_demo()
