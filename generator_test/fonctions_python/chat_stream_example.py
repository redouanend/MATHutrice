"""
EXEMPLE - Ajoute cette fonction chat_stream() a ton fichier chatbot.py

Cette fonction utilise Mistral AI en mode streaming pour renvoyer
la reponse mot par mot (effet de frappe comme ChatGPT).
"""

from mistralai import Mistral
import asyncio

# Ta cle API Mistral (utilise la meme que dans ton chatbot.py)
api_key = "ta_cle_api"
client = Mistral(api_key=api_key)

# System prompt pour les maths avec LaTeX
SYSTEM_PROMPT = """Tu es MATHutrice, un tuteur IA specialise en mathematiques.
Tu reponds en francais de maniere claire et pedagogique.
Pour les formules mathematiques, utilise la notation LaTeX :
- Formules inline : $formule$
- Formules en bloc : $$formule$$
Exemples : $x^2 + y^2 = z^2$, $$\\frac{a}{b}$$, $\\sqrt{x}$
"""


async def chat_stream(user_message: str):
    """
    Generateur asynchrone qui yield la reponse mot par mot.
    Utilise Mistral AI en mode streaming.
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message}
    ]

    # Utilise stream=True pour le streaming
    response = client.chat.stream(
        model="mistral-small-latest",
        messages=messages
    )

    for chunk in response:
        if chunk.data.choices[0].delta.content:
            content = chunk.data.choices[0].delta.content
            yield content
            # Petit delai pour un effet de frappe plus naturel
            await asyncio.sleep(0.01)


# ─────────────────────────────────────────────────────────────────────────────
# COPIE cette fonction dans ton chatbot.py existant et adapte-la
# avec ta configuration (api_key, model, system prompt, etc.)
# ─────────────────────────────────────────────────────────────────────────────
