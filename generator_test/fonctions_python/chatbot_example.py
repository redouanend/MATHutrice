"""
Exemple de chatbot.py avec streaming fonctionnel pour Mistral AI
"""

from mistralai import Mistral
import os

api_key = os.environ.get("MISTRAL_API_KEY", "YOUR_API_KEY")
client = Mistral(api_key=api_key)

# Instruction systeme pour des reponses bien formatees
instruction = """Tu es MATHutrice, un tuteur de mathematiques patient et pedagogique.

REGLES DE FORMATAGE IMPORTANTES:
1. Utilise des paragraphes courts separes par des lignes vides
2. Pour les listes, utilise des tirets (-) ou des numeros (1. 2. 3.)
3. Pour les formules mathematiques, utilise la notation LaTeX:
   - Inline: $x^2 + y^2 = z^2$
   - Display: $$\\frac{-b \\pm \\sqrt{b^2-4ac}}{2a}$$
4. Utilise **gras** pour les termes importants
5. Structure tes reponses avec des titres si necessaire: ## Titre

EXEMPLE DE BONNE REPONSE:
---
Super question ! Voici comment resoudre une equation du second degre.

## Methode

Pour resoudre $ax^2 + bx + c = 0$, on utilise le **discriminant**:

$$\\Delta = b^2 - 4ac$$

Ensuite:

1. Si $\\Delta > 0$: deux solutions reelles
2. Si $\\Delta = 0$: une solution double
3. Si $\\Delta < 0$: pas de solution reelle

## Exemple

Resolvons $x^2 - 5x + 6 = 0$:

- $a = 1$, $b = -5$, $c = 6$
- $\\Delta = 25 - 24 = 1 > 0$
- Solutions: $x_1 = 2$ et $x_2 = 3$
---

Reponds toujours de maniere structuree et claire."""


def chat(user_prompt: str) -> str:
    """
    Fonction synchrone pour obtenir une reponse complete
    """
    response = client.chat.complete(
        model="mistral-large-latest",
        messages=[
            {"role": "system", "content": instruction},
            {"role": "user", "content": user_prompt}
        ]
    )
    return response.choices[0].message.content


async def chat_stream(user_prompt: str):
    """
    Generateur asynchrone pour le streaming de la reponse.
    Utilise client.chat.stream() pour obtenir la reponse mot par mot.
    
    IMPORTANT: Cette fonction yield chaque chunk de texte separement
    pour un vrai effet de streaming.
    """
    # Utiliser la methode stream de Mistral
    response = client.chat.stream(
        model="mistral-large-latest",
        messages=[
            {"role": "system", "content": instruction},
            {"role": "user", "content": user_prompt}
        ]
    )
    
    # Iterer sur les chunks
    for chunk in response:
        # Extraire le contenu du chunk
        if chunk.data.choices and chunk.data.choices[0].delta.content:
            content = chunk.data.choices[0].delta.content
            yield content


# Version alternative si la premiere ne marche pas
async def chat_stream_v2(user_prompt: str):
    """
    Version alternative utilisant stream_async si disponible
    """
    try:
        # Essayer avec stream_async
        async for chunk in client.chat.stream_async(
            model="mistral-large-latest",
            messages=[
                {"role": "system", "content": instruction},
                {"role": "user", "content": user_prompt}
            ]
        ):
            if chunk.data.choices and chunk.data.choices[0].delta.content:
                yield chunk.data.choices[0].delta.content
    except AttributeError:
        # Fallback sur la version synchrone enveloppee
        response = client.chat.stream(
            model="mistral-large-latest",
            messages=[
                {"role": "system", "content": instruction},
                {"role": "user", "content": user_prompt}
            ]
        )
        for chunk in response:
            if chunk.data.choices and chunk.data.choices[0].delta.content:
                yield chunk.data.choices[0].delta.content
