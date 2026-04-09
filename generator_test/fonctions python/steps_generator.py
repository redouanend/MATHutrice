"""
steps_generator.py — Générateur d'exercices step by step

Format JSON produit par Mistral :
  {
    "enonce": "Texte complet du problème à résoudre",
    "questions": [
      "Étape 1 : ...",
      "Étape 2 : ...",
      "Étape n : ..."
    ],
    "correct_answers": [
      "Réponse à l'étape 1",
      "Réponse à l'étape 2",
      "Réponse à l'étape n"
    ]
  }

Principe : Mistral décompose un problème en étapes dans l'ordre logique
de résolution. L'étudiant répond étape par étape.
Si une étape est fausse, le programme le signale et continue quand même
— pour détecter exactement où est l'erreur de raisonnement.

Différence avec trous_generator :
  - trous  : phrases à compléter avec un ___ (réponses très courtes)
  - steps  : questions libres sur chaque étape de résolution (réponses plus longues)
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
from qro_generator import evaluate_answer


# ─── PROMPT ───────────────────────────────────────────────────────────────────

STEPS_FORMAT = """
{
  "enonce": "Texte complet du problème à résoudre",
  "questions": [
    "Étape 1 : question sur la première sous-étape",
    "Étape 2 : question sur la deuxième sous-étape",
    "Étape n : question sur la dernière sous-étape"
  ],
  "correct_answers": [
    "Réponse attendue à l'étape 1",
    "Réponse attendue à l'étape 2",
    "Réponse attendue à l'étape n"
  ]
}
"""


def build_prompt(notion: str, niveau: str) -> str:
    return f"""
Tu es un tuteur de mathématiques pour des étudiants de première année d'université.
Ta tâche est de générer UN exercice de mathématiques décomposé en étapes.

Informations :
- Notion : {notion}
- Niveau : {niveau}

Contraintes pédagogiques :
- L'énoncé doit présenter un problème complet à résoudre.
- Décompose la résolution en étapes dans l'ordre logique exact.
- Chaque étape doit être une sous-question précise et indépendante.
- Les étapes doivent être suffisamment détaillées pour identifier exactement
  où un étudiant fait une erreur (entre 3 et 6 étapes selon la complexité).
- Chaque correct_answer doit être la réponse attendue à cette étape précise.
- Les calculs doivent être mathématiquement corrects.

Exemples de bonnes étapes :
  Problème : Calculer la dérivée de f(x) = x² · sin(x)
  Étape 1 : "Quelle règle de dérivation faut-il utiliser ici ?"  → "La règle du produit : (uv)' = u'v + uv'"
  Étape 2 : "Que vaut u' si u = x² ?"                           → "u' = 2x"
  Étape 3 : "Que vaut v' si v = sin(x) ?"                       → "v' = cos(x)"
  Étape 4 : "Donne l'expression finale de f'(x)"                → "f'(x) = 2x·sin(x) + x²·cos(x)"

