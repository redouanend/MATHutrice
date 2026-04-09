from mistralai import Mistral
import json
import re

API_KEY = "fOTxUhR9dDPIsmNOCRIxggr0Erhew4yk"
MODEL = "mistral-small"

client = Mistral(api_key=API_KEY)


# Prompt to send to mistral
def build_prompt(notion: str, niveau: str) -> str:

    prompt = f"""
Tu es un tuteur de mathématiques pour des étudiants.

Ta tâche est de générer un exercice de mathématiques sous forme de QCM.

Informations :
- Notion : {notion}
- Niveau : {niveau}

Contraintes pédagogiques :
- L'exercice doit être adapté au niveau demandé.
- L'énoncé doit être clair et sans ambiguïté.
- Les calculs doivent être mathématiquement corrects.

Règles de sortie (très important) :
- Réponds uniquement avec un JSON valide.
- N'ajoute aucun texte avant ou après le JSON.
- N'utilise pas de markdown.

Format attendu :

{{
"question": "Texte de la question",
"options": ["rép1", "rép2", "rép3", "rép4"],
"answer": "bonne réponse exacte"
}}

Contraintes :
- exactement 4 options
- une seule bonne réponse
- la bonne réponse doit être dans options
"""

    return prompt


# Send the prompt to mistral
def call_mistral(prompt: str) -> str:

    response = client.chat.complete(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
    )

    return response.choices[0].message.content


# To get a dictionnary from what the prompt sent in JSON format
def clean_json_response(text: str) -> dict:

    text = re.sub(r"```json|```", "", text).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise ValueError("Réponse du modèle non JSON valide")


# To verify we have a statement and options wich include the answer
def validate_qcm(data: dict) -> dict:

    question = data.get("question", "").strip()
    options = data.get("options", [])
    answer = data.get("answer", "")

    if not question:
        raise ValueError("Question vide")

    if not isinstance(options, list) or len(options) != 4:
        raise ValueError("Il doit y avoir exactement 4 options")

    if answer not in options:
        raise ValueError("La bonne réponse doit être dans options")

    return {"question": question, "options": options, "answer": answer}


# To show the statement in a clear way
def build_statement(qcm: dict) -> str:

    question = qcm["question"]
    options = qcm["options"]

    statement = question + "\n\n"

    for i, opt in enumerate(options, 1):
        statement += f"{i}. {opt}\n"

    return statement


# "main" function of the file, it will be called in app.py
def generate_qcm_statement(notion: str, niveau: str) -> str:

    prompt = build_prompt(notion, niveau)

    raw_response = call_mistral(prompt)

    json_data = clean_json_response(raw_response)

    qcm = validate_qcm(json_data)

    statement = build_statement(qcm)

    return statement


# To test
if __name__ == "__main__":
    notion = "trigonométrie"
    niveau = "intermédiaire"
    print("cam")
    statement = generate_qcm_statement(notion, niveau)

    print(statement)
