from mistralai import Mistral

API_KEY = "fOTxUhR9dDPIsmNOCRIxggr0Erhew4yk"

client = Mistral(api_key=API_KEY)

MODEL = "mistral-small"


# Fonction pour générer le prompt
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
                - Réponds uniquement avec le JSON brut.
                - N'utilise pas de bloc markdown.
                - Ne mets pas ```json.
                """
    return prompt


# Listes des notions
notions = ["trigonométrie", "nombres complexes", "fractions"]

# notion sélectionné
notion = notions[0]

# niveau de l'éléve (non adaptatif)
niveaux = ["facile", "intermédiaire", "avancé"]
niveau = niveaux[1]

# format de question
formats = [
    """
{
  "question": "Texte de la question",
  "options": ["A","B","C","D"],
  "correct_index": 1
}
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
""",
]

format = formats[2]

# génération d'un prompt
prompt = genererate_prompt(notion, niveau, format)

# Appel d'API pour générer l'exercice
response = client.chat.complete(
    model=MODEL, messages=[{"role": "user", "content": prompt}]
)

print(response.choices[0].message.content)
