#test_franklin

from mistralai import Mistral
import json
import re

API_KEY = "fOTxUhR9dDPIsmNOCRIxggr0Erhew4yk"

client = Mistral(api_key=API_KEY)

MODEL = "mistral-small"


# generate a prompt
def genererate_prompt(notion, niveau, format):
    prompt = prompt = f"""
                Tu es un tuteur de mathématiques pour des étudiants de première année d'université.

                Ta tâche est de générer un exercice de mathématiques.

                Informations :
                - Notion : {notion}
                - Niveau : {niveau}

                Contraintes pédagogiques :
                - L'exercice doit être adapté au niveau demandé.
                - L'énoncé doit être clair et sans ambiguïté.
                - Les calculs doivent être mathématiquement corrects.
                - Utilise un vocabulaire simple et pédagogique.

                Règles de sortie (très important) :
                - Réponds uniquement avec un JSON valide.
                - N'ajoute aucun texte avant ou après le JSON.
                - N'utilise pas de markdown.
                - N'utilise pas de balises ```json.

                Format attendu :
                {format}

                Important :
                Réponds uniquement avec le JSON correspondant au format.
                """
    return prompt


# List of Notions
notions = ["trigonométrie", "nombres complexes", "fractions"]

# notions selected
notion = notions[0]

# niveau de l'éléve (non adaptatif)
niveau = "intermédaire"

# format de question
formats = [
    # 1. QCM
    """
        {
        "question": "Texte de la question",
        "options": ["rép1", "rép2", "rép3", "rép4"],
        "answer": "bonne reponse exacte""
        }

        Règles spécifiques :
        - Réponds uniquement avec un JSON valide.
        - "options" doit contenir exactement 4 propositions.
        - Une seule réponse est correcte.
        - La bonne réponse doit être présente dans "options".
        - Ne mets aucun texte hors JSON.
        - Ne mets pas de markdown.
        - Ne mets pas de ```json.
        """,
    # 2. Réponse directe
    """
        {
        "question": "Texte de la question",
        "correct_answer": "réponse à la question"
        }

        Règles spécifiques :
        - Réponds uniquement avec un JSON valide.
        - "question" doit être une chaîne non vide.
        - "correct_answer" doit être une chaîne non vide.
        - Ne génère pas "options".
        - Ne génère pas "answer".
        - Ne mets aucun texte hors JSON.
        - Ne mets pas de markdown.
        - Ne mets pas de ```json.
        """,
    # 3. Exercice par étapes
    """
        {
        "enonce": "Texte de l'énoncé",
        "questions": [
            "Question de l'étape 1",
            "Question de l'étape 2",
            "Question de l'étape 3"
        ],
        "correct_answers": [
            "Réponse à l'étape 1",
            "Réponse à l'étape 2",
            "Réponse à l'étape 3"
        ]
        }

        Règles spécifiques :
        - Réponds uniquement avec un JSON valide.
        - "enonce" doit être une chaîne non vide.
        - "questions" doit être une liste de chaînes non vides.
        - "correct_answers" doit être une liste de chaînes non vides.
        - "questions" et "correct_answers" doivent avoir exactement la même longueur.
        - Les étapes doivent être détaillées et suivre un ordre logique de résolution.
        - Ne génère pas "options".
        - Ne génère pas "answer".
        - Ne mets aucun texte hors JSON.
        - Ne mets pas de markdown.
        - Ne mets pas de ```json.
        """,
]


format = formats[0]

import json


def format_qcm_question(raw_data):
    """
    Formate et valide une question de QCM générée par un chatbot/API.

    Paramètres:
        raw_data (dict | str): Données brutes reçues (dict ou JSON string).

    Retour:
        dict: Question formatée avec clés 'question', 'options', 'correct_index'.

    Exceptions:
        ValueError: Si le format est invalide.
    """
    # Si les données sont en JSON string, on les convertit
    if isinstance(raw_data, str):
        try:
            raw_data = json.loads(raw_data)
        except json.JSONDecodeError:
            raise ValueError("Les données fournies ne sont pas un JSON valide.")

    if not isinstance(raw_data, dict):
        raise ValueError("Les données doivent être un dictionnaire ou un JSON valide.")

    # Extraction avec valeurs par défaut
    question = raw_data.get("question", "").strip()
    options = raw_data.get("options", [])
    correct_index = raw_data.get("answer", None)

    # Validation du champ question
    if not question:
        raise ValueError("La question ne peut pas être vide.")

    # Validation des options
    if not isinstance(options, list) or not (2 <= len(options) <= 6):
        raise ValueError("Il doit y avoir entre 2 et 6 options.")
    if not all(isinstance(opt, str) and opt.strip() for opt in options):
        raise ValueError("Toutes les options doivent être des chaînes non vides.")

    # # Validation de l'index correct
    # if not isinstance(correct_index, int):
    #     raise ValueError("L'index de la bonne réponse est invalide.")

    # Retour du format imposé
    return {"question": question, "options": options, "answer": correct_index}





def clean_json_response(text):
    text = re.sub(r"```json|```", "", text).strip()
    return json.loads(text)


def ask_question(dict_question):

    print(dict_question["question"])

    for i, choice in enumerate(dict_question["options"], 1):
        print(f"{i}. {choice}")

    answer_user = int(input("Enter your answer: ").strip())

    selected_option = dict_question["options"][answer_user - 1]

    return selected_option == dict_question["answer"]


def main():
    # génération d'un prompt
    prompt = genererate_prompt(notion, niveau, format)

    # Appel d'API pour générer l'exercice
    response = client.chat.complete(
        model=MODEL, messages=[{"role": "user", "content": prompt}]
    )

    print(response.choices[0].message.content)

    clear_response = clean_json_response(response.choices[0].message.content)
    dict_qcm = format_qcm_question(clear_response)

    score = 0

    if ask_question(dict_qcm):
        print("Correct ! \n")
        score += score
    else:
        print("Wrong answer")


main()
