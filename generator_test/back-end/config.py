from mistralai import Mistral

API_KEY = "fOTxUhR9dDPIsmNOCRIxggr0Erhew4yk"

client = Mistral(api_key=API_KEY)

MODEL = "mistral-small"


# generate a prompt
def genererate_prompt(notion, niveau, format):
    prompt = f"""
                Tu es un tuteur de mathématiques pour des étudiants de première année.

                Génère un QCM de mathématiques.

                Notion : {notion}
                Niveau : {niveau}

                Contraintes :
                - Une seule bonne réponse
                - 4 propositions
                - aucun texte en dehors du format

                Format:
                {format}

                Important :
                Réponds uniquement avec le format.
                format json
                """
    return prompt


# List of Notions
notions = ["trigonométrie", "nombres complexes", "fractions"]

# notions selected
notion = notions[0]

# niveau de l'éléve (non adaptatif)
niveau = "intermédiaire"

# format de question
formats = [
    """
            {
            "question": "Texte de la question",
            "options": ["A","B","C","D"],
            "answer": position bonne option 
            }
            Réponds uniquement avec du JSON valide.
            La bonne reponse est dans les options
            answer est lier à la position de la bonne reponse
            Ne mets PAS de ```json ni de markdown.
            """
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

    # Validation de l'index correct
    if not isinstance(correct_index, int) or not (0 <= correct_index < len(options)):
        raise ValueError("L'index de la bonne réponse est invalide.")

    # Retour du format imposé
    return {"question": question, "options": options, "answer": correct_index}


import re


def clean_json_response(text):
    text = re.sub(r"```json|```", "", text).strip()
    return json.loads(text)


def ask_question(dict_question):
    print(dict_question["question"])
    for i, choice in enumerate(dict_question["options"], 0):
        print(f"{i}. {choice}")

    answer = int(input("Enter the correct answer :").strip())
    return answer == dict_question["answer"]


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
        print(f"Wrong")


main()
