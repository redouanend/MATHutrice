"""
qro_generator.py — Générateur de questions à réponse ouverte (QRO)

Format JSON produit par Mistral :
  {
    "question": "Texte de la question",
    "correct_answer": "La réponse attendue complète"
  }

Particularité : pas de vérification SymPy automatique (réponse ouverte).
La correction se fait par comparaison souple (normalisation de la chaîne)
+ un second appel Mistral en mode "correcteur" pour les cas ambigus.
"""

from base_generator import (
    call_mistral,
    generate_test,
    display_score,
    print_test_header,
    print_question_header,
    parse_json,
    logger,
    client,
    MODEL,
)


# GENERATE PROMPT  INSTRUCTIONS POUR MISTRAL

QRO_FORMAT = """
{
  "question": "Texte de la question",
  "correct_answer": "La réponse attendue (complète et précise)"
}
"""

def build_prompt(notion_nom: str, competence: dict) -> str:
    return f"""
Tu es un tuteur de mathématiques pour des étudiants de première année d'université.
Ta tâche est de générer UNE question à réponse ouverte (QRO) de mathématiques.

Informations :
- Notion : {notion_nom}
- Code compétence : {competence["code"]}
- Compétence ciblée : {competence["nom"]}
- Niveau : {competence["niveau"]}
- Score actuel : {competence["score"]}

Contraintes pédagogiques :
- La question doit évaluer principalement la compétence ciblée.
- La question doit être adaptée au niveau de la compétence.
- La question doit appeler une réponse courte et précise.
- La réponse attendue doit être concise : un résultat, une formule ou une expression.
- Les calculs doivent être mathématiquement corrects.
- Évite les questions trop générales ou qui nécessitent un long développement.

Règles de sortie — TRÈS IMPORTANT :
- Réponds UNIQUEMENT avec un JSON valide, rien d'autre.
- Pas de texte avant ou après le JSON.
- Pas de markdown, pas de balises ```json.
- Ne génère pas de champ "options" ni "answer".

Format attendu :
{QRO_FORMAT}
"""


# correction prompt (LLM-as-judge)


def build_correction_prompt(
    question: str, correct_answer: str, user_answer: str
) -> str:
    return f"""
Tu es un correcteur de mathématiques strict mais juste.

Question posée : {question}
Réponse attendue : {correct_answer}
Réponse de l'étudiant : {user_answer}

Ta tâche : dire si la réponse de l'étudiant est correcte ou non.

Règles :
- Accepte les réponses mathématiquement équivalentes (ex: "6x" et "6·x" sont identiques).
- Accepte les différences de notation mineures (ex: "1/2" et "0.5").
- Refuse les réponses incomplètes ou approximatives.
- Réponds UNIQUEMENT avec un JSON valide.
- Pas de texte avant ou après le JSON.

Format attendu :
{{
  "correct": true,
  "feedback": "Explication courte (1 phrase)"
}}
"""


# PARSING AND VALIDATION OF MISTRAL'S RESPONSE


def parse_and_validate(raw: str) -> dict:
    """
    Valide que la réponse brute de Mistral respecte le format QRO.
    Lève ValueError si un champ est manquant ou incorrect.
    """
    data = parse_json(raw)

    question = data.get("question", "").strip()
    correct_answer = data.get("correct_answer", "").strip()

    if not question:
        raise ValueError("Le champ 'question' est vide.")

    if not correct_answer:
        raise ValueError("Le champ 'correct_answer' est vide.")

    # PAS FORCEMENT UTILE SI LE PROMPT EST BIEN REALISER OU ALORS METTRE JUSTE PAS DE 3e COMPOSENTES DANS LE DICO
    # Sécurité : Mistral ne doit pas générer de champ "options" pour ce format
    if "options" in data:
        raise ValueError(
            "Format QRO invalide : champ 'options' présent (format QCM reçu)."
        )

    return {"question": question, "correct_answer": correct_answer}


# CORRECTION DE LA RÉPONSE ÉTUDIANT


def normalize(s: str) -> str:
    """Normalise une chaîne pour comparaison souple (minuscules, espaces, ponctuation)."""
    s = s.lower().strip()
    s = s.replace(" ", "").replace("*", "").replace("·", "")
    s = s.replace(",", ".").replace("−", "-")
    return s


