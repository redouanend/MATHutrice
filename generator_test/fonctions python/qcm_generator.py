"""
qcm_generator.py — Générateur de questions QCM

Format JSON produit par Mistral :
  {
    "question": "Texte de la question",
    "options": ["rép1", "rép2", "rép3", "rép4"],
    "answer": "la bonne réponse (identique à l'une des options)"
  }

Particularité : vérification mathématique via SymPy (verifier.py)
Les réponses fausses de Mistral sont corrigées automatiquement.
"""

from base_generator import (
    call_mistral,
    generate_test,
    display_score,
    print_test_header,
    print_question_header,
    parse_json,
    logger,
)
from verifier import apply_verification


# ─── PROMPT ───────────────────────────────────────────────────────────────────

QCM_FORMAT = """
{
  "question": "Texte de la question",
  "options": ["rép1", "rép2", "rép3", "rép4"],
  "answer": "la bonne réponse (doit être identique à l'une des options)"
}
"""


def build_prompt(notion: str, niveau: str) -> str:
    return f"""
Tu es un tuteur de mathématiques pour des étudiants de première année d'université.
Ta tâche est de générer UNE question QCM de mathématiques.

Informations :
- Notion : {notion}
- Niveau : {niveau}

Contraintes pédagogiques :
- La question doit être adaptée au niveau demandé.
- L'énoncé doit être clair et sans ambiguïté.
- Les calculs doivent être mathématiquement corrects.
- Une seule réponse parmi les options est correcte.
- Les 3 mauvaises réponses doivent être plausibles (pas absurdes).

Règles de sortie — TRÈS IMPORTANT :
- Réponds UNIQUEMENT avec un JSON valide, rien d'autre.
- Pas de texte avant ou après le JSON.
- Pas de markdown, pas de balises ```json.
- Le champ "answer" doit être une chaîne identique à l'une des options.

Format attendu :
{QCM_FORMAT}
"""


# ─── PARSING & VALIDATION ─────────────────────────────────────────────────────


def parse_and_validate(raw: str) -> dict:
    """
    Valide que la réponse brute de Mistral respecte le format QCM.
    Lève ValueError si un champ est manquant ou incorrect.
    """
    data = parse_json(raw)

    question = data.get("question", "").strip()
    options = data.get("options", [])
    answer = data.get("answer", "")

    if not question:
        raise ValueError("Le champ 'question' est vide.")

    if not isinstance(options, list) or len(options) != 4:
        raise ValueError(
            f"'options' doit contenir exactement 4 éléments, reçu : {len(options)}."
        )

    if not all(isinstance(o, str) and o.strip() for o in options):
        raise ValueError("Toutes les options doivent être des chaînes non vides.")

    if not isinstance(answer, str) or answer.strip() not in options:
        raise ValueError(
            f"'answer' doit être identique à l'une des options. Reçu : '{answer}'"
        )

    return {"question": question, "options": options, "answer": answer.strip()}


# ─── POST-PROCESSING : vérification SymPy ─────────────────────────────────────


def post_process(question: dict) -> dict:
    """Applique la vérification mathématique SymPy après validation du format."""
    question = apply_verification(question)
    if question.get("corrected"):
        logger.warning("Réponse de Mistral corrigée par SymPy.")
    return question


# ─── GÉNÉRATION ───────────────────────────────────────────────────────────────


def generate_qcm_question(notion: str, niveau: str) -> dict | None:
    """Génère une question QCM validée et vérifiée. Retourne None si échec."""
    prompt = build_prompt(notion, niveau)
    return call_mistral(prompt, notion, parse_and_validate, post_process)


def generate_qcm_test(notion: str, niveau: str, n: int) -> list[dict]:
    """Génère un test de n questions QCM."""
    return generate_test(notion, niveau, n, generate_qcm_question)


# ─── INTERFACE CONSOLE ────────────────────────────────────────────────────────


def ask_question(index: int, total: int, q: dict) -> bool:
    """Pose une question QCM dans le terminal. Retourne True si bonne réponse."""
    verified = q.get("verified", False)
    corrected = q.get("corrected", False)

    if corrected:
        status = "⚠ corrigée par SymPy"
    elif verified:
        status = "✅ vérifiée"
    else:
        status = "🔵 non vérifiée"

    print_question_header(index, total, status)
    print(f"\n{q['question']}\n")

    for i, option in enumerate(q["options"], 1):
        print(f"  {i}. {option}")

    while True:
        raw = input("\nVotre réponse (1-4) : ").strip()
        if raw.isdigit() and 1 <= int(raw) <= 4:
            break
        print("  ⚠ Entrez un chiffre entre 1 et 4.")

    chosen = q["options"][int(raw) - 1]
    correct = chosen == q["answer"]

    if correct:
        print("  ✅ Correct !")
    else:
        print(f"  ❌ Incorrect. La bonne réponse était : {q['answer']}")

    return correct


# Faut faire un main globale des 3 formats
def run_test(questions: list[dict]) -> None:
    """Lance le test QCM en console et affiche le score final."""
    if not questions:
        print("Aucune question disponible. Abandon.")
        return

    total = len(questions)
    score = 0

    # print_test_header(total, "QCM")

    for i, q in enumerate(questions, 1):
        if ask_question(i, total, q):
            score += 1

    display_score(score, total, "QCM")


# # ─── MAIN ─────────────────────────────────────────────────────────────────────

# def main(notion: str = "trigonométrie", niveau: str = "intermédiaire", n: int = 3):
#     questions = generate_qcm_test(notion=notion, niveau=niveau, n=n)
#     run_test(questions)


# if __name__ == "__main__":
#     main(notion="trigonométrie", niveau="intermédiaire", n=3)
