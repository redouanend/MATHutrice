from mistralai import Mistral
import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("MISTRAL_API_KEY", "fOTxUhR9dDPIsmNOCRIxggr0Erhew4yk")
client = Mistral(api_key=api_key)
MODEL = "mistral-small"

system_prompt = """Tu es MATHutrice, une tutrice IA specialisee en mathematiques.

REGLES DE FORMATAGE OBLIGATOIRES:
1. Separe tes paragraphes par des lignes vides
2. Pour les listes, utilise:
   - Tirets pour les listes non ordonnees
   1. Numeros pour les listes ordonnees
3. FORMULES MATHEMATIQUES - TRES IMPORTANT:
   - Inline: $x^2$ (avec un seul $)
   - Display: $$\\frac{a}{b}$$ (avec deux $$)
   - NE JAMAIS utiliser ( ) pour les maths, TOUJOURS $ ou $$
4. Utilise **gras** pour les termes importants
5. Utilise ## pour les titres de sections

Exemple de bonne reponse:
## Les equations du second degre

Une equation du second degre a la forme $ax^2 + bx + c = 0$.

**La formule quadratique:**

$$x = \\frac{-b \\pm \\sqrt{b^2 - 4ac}}{2a}$$

**Etapes de resolution:**
1. Identifier $a$, $b$ et $c$
2. Calculer le discriminant $\\Delta = b^2 - 4ac$
3. Appliquer la formule"""

messages_history = [{"role": "system", "content": system_prompt}]


def chat(user_input: str) -> str:
    """Version non-streaming du chat"""
    messages_history.append({"role": "user", "content": user_input})
    try:
        response = client.chat.complete(model=MODEL, messages=messages_history)
        reply = response.choices[0].message.content
        messages_history.append({"role": "assistant", "content": reply})
        return reply
    except Exception as e:
        messages_history.pop()
        return f"Erreur: {str(e)}"


def chat_stream(user_input: str):
    """
    Generateur SYNCHRONE avec vrai streaming Mistral.
    """
    messages_history.append({"role": "user", "content": user_input})
    full_response = ""
    
    try:
        # Vrai streaming avec Mistral
        stream = client.chat.stream(
            model=MODEL,
            messages=messages_history
        )
        
        for event in stream:
            if event.data.choices and len(event.data.choices) > 0:
                delta = event.data.choices[0].delta
                if delta.content:
                    chunk = delta.content
                    full_response += chunk
                    yield chunk
        
        messages_history.append({"role": "assistant", "content": full_response})
        
    except Exception as e:
        # Fallback: utilise la version complete
        messages_history.pop()
        try:
            response = chat(user_input)
            words = response.split(' ')
            for i, word in enumerate(words):
                if i > 0:
                    yield ' '
                yield word
        except Exception as e2:
            yield f"Erreur: {str(e2)}"


def reset_conversation():
    """Reinitialise l'historique"""
    global messages_history
    messages_history = [{"role": "system", "content": system_prompt}]
