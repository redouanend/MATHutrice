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
"""

prompt = genererate_prompt(notion, niveau, format)

response = client.chat.complete(
    model=MODEL, messages=[{"role": "user", "content": prompt}]
)

print(response.choices[0].message.content)