Règles de sortie — TRÈS IMPORTANT :
- Réponds UNIQUEMENT avec un JSON valide, rien d'autre.
- Pas de texte avant ou après le JSON.
- Pas de markdown, pas de balises ```json.
- "questions" et "correct_answers" doivent avoir exactement la même longueur.

Format attendu :
{STEPS_FORMAT}
"""


# ─── PARSING & VALIDATION ─────────────────────────────────────────────────────


def parse_and_validate(raw: str) -> dict:
    """
    Valide que la réponse brute de Mistral respecte le format step by step.
    Lève ValueError si un champ est manquant ou incohérent.
    """
    data = parse_json(raw)

    enonce = data.get("enonce", "").strip()
    questions = data.get("questions", [])
    correct_answers = data.get("correct_answers", [])

    if not enonce:
        raise ValueError("Le champ 'enonce' est vide.")

    if not isinstance(questions, list) or len(questions) == 0:
        raise ValueError("Le champ 'questions' doit être une liste non vide.")

    if not isinstance(correct_answers, list) or len(correct_answers) == 0:
        raise ValueError("Le champ 'correct_answers' doit être une liste non vide.")

    if len(questions) != len(correct_answers):
        raise ValueError(
            f"'questions' ({len(questions)}) et 'correct_answers' ({len(correct_answers)}) "
            f"doivent avoir la même longueur."
        )

    if not all(isinstance(q, str) and q.strip() for q in questions):
        raise ValueError("Toutes les questions doivent être des chaînes non vides.")

    if not all(isinstance(a, str) and a.strip() for a in correct_answers):
        raise ValueError(
            "Toutes les correct_answers doivent être des chaînes non vides."
        )

    return {
        "enonce": enonce,
        "questions": [q.strip() for q in questions],
        "correct_answers": [a.strip() for a in correct_answers],
    }


# ─── GÉNÉRATION ───────────────────────────────────────────────────────────────


def generate_steps_question(notion: str, niveau: str) -> dict | None:
    """Génère un exercice step by step validé. Retourne None si échec."""
    prompt = build_prompt(notion, niveau)
    return call_mistral(prompt, notion, parse_and_validate)


def generate_steps_test(notion: str, niveau: str, n: int) -> list[dict]:
    """Génère n exercices step by step."""
    return generate_test(notion, niveau, n, generate_steps_question)


# ─── INTERFACE CONSOLE ────────────────────────────────────────────────────────


def ask_exercice(index: int, total: int, ex: dict) -> tuple[int, int]:
    """
    Pose un exercice step by step dans le terminal.
    Affiche toutes les étapes même si l'étudiant se trompe
    — l'objectif est de détecter exactement où est l'erreur.
    Retourne (score_obtenu, total_etapes).
    """
    print_question_header(index, total)
    print(f"\n📋 Énoncé :\n{ex['enonce']}\n")
    print(
        f"Cet exercice comporte {len(ex['questions'])} étape(s). "
        f"Répondez à chaque étape dans l'ordre.\n"
    )

    score_ex = 0
    total_ex = len(ex["questions"])
    first_error = None  # index de la première étape fausse

    for i, (question, correct) in enumerate(
        zip(ex["questions"], ex["correct_answers"]), 1
    ):
        print(f"  {'─' * 44}")
        print(f"  Étape {i}/{total_ex} : {question}")

        user_answer = input("  Votre réponse : ").strip()

        if not user_answer:
            print(f"  ⚠ Réponse vide.")
            print(f"  Réponse attendue : {correct}")
            if first_error is None:
                first_error = i
            print()
            continue

        q_temp = {"question": question, "correct_answer": correct}
        correct_flag, feedback = evaluate_answer(q_temp, user_answer)

        if correct_flag:
            print("  ✅ Correct !")
            score_ex += 1
        else:
            print(f"  ❌ Incorrect. Réponse attendue : {correct}")
            if first_error is None:
                first_error = i

        if feedback:
            print(f"  💬 {feedback}")

        print()

    # Résumé de l'exercice
    print(f"  {'═' * 44}")
    print(f"  Score : {score_ex}/{total_ex}")
    if first_error:
        print(
            f"  ⚠ Première erreur détectée à l'étape {first_error} — "
            f"c'est là que le raisonnement diverge."
        )
    else:
        print("  🏆 Toutes les étapes sont correctes !")
    print(f"  {'═' * 44}\n")

    return score_ex, total_ex


def run_test(exercices: list[dict]) -> None:
    """Lance le test step by step en console et affiche le score final."""
    if not exercices:
        print("Aucun exercice disponible. Abandon.")
        return

    total_ex = len(exercices)
    score_total = 0
    max_total = 0

    # print_test_header(total_ex, "STEP BY STEP")

    for i, ex in enumerate(exercices, 1):
        score_ex, nb_etapes = ask_exercice(i, total_ex, ex)
        score_total += score_ex
        max_total += nb_etapes

    display_score(score_total, max_total, "STEP BY STEP")


# ─── MAIN ─────────────────────────────────────────────────────────────────────


def main(notion: str = "dérivées", niveau: str = "intermédiaire", n: int = 2):
    exercices = generate_steps_test(notion=notion, niveau=niveau, n=n)
    run_test(exercices)


if __name__ == "__main__":
    main(notion="dérivées", niveau="intermédiaire", n=2)
