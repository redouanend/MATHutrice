from mistralai.client import Mistral

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
            """,
            """
            {
            "question": "Texte de la question",
            "correct_answer": ["réponse à la question"],
            }
            """,
            """
            {
            "enoncé" : ["Texte de la question"]
            "question": ["Question de la étape 1","Question de la étape 2",...,"Question de la étape n (selon nombre d'étape extremement détaillé pour détecter ou est l'erreur pour résoudre)"],
            "correct_answer": ["Réponse à l'étape 1","Réponse à l'étape 2",...,"n"],
            }
            """
            ]


format = formats[2]

import json
def format_step_by_step_question(raw_data):
    """
    Formate et valide un exercice guidé par étapes généré par un chatbot/API.

    Paramètres:
        raw_data (dict | str): Données brutes reçues (dict ou JSON string).

    Retour:
        dict: Exercice formaté avec les clés 'type', 'statement', 'questions', 'correct_answers'.

    Exceptions:
        ValueError: Si le format est invalide.
    """
    # Si les données sont en JSON string, on les convertit
    if isinstance (raw_data,str): #est-ce que raw_data c'est une chaine de caractere?
        try: 
            raw_data=json.loads(raw_data) #si oui on le convertit en dict (json -> objet python)
        except json.JSONDecodeError : 
            raise ValueError ("Les données fournies ne sont pas un JSON valide.")
    #Vérification que le résultat final est bien un dict
    if not isinstance (raw_data, dict): #meme si raw_data n'est pas une chaine, ca peut etre un dictionnaire, car apres on va extraire de raw_data avec .get() et ca fonctionne que sur un dict
        raise ValueError ("Les données doivent être un dictionnaire ou un JSON valide.")


    #Extractions des champs IMPORTANTS
    statement = raw_data.get("enoncé", "").strip() #ca signifie qu'il va chercher la valeur associée à la clé statement et si elle existe pas ca prend une chaine vide "" à la place, puis .strip() enleve les espaces inutiles
    questions = raw_data.get("questions", []) #meme principe ici, si jamais la clé question existe pas on prend une liste vide
    correct_answers = raw_data.get("correct_answers", []) #exactement pareil la

    #Vérification que l'énoncé n'est pas vide
    if not statement: # if not -> si c'est vide, faux ou absent
        raise ValueError("L'énoncé ne peut pas être vide.")

    #Vérification liste de questions
    if not isinstance(questions, list) or len(questions) == 0: #question DOIT êtr une liste et ne doit pas être vide, si l'un OU l'autre alors erreur
        raise ValueError("Il doit y avoir au moins une question d'étape.")

    #Vérification liste des réponses
    if not isinstance(correct_answers, list) or len(correct_answers) == 0: #meme logique que pour les questions
        raise ValueError("Il doit y avoir au moins une réponse d'étape.")

    #Vérification nombre de questions ET de réponses (doit avoir le meme nombre)
    if len(questions) != len(correct_answers):
        raise ValueError("Le nombre de questons et de réponses doit être identique.")

    #Vérification que TOUTES les questions sont du texte non vide
    if not all(isinstance(q, str) and q.strip() for q in questions): #on vérif que ALL (tous) les elements verifient : d'abord que chaque question est une chaine de  caracteres, puis qu'elle n'est pas vide ou remplie d'espaces avec strip
        raise ValueError("Toutes les questions doivent être des chaînes non vides.")

    #VMême vérif pour les réponses
    if not all(isinstance(a, str) and a.strip() for a in correct_answers):
        raise ValueError("Toutes les réponses doivent être des chaînes non vides.")

    # Retour du format imposé (dict propre)
    return {"enoncé": statement,"questions": questions,"correct_answers": correct_answers}



  

abon = {
    "enoncé": "Dans un triangle rectangle ABC, rectangle en A, on sait que AB = 6 cm et AC = 8 cm. Détermine la longueur BC, puis calcule cos(B), sin(B) et tan(B).",
    "question": [
        "Calcule d’abord la longueur BC en utilisant le théorème de Pythagore.",
        "En te plaçant par rapport à l’angle B, calcule ensuite cos(B), sin(B) et tan(B)."
    ],
    "correct_answer": [
        "BC² = AB² + AC² = 6² + 8² = 36 + 64 = 100, donc BC = 10 cm.",
        "Par rapport à l’angle B : le côté adjacent est AB, le côté opposé est AC et l’hypoténuse est BC. Donc cos(B) = AB / BC = 6 / 10 = 0.6, sin(B) = AC / BC = 8 / 10 = 0.8, tan(B) = AC / AB = 8 / 6 = 1.3333333333333333."
    ]
}

def clean_json_response(text):
    text = re.sub(r"```json|```", "", text).strip()
    return json.loads(text)

print(format_step_by_step_question(abon))