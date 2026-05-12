"""
main.py — Point d'entrée principal (version RAG)

Changements vs version originale :
  1. Import de RAGBridge et EleveContext
  2. Chargement du bridge au démarrage (une seule fois)
  3. Les appels generate_*_test() sont remplacés par bridge.generate_*()
     avec le profil élève en paramètre
  → Tout le reste est IDENTIQUE à l'original

Usage :
  python main.py                         # menu interactif
  python main.py --format qcm --notion "fractions" --niveau "débutant" --n 3
"""

import argparse
import logging

# ── Imports originaux (inchangés) ──────────────────────
from type_questions.qcm_generator   import run_test as run_qcm
from type_questions.qro_generator   import run_test as run_qro
from type_questions.steps_generator import run_test as run_sbs
from type_questions.trous_generator import run_test as run_trous

# ── AJOUT RAG ──────────────────────────────────────────
from rag_bridge import RAGBridge, EleveContext

logging.basicConfig(level=logging.WARNING, format="%(levelname)s | %(message)s")

# Chargement du bridge une seule fois au démarrage
# (si le vectorstore n'existe pas → mode dégradé sans RAG, aucun crash)
bridge = RAGBridge.load()

# ─────────────────────────────────────────────────────────

NOTIONS = [
    "fractions",
    "puissances",
    "radicaux",
    "trigonométrie",
    "dérivées",
    "nombres complexes",
]

NIVEAUX = ["débutant", "intermédiaire", "avancé"]

FORMATS = {
    "qcm"  : run_qcm,
    "qro"  : run_qro,
    "sbs"  : run_sbs,
    "trous": run_trous,
}

NIVEAU_TO_INT = {"débutant": 1, "intermédiaire": 3, "avancé": 5}


# ─── MENU INTERACTIF (inchangé) ───────────────────────

def choose_from(label: str, options: list[str]) -> str:
    print(f"\n{label}")
    for i, opt in enumerate(options, 1):
        print(f"  {i}. {opt}")
    while True:
        raw = input(f"Votre choix (1-{len(options)}) : ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1]
        print(f"  ⚠ Entrez un chiffre entre 1 et {len(options)}.")


def interactive_menu():
    print("\n" + "═" * 50)
    print("  MATHutrice — Générateur de tests")
    print("═" * 50)

    fmt    = choose_from("Format :", list(FORMATS.keys()))
    notion = choose_from("Notion :", NOTIONS)
    niveau = choose_from("Niveau :", NIVEAUX)

    while True:
        raw = input("\nNombre de questions (1-10) : ").strip()
        if raw.isdigit() and 1 <= int(raw) <= 10:
            n = int(raw)
            break
        print("  ⚠ Entrez un nombre entre 1 et 10.")

    return fmt, notion, niveau, n


# ─── GÉNÉRATION ENRICHIE PAR LE RAG ──────────────────
# Remplace les anciens appels generate_*_test()

def generate_with_rag(fmt: str, notion: str, niveau: str,
                      n: int, eleve: EleveContext = None) -> list[dict]:
    """
    Génère des questions avec contexte RAG.
    Si le vectorstore n'est pas chargé → fallback automatique sans RAG.
    """
    eleve = eleve or EleveContext(
        niveau = NIVEAU_TO_INT.get(niveau, 2)
    )

    generators = {
        "qcm"  : bridge.generate_qcm,
        "qro"  : bridge.generate_qro,
        "sbs"  : bridge.generate_steps,
        "trous": bridge.generate_trous,
    }

    gen_fn = generators.get(fmt)
    if not gen_fn:
        print(f"Format inconnu : '{fmt}'")
        return []

    return gen_fn(notion, niveau, n, eleve)


def generate_mixed_test(notion: str, niveau: str,
                         n_qcm: int = 0, n_qro: int = 0,
                         n_steps: int = 0, n_trous: int = 0,
                         eleve: EleveContext = None) -> list[dict]:
    """Génère un test mixte enrichi par le RAG."""
    test = []
    eleve = eleve or EleveContext(niveau=NIVEAU_TO_INT.get(niveau, 2))

    for fmt, n in [("qcm", n_qcm), ("qro", n_qro),
                   ("sbs", n_steps), ("trous", n_trous)]:
        if n > 0:
            questions = generate_with_rag(fmt, notion, niveau, n, eleve)
            for q in questions:
                q["type"] = fmt
            test.extend(questions)

    return test


# ─── RUN TEST MIXTE (inchangé) ────────────────────────

def run_test(questions: list[dict]) -> None:
    total = len(questions)
    run_map = {"qcm": run_qcm, "qro": run_qro,
               "sbs": run_sbs, "trous": run_trous}

    for i, question in enumerate(questions, start=1):
        q_type = question.get("type")
        print(f"\n--- Question {i}/{total} ---")
        runner = run_map.get(q_type)
        if runner:
            runner([question])
        else:
            print(f"Type inconnu : {q_type}")


# ─── ARGPARSE ─────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="MATHutrice — Générateur de tests avec RAG"
    )
    parser.add_argument("--format", choices=list(FORMATS.keys()), default=None)
    parser.add_argument("--notion", type=str, default=None)
    parser.add_argument("--niveau", choices=NIVEAUX, default=None)
    parser.add_argument("--n",      type=int, default=None)
    # Paramètres élève optionnels (pour simulation / tests)
    parser.add_argument("--eleve-niveau", type=int, default=None,
                        help="Niveau élève 1-5 (override le niveau textuel)")
    parser.add_argument("--lacunes", type=str, default="",
                        help="Lacunes séparées par des virgules (ex: 'fractions,puissances')")
    return parser.parse_args()


# ─── MAIN ─────────────────────────────────────────────

def main():
    args = parse_args()

    # Construire le profil élève depuis les args
    eleve = EleveContext(
        niveau  = args.eleve_niveau or NIVEAU_TO_INT.get(args.niveau or "intermédiaire", 2),
        lacunes = [l.strip() for l in args.lacunes.split(",") if l.strip()]
    )

    # Mode direct si tous les args sont fournis
    if all([args.format, args.notion, args.niveau, args.n]):
        questions = generate_with_rag(
            args.format, args.notion, args.niveau, args.n, eleve
        )
        run_map = {"qcm": run_qcm, "qro": run_qro,
                   "sbs": run_sbs, "trous": run_trous}
        run_map[args.format](questions)

    # Sinon → menu interactif
    else:
        fmt, notion, niveau, n = interactive_menu()
        eleve.niveau = NIVEAU_TO_INT.get(niveau, 2)
        questions    = generate_with_rag(fmt, notion, niveau, n, eleve)
        FORMATS[fmt](questions)

    # Afficher les stats RAG en fin de session
    if bridge._ready:
        stats = bridge.stats()
        print(f"\n📊 RAG actif — {stats['total_chunks']} chunks "
              f"({stats.get('llm_enriched_pct', 0)}% enrichis LLM)")


if __name__ == "__main__":
    main()
