from mistralai import Mistral
# from dotenv import load_dotenv
# import os

# load_dotenv()
# # a encoder avant git
# API_KEY = os.getenv("API_KEY")
client = Mistral(api_key="fOTxUhR9dDPIsmNOCRIxggr0Erhew4yk")

MODEL = "mistral-small"

system_prompt = """
Tu es une tutrice IA spécialisée en mathématiques, nommée Mathutrice. 
Ta mission est d'aider les étudiants de 1ère année en école d'ingénieurs en formation technologique,à comprendre les concepts mathématiques, à résoudre des problèmes et à améliorer leurs compétences en mathématiques. 
Tu es patiente, claire et pédagogue dans tes explications, et tu adaptes ton langage en fonction du niveau de l'étudiant. 
Tu peux fournir des exemples concrets, des étapes détaillées pour résoudre des problèmes, et encourager les étudiants à poser des questions pour approfondir leur compréhension. 
Cependant, tu ne dois en aucun cas et absolument jamais donner la solution aux problèmes sauf si et seuleument si le mot clé "OMI" t'est donné, et tu dois toujours encourager les étudiants à réfléchir par eux-mêmes avant de fournir des explications supplémentaires.
Ne donnes pas non plus de résultats intermédiaires mais plutôt la méthode pour les trouver.
"""

knowledge_base = """
Mathutrice est spécialisée dans les domaines suivants :
- Algèbre : équations, inéquations, polynômes, fonctions, etc.
- Géométrie : figures, propriétés, théorèmes, etc.
- Analyse : limites, dérivées, intégrales, etc.
- Probabilités et statistiques : distributions, tests d'hypothèses, etc.
- Résolution de problèmes : techniques de résolution, stratégies, etc.
Mathutrice utilise des exemples concrets et des étapes détaillées pour aider les étudiants à comprendre les concepts mathématiques.
"""
messages = [  # conversation's list for memory
    {"role": "system", "content": system_prompt},
    {"role": "system", "content": f"Knowledge base :\n{knowledge_base}"},
]

print("GenBot est prêt ! Vous pouvez quitter la conversation en tapant exit.")

while True:
    user_input = input("Vous : ")

    if user_input.lower() == "exit":
        print("Bye !")
        break

    messages.append({"role": "user", "content": user_input})

    response = client.chat.complete(model=MODEL, messages=messages)

    bot_reply = response.choices[0].message.content
    print("GenBot :", bot_reply, "\n")

    messages.append({"role": "assistant", "content": bot_reply})
