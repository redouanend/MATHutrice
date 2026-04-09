"""
trous_generator.py — Générateur de phrases à trous guidées

Format JSON produit par Mistral :
  {
    "enonce": "Contexte ou rappel de cours introduisant l'exercice",
    "phrases": [
      "La dérivée de x² est ___.",
      "cos(0) = ___.",
      "Le module de z = 3 + 4i est ___."
    ],
    "correct_answers": ["2x", "1", "5"]
  }

Principe : chaque phrase a un seul trou (___)  à compléter.
L'étudiant complète les trous un par un dans le terminal.
La correction utilise la même logique double-passe que le QRO
(comparaison normalisée → LLM-as-judge si nécessaire).
"""

from base_generator import (
    call_mistral, generate_test, display_score,
    print_test_header, print_question_header, parse_json, logger, client, MODEL
)
from qro_generator import evaluate_answer  # même logique de correction


# ─── PROMPT DE GÉNÉRATION ─────────────────────────────────────────────────────

TROUS_FORMAT = """
{
  "enonce": "Rappel de cours ou contexte de l'exercice (1-2 phrases)",
  "phrases": [
    "Première phrase avec un seul trou noté ___.",
    "Deuxième phrase avec un seul trou noté ___.",
    "Troisième phrase avec un seul trou noté ___."
  ],
  "correct_answers": [
    "réponse au trou 1",
    "réponse au trou 2",
    "réponse au trou 3"
  ]
}
"""

def build_prompt(notion: str, niveau: str) -> str:
    return f"""
Tu es un tuteur de mathématiques pour des étudiants de première année d'université.
Ta tâche est de générer UN exercice de phrases à trous guidées en mathématiques.

Informations :
- Notion : {notion}
- Niveau : {niveau}

Contraintes pédagogiques :
- L'énoncé doit rappeler brièvement le contexte ou la formule clé.
- Chaque phrase doit contenir EXACTEMENT un seul trou noté ___.
- Le trou doit être placé à la fin ou dans la phrase de façon naturelle.
- Les réponses doivent être courtes : un résultat, une formule, une valeur.
- Génère entre 3 et 5 phrases selon la complexité de la notion.
- "phrases" et "correct_answers" doivent avoir exactement la même longueur.
- Les calculs doivent être mathématiquement corrects.

Exemples de bonnes phrases à trous :
  "La dérivée de xⁿ est ___."  →  "n·x^(n-1)"
  "cos(π) = ___."               →  "-1"
  "Le conjugué de z = a + bi est ___."  →  "a - bi"

Règles de sortie — TRÈS IMPORTANT :
- Réponds UNIQUEMENT avec un JSON valide, rien d'autre.
- Pas de texte avant ou après le JSON.
- Pas de markdown, pas de balises ```json.
- Chaque phrase doit contenir le mot ___ (trois underscores) exactement une fois.

Format attendu :
{TROUS_FORMAT}
"""


# ─── PARSING & VALIDATION ─────────────────────────────────────────────────────