def is_correct_simple(user_answer: str, correct_answer: str) -> bool:
    """Comparaison directe normalisée. Rapide, sans appel API."""
    return normalize(user_answer) == normalize(correct_answer)


def is_correct_llm(
    question: str, correct_answer: str, user_answer: str
) -> tuple[bool, str]:
    """
    Correction via Mistral (LLM-as-judge).
    Utilisée quand la comparaison simple ne suffit pas.
    Retourne (correct: bool, feedback: str).
    """
    prompt = build_correction_prompt(question, correct_answer, user_answer)
    try:
        response = client.chat.complete(
            model=MODEL, messages=[{"role": "user", "content": prompt}]
        )
        raw = response.choices[0].message.content
        data = parse_json(raw)

        correct = bool(data.get("correct", False))
        feedback = data.get("feedback", "").strip()
        return correct, feedback

    except Exception as e:
        logger.warning(
            f"Correction LLM échouée : {e}. Fallback sur comparaison simple."
        )
        return is_correct_simple(user_answer, correct_answer), ""


def evaluate_answer(q: dict, user_answer: str) -> tuple[bool, str]:
    """
    Évalue la réponse de l'étudiant en deux passes :
      1. Comparaison normalisée rapide (sans appel API)
      2. Si pas de match → LLM-as-judge (Mistral corrige)
    Retourne (correct: bool, feedback: str).
    """
    # comparaison simple
    if is_correct_simple(user_answer, q["correct_answer"]):
        return True, ""

    # LLM-as-judge
    logger.info("Comparaison simple insuffisante → appel correcteur LLM.")
    return is_correct_llm(q["question"], q["correct_answer"], user_answer)


# GÉNÉRATION


# def generate_qro_question(notion: str, niveau: str) -> dict | None:
#     """Génère une question QRO validée. Retourne None si échec."""
#     prompt = build_prompt(notion, niveau)
#     return call_mistral(prompt, notion, parse_and_validate)


# def generate_qro_test(notion: str, niveau: str, n: int) -> list[dict]:
#     """Génère un test de n questions QRO."""
#     return generate_test(notion, niveau, n, generate_qro_question)

def generate_qro_question(notion_nom: str, competence: dict) -> dict | None:
    """Génère une question QRO validée à partir d'une compétence déjà choisie."""

    prompt = build_prompt(
        notion_nom=notion_nom,
        competence=competence
    )

    return call_mistral(prompt, notion_nom, parse_and_validate)


def generate_qro_test(notion_nom: str, competences: list[dict]) -> list[dict]:
    """Génère un test QRO à partir d'une liste de compétences déjà choisies."""

    questions = []

    for competence in competences:
        question = generate_qro_question(notion_nom, competence)

        if question is not None:
            question["competence_cible"] = competence
            questions.append(question)

    return questions
# INTERFACE CONSOLE


def ask_question(index: int, total: int, q: dict) -> tuple[bool, str]:
    """Pose une question QRO dans le terminal. Retourne (correct, reponse_etudiant)."""
    print_question_header(index, total)
    print(f"\n{q['question']}\n")

    user_answer = input("Votre réponse : ").strip()

    if not user_answer:
        print("  ⚠ Réponse vide. Question comptée comme incorrecte.")
        print(f"  La réponse attendue était : {q['correct_answer']}")
        return False, ""

    correct, feedback = evaluate_answer(q, user_answer)

    if correct:
        print("  ✅ Correct !")
    else:
        print(f"  ❌ Incorrect. La réponse attendue était : {q['correct_answer']}")

    if feedback:
        print(f"  💬 {feedback}")

    return correct, user_answer


# Faut faire un run test globale des 3 formats
def run_test(questions: list[dict]) -> None:
    """Lance le test QRO en console et affiche le score final."""
    if not questions:
        print("Aucune question disponible. Abandon.")
        return

    total = len(questions)
    score = 0

    # print_test_header(total, "QRO")

    for i, q in enumerate(questions, 1):
        correct, _ = ask_question(i, total, q)
        if correct:
            score += 1

    display_score(score, total, "QRO")


# # ─── MAIN ─────────────────────────────────────────────────────────────────────

# def main(notion: str = "dérivées", niveau: str = "intermédiaire", n: int = 3):
#     questions = generate_qro_test(notion=notion, niveau=niveau, n=n)
#     run_test(questions)


# if __name__ == "__main__":
#     main(notion="dérivées", niveau="intermédiaire", n=3)
