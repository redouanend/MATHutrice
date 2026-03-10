from mistralai import Mistral

API_KEY = "fOTxUhR9dDPIsmNOCRIxggr0Erhew4yk"

client = Mistral(api_key=API_KEY)

MODEL = "mistral-small"


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
                Réponds uniquement avec du JSON valide.
                Ne mets PAS de ```json ni de markdown.
                """
    return prompt


notions = ["trigonométrie", "nombres complexes", "fractions"]
notion = notions[0]
niveau = "intermédiaire"
format = """
{
  "question": "Texte de la question",
  "options": ["A","B","C","D"],
  "correct_index": 1
}
Réponds uniquement avec du JSON valide.
Ne mets PAS de ```json ni de markdown.
"""

prompt = genererate_prompt(notion, niveau, format)

response = client.chat.complete(
    model=MODEL, messages=[{"role": "user", "content": prompt}]
)

print(response.choices[0].message.content)

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
    correct_index = raw_data.get("correct_index", None)

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
    return {
        "question": question,
        "options": options,
        "correct_index": correct_index
    }

import re

def clean_json_response(text):
    text = re.sub(r"```json|```", "", text).strip()
    return json.loads(text)

true_response = clean_json_response(response.choices[0].message.content)
format_qcm = format_qcm_question(true_response)