def parse_and_validate(raw: str) -> dict:
    """
    Valide que la réponse brute de Mistral respecte le format phrases à trous.
    Lève ValueError si un champ est manquant ou incohérent.
    """
    data = parse_json(raw)

    enonce          = data.get("enonce", "").strip()
    phrases         = data.get("phrases", [])
    correct_answers = data.get("correct_answers", [])

    if not enonce:
        raise ValueError("Le champ 'enonce' est vide.")

    if not isinstance(phrases, list) or len(phrases) == 0:
        raise ValueError("Le champ 'phrases' doit être une liste non vide.")

    if not isinstance(correct_answers, list) or len(correct_answers) == 0:
        raise ValueError("Le champ 'correct_answers' doit être une liste non vide.")

    if len(phrases) != len(correct_answers):
        raise ValueError(
            f"'phrases' ({len(phrases)}) et 'correct_answers' ({len(correct_answers)}) "
            f"doivent avoir la même longueur."
        )

    if not all(isinstance(p, str) and p.strip() for p in phrases):
        raise ValueError("Toutes les phrases doivent être des chaînes non vides.")

    if not all(isinstance(a, str) and a.strip() for a in correct_answers):
        raise ValueError("Toutes les réponses doivent être des chaînes non vides.")

    # Vérifie que chaque phrase contient exactement un ___
    for i, phrase in enumerate(phrases):
        count = phrase.count("___")
        if count == 0:
            raise ValueError(f"Phrase {i+1} ne contient pas de trou '___' : '{phrase}'")
        if count > 1:
            raise ValueError(f"Phrase {i+1} contient {count} trous (max 1 attendu) : '{phrase}'")

    return {
        "enonce":          enonce,
        "phrases":         [p.strip() for p in phrases],
        "correct_answers": [a.strip() for a in correct_answers],
    }


# ─── GÉNÉRATION ───────────────────────────────────────────────────────────────

def generate_trous_question(notion: str, niveau: str) -> dict | None:
    """Génère un exercice phrases à trous validé. Retourne None si échec."""
    prompt = build_prompt(notion, niveau)
    return call_mistral(prompt, notion, parse_and_validate)


def generate_trous_test(notion: str, niveau: str, n: int) -> list[dict]:
    """
    Génère n exercices phrases à trous.
    Note : chaque exercice contient lui-même plusieurs phrases (3 à 5).
    """
    return generate_test(notion, niveau, n, generate_trous_question)


# ─── INTERFACE CONSOLE ────────────────────────────────────────────────────────

def ask_exercice(index: int, total: int, ex: dict) -> tuple[int, int]:
    """
    Pose un exercice phrases à trous dans le terminal.
    Retourne (score_obtenu, total_phrases) pour cet exercice.
    """
    print_question_header(index, total)
    print(f"\n📖 {ex['enonce']}\n")
    print("Complétez les phrases suivantes (remplacez ___ par votre réponse) :\n")

    score_ex = 0
    total_ex = len(ex["phrases"])

    for i, (phrase, correct) in enumerate(
        zip(ex["phrases"], ex["correct_answers"]), 1
    ):
        print(f"  {i}. {phrase}")
        user_answer = input("     Votre réponse : ").strip()

        if not user_answer:
            print(f"     ⚠ Réponse vide. Réponse attendue : {correct}")
            continue

        # Construit un faux dict QRO pour réutiliser evaluate_answer
        q_temp = {"question": phrase, "correct_answer": correct}
        correct_flag, feedback = evaluate_answer(q_temp, user_answer)

        if correct_flag:
            print("     ✅ Correct !")
            score_ex += 1
        else:
            print(f"     ❌ Incorrect. Réponse attendue : {correct}")

        if feedback:
            print(f"     💬 {feedback}")

        print()

    print(f"  → Score pour cet exercice : {score_ex}/{total_ex}")
    return score_ex, total_ex


def run_test(exercices: list[dict]) -> None:
    """Lance le test phrases à trous en console et affiche le score final."""
    if not exercices:
        print("Aucun exercice disponible. Abandon.")
        return

    total_ex  = len(exercices)
    score_total = 0
    max_total   = 0

    print_test_header(total_ex, "PHRASES À TROUS")

    for i, ex in enumerate(exercices, 1):
        score_ex, nb_phrases = ask_exercice(i, total_ex, ex)
        score_total += score_ex
        max_total   += nb_phrases

    display_score(score_total, max_total, "PHRASES À TROUS")


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main(notion: str = "nombres complexes", niveau: str = "intermédiaire", n: int = 2):
    exercices = generate_trous_test(notion=notion, niveau=niveau, n=n)
    run_test(exercices)


if __name__ == "__main__":
    main(notion="nombres complexes", niveau="intermédiaire", n=2)
