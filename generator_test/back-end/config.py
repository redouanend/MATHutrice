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
                """
    return prompt


# Listes des notions
notions = ["trigonométrie", "nombres complexes", "fractions"]

# notion sélectionné
notion = notions[0]

# niveau de l'éléve (non adaptatif)
niveau = "intermédiaire"

# format de question
format = """
{
  "question": "Texte de la question",
  "options": ["A","B","C","D"],
  "correct_index": 1
}
"""

# génération d'un prompt
prompt = genererate_prompt(notion, niveau, format)

# Appel d'API pour générer l'exercice
response = client.chat.complete(
    model=MODEL, messages=[{"role": "user", "content": prompt}]
)

print(response.choices[0].message.content)
