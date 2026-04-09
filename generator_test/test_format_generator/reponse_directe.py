import json
import re
from mistralai import Mistral

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
                - N'utilise pas de balises 
json.

                Format attendu :
                {format}

                Important :
                Réponds uniquement avec le JSON correspondant au format.
                """
    return prompt

print("hello")
# List of Notions
notions = ["trigonométrie", "nombres complexes", "fractions"]

# notions selected
notion = notions[1]

# niveau de l'éléve (non adaptatif)
niveau = "intermédiaire"

# format de question
formats = [
    # 1. QCM
    """
        {
        "question": "Texte de la question",
        "options": ["rép1", "rép2", "rép3", "rép4"],
        "answer": "bonne reponse exacte"
        }

        Règles spécifiques :
        - Réponds uniquement avec un JSON valide.
        - "options" doit contenir exactement 4 propositions.
        - "answer" est l'index de la bonne réponse dans "options".
        - "answer" doit être un entier entre 0 et 3.
        - Une seule réponse est correcte.
        - La bonne réponse doit être présente dans "options".
        - Ne mets aucun texte hors JSON.
        - Ne mets pas de markdown.
        - Ne mets pas de
json.
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
        - "correct_answer" doit être strictement et uniquement une valeur.
        - Ne génère pas "options".
        - Ne génère pas "answer".
        - Ne mets aucun texte hors JSON.
        - Ne mets pas de markdown.
        - Ne mets pas de 
json.
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
        - Ne mets pas de
json.
        """,
]

format = formats[1]


def clean_json_response(text):
    text = re.sub(r"```json|```", "", text).strip()
    return json.loads(text)


def ask_question(dict_question):

    print("\n" + dict_question["question"])

    user_answer = input("Your answer: ").strip()

    correct = dict_question["correct_answer"]
    print(correct)
    return user_answer == correct


def main():

    
    prompt = genererate_prompt(notion, niveau, format)

   
    response = client.chat.complete(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}]
        
    )

    llm_text = response.choices[0].message.content

    print("\nLLM response:\n")
    print(llm_text)

    #converts json to dict
    dict_question = clean_json_response(llm_text)

    
    if ask_question(dict_question):
        print("\nCorrect!")
    else:
        print(f"\nWrong. Correct answer was: {dict_question['correct_answer']}")

main()