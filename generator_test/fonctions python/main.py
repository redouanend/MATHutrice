"""
main.py — Point d'entrée principal

Lance un test en choisissant :
  - Le format  : qcm | qro | trous
  - La notion  : trigonométrie | fractions | dérivées | nombres complexes | ...
  - Le niveau  : débutant | intermédiaire | avancé
  - Le nombre  : n questions (ou exercices pour les trous)

Usage :
  python main.py                         # paramètres par défaut
  python main.py --format qro            # format QRO
  python main.py --format trous --n 2    # 2 exercices phrases à trous
  python main.py --format qcm --notion "fractions" --niveau "débutant" --n 5
"""

import argparse

from qcm_generator import generate_qcm_test, run_test as run_qcm
from qro_generator import generate_qro_test, run_test as run_qro
from steps_generator import generate_steps_test, run_test as run_sbs


# ─── NOTIONS DISPONIBLES ──────────────────────────────────────────────────────

NOTIONS = [
    "trigonométrie",
    "fractions",
    "dérivées",
    "nombres complexes",
]

NIVEAUX = ["débutant", "intermédiaire", "avancé"]

FORMATS = {
    "qcm": (generate_qcm_test, run_qcm),
    "qro": (generate_qro_test, run_qro),
    "sbs": (generate_steps_test, run_sbs),
}


# ─── MENU INTERACTIF ──────────────────────────────────────────────────────────


def choose_from(label: str, options: list[str]) -> str:
    """Affiche un menu numéroté et retourne le choix de l'utilisateur."""
    print(f"\n{label}")
    for i, opt in enumerate(options, 1):
        print(f"  {i}. {opt}")

    while True:
        raw = input(f"Votre choix (1-{len(options)}) : ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1]
        print(f"  ⚠ Entrez un chiffre entre 1 et {len(options)}.")


def interactive_menu() -> tuple[str, str, str, int]:
    """Lance le menu interactif et retourne (notion, niveau, n)."""
    print("\n" + "═" * 50)
    print("  MATHTUTORIA — Générateur de tests")
    print("═" * 50)

    notion = choose_from("Notion :", NOTIONS)
    niveau = choose_from("Niveau :", NIVEAUX)

    while True:
        raw = input("\nNombre de questions (1-10) : ").strip()
        if raw.isdigit() and 1 <= int(raw) <= 10:
            n = int(raw)
            break
        print("  ⚠ Entrez un nombre entre 1 et 10.")

    return notion, niveau, n


# ─── LANCEMENT DU TEST ────────────────────────────────────────────────────────


def run(fmt: str, notion: str, niveau: str, n: int) -> None:
    """Génère et lance le test selon le format choisi."""
    if fmt not in FORMATS:
        print(f"Format inconnu : '{fmt}'. Choisir parmi : {list(FORMATS.keys())}")
        return

    generate_fn, run_fn = FORMATS[fmt]
    questions = generate_fn(notion=notion, niveau=niveau, n=n)
    run_fn(questions)


def generate_mixed_test(
    notion: str,
    niveau: str,
    n_qcm: int = 0,
    n_qro: int = 0,
    n_steps: int = 0,
) -> list[dict]:
    """Génère un test mixte avec QCM, QRO et step by step."""
    test = []

    if n_qcm > 0:
        qcms = generate_qcm_test(notion, niveau, n_qcm)
        for q in qcms:
            q["type"] = "qcm"
        test.extend(qcms)

    if n_qro > 0:
        qros = generate_qro_test(notion, niveau, n_qro)
        for q in qros:
            q["type"] = "qro"
        test.extend(qros)

    if n_steps > 0:
        steps = generate_steps_test(notion, niveau, n_steps)
        for q in steps:
            q["type"] = "sbs"
        test.extend(steps)

    return test


def run_test(questions: list[dict]) -> None:
    """Lance un test mixte en exécutant chaque question selon son type."""
    total = len(questions)
    for i, question in enumerate(questions, start=1):
        q_type = question.get("type")

        print(f"\n--- Question {i} ---/{total}")

        if q_type == "qcm":
            run_qcm([question])

        elif q_type == "qro":
            run_qro([question])

        elif q_type == "sbs":
            run_sbs([question])

        else:
            print(f"Type de question inconnu : {q_type}")


# ─── ARGPARSE ─────────────────────────────────────────────────────────────────


def parse_args():
    parser = argparse.ArgumentParser(
        description="Générateur de tests de mathématiques via Mistral AI"
    )
    parser.add_argument(
        "--format",
        choices=list(FORMATS.keys()),
        default=None,
        help="Format du test : qcm | qro | trous",
    )
    parser.add_argument(
        "--notion",
        type=str,
        default=None,
        help=f"Notion mathématique. Exemples : {', '.join(NOTIONS)}",
    )
    parser.add_argument(
        "--niveau",
        choices=NIVEAUX,
        default=None,
        help="Niveau de difficulté : débutant | intermédiaire | avancé",
    )
    parser.add_argument(
        "--n", type=int, default=None, help="Nombre de questions à générer (1-10)"
    )
    return parser.parse_args()


# ─── MAIN ─────────────────────────────────────────────────────────────────────


def main():
    args = parse_args()

    # Si tous les arguments sont fournis en ligne de commande → mode direct
    if all([args.format, args.notion, args.niveau, args.n]):
        test = generate_mixed_test(
            args.format, args.notion, args.niveau, args.n, args.n, args.n
        )
        run_test(test)

    # Sinon → menu interactif (les args partiels sont ignorés)
    else:
        notion, niveau, n = interactive_menu()
        test = generate_mixed_test(notion, niveau, n, n, n)
        run_test(test)


if __name__ == "__main__":
    main()
