from mistralai import Mistral
import json
import re
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "generator_test", "fonctions_python"))
from main import REFERENTIEL

API_KEY = "fOTxUhR9dDPIsmNOCRIxggr0Erhew4yk"

client = Mistral(api_key=API_KEY)

MODEL = "mistral-small"


# generate a prompt
def reperage_lacune(
    notion,
    niveau,
    format,
    enonce,
    reponse_correcte,
    reponse_etudiant,
    nb_tentatives,
    dernieres_erreurs,
    competences=None,
):
    if competences:
        competences_str = "\n".join(
            f'  - [{c["code"]}] {c["nom"]} (niveau : {c["niveau"]})'
            for c in competences
        )
        competences_section = f"""
            Compétences de cette notion (utilise UNIQUEMENT ces codes) :
{competences_str}
"""
    else:
        competences_section = ""

    prompt = f"""
            Tu es un expert en diagnostic pédagogique pour des étudiants
            de première année d'université en mathématiques.

            Ta tâche est d'analyser la réponse d'un étudiant à un exercice
            et d'identifier ses lacunes avec précision.

            Informations sur l'exercice :
            - Notion ciblée : {notion}
            - Niveau de difficulté : {niveau}
            - Énoncé : {enonce}
            - Réponse correcte avec étapes : {reponse_correcte}
            - Réponse de l'étudiant : {reponse_etudiant}
{competences_section}
            Informations sur l'historique de l'étudiant :
            - Nombre de tentatives sur cette notion : {nb_tentatives}
            - Dernières erreurs connue : {dernieres_erreurs}

            Contraintes d'analyse :
            - Compare le raisonnement étape par étape, pas uniquement le résultat final.
            - Identifie exactement à quelle étape l'erreur apparaît.
            - Si l'erreur ressemble à la dernière erreur connue, marque erreur_recurrente à true.
            - Cherche toujours si l'erreur vient d'une notion prérequise non maîtrisée.
            - Rédige le feedback en "tu", de manière bienveillante, sans donner la réponse complète.
            - Si une liste de compétences est fournie, identifie dans competences_lacunaires les codes
              des compétences non maîtrisées. Utilise UNIQUEMENT les codes fournis. Si correct, renvoie [].
              Si aucune liste n'est fournie, renvoie null.

            Taxonomie des types d'erreurs utilise EXACTEMENT ces valeurs :
            - "aucune"             : réponse correcte
            - "conceptuelle"       : concept fondamental mal compris
            - "confusion_regle"    : bonne idée mais mauvaise règle appliquée
            - "prerequis_manquant" : lacune sur une notion antérieure   
            - "erreur_calcul"      : méthode correcte mais erreur numérique
            - "erreur_inversion"   : deux éléments inversés dans la procédure
            - "erreur_signe"       : erreur sur un signe
            - "incomplet"          : raisonnement arrêté trop tôt
            - "hors_sujet"         : réponse sans lien avec la question

            Taxonomie de gravité utilise EXACTEMENT ces valeurs :
            - "bloquante"  : empêche toute progression sur les notions suivantes
            - "importante" : gêne significative mais progression possible
            - "mineure"    : erreur ponctuelle, notion globalement maîtrisée

            Calibrage du score :
            - 1.0 : parfaitement correct, raisonnement complet
            - 0.8 : quasi-correct, légère imprécision ou erreur de calcul isolée
            - 0.6 : raisonnement globalement bon, erreur sur une étape
            - 0.4 : début correct, erreur majeure à mi-parcours
            - 0.2 : quelques éléments pertinents, erreur fondamentale
            - 0.0 : totalement faux ou hors sujet

            Recommandation adaptative utilise EXACTEMENT ces valeurs :
            - "notion_prerequis"   : si prerequis_suspect non null ET gravite bloquante
            - "reexpliquer"        : si type_erreur est conceptuelle ET score < 0.4
            - "exercice_similaire" : si score entre 0.3 et 0.7
            - "exercice_difficile" : si score >= 0.8 et pas parfait
            - "notion_suivante"    : si score >= 0.9

            Règles de sortie (très important) :
            - Réponds uniquement avec un JSON valide.
            - N'ajoute aucun texte avant ou après le JSON.
            - N'utilise pas de markdown.
            - N'utilise pas de balises ```json.

            Format attendu :
            {format}

            Important :
            Réponds uniquement avec le JSON correspondant au format.
            """
    return prompt


def parse_diagnostic(reponse_llm):
    texte = reponse_llm.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", texte)
    if match:
        texte = match.group(1).strip()
    match = re.search(r"\{[\s\S]*\}", texte)
    if match:
        texte = match.group(0)
    return json.loads(texte)


# Format de sortie attendu
format = """{
    "correct": true ou false,
    "diagnostic": {
        "type_erreur": "une des valeurs de la taxonomie",
        "gravite": "bloquante | importante | mineure | null",
        "etape_echec": "description de l etape où l erreur apparait ou null",
        "sous_notion_echouee": "nom précis de la sous-notion en échec ou null",
        "erreur_recurrente": true ou false,
        "lacune_precise": "description claire et précise de ce qui manque ou null",
        "prerequis_suspect": "notion prérequise probablement non maîtrisée ou null",
        "competences_lacunaires": ["code1", "code2"] ou [] si correct ou null si pas de référentiel fourni
    },
    "feedback_etudiant": "explication bienveillante en tu, 2-3 phrases, sans donner la réponse",
    "recommandation": {
        "exercice_suivant": "une des valeurs de la taxonomie",
        "notion_cible": "notion sur laquelle générer le prochain exercice",
        "niveau_cible": "debutant | intermediaire | avance",
        "consigne_generation": "instruction précise pour générer le prochain exercice"
    },
    "confiance_diagnostic": nombre entre 0.0 et 1.0
}"""


# ============================================================
# TEST 1 — Erreur de signe sur une multiplication de fractions
# Résultat attendu : erreur_signe, gravite importante, score ~0.6
# ============================================================

# notion = "Fractions"
# niveau = "debutant"
# enonce = "Calculer : (-3/4) × (-8/9)"
# reponse_correcte = "(-3) × (-8) = 24 et 4 × 9 = 36, donc 24/36 = 2/3"
# reponse_etudiant = "(-3) × 8 = -24 et 4 × 9 = 36, donc -24/36 = -2/3"
# nb_tentatives = 1
# dernieres_erreurs = "aucune"

# ============================================================
# TEST 2 — Réponse incomplète sur dérivée (règle de la chaîne)
# Résultat attendu : incomplet, gravite importante, score ~0.5
# ============================================================

notion = "Dérivée de fonctions composées"
niveau = "intermediaire"
enonce = "Dériver f(x) = sin(3x² + 1)"
reponse_correcte = (
    "Règle de la chaîne : f'(x) = cos(3x² + 1) × (3x² + 1)' = cos(3x² + 1) × 6x"
)
reponse_etudiant = "f'(x) = cos(3x² + 1)"
nb_tentatives = 2
dernieres_erreurs = "incomplet"

notion_key = "logarithme_exponentielle"
competences = REFERENTIEL[notion_key]["competences"]

prompt = reperage_lacune(
    notion,
    niveau,
    format,
    enonce,
    reponse_correcte,
    reponse_etudiant,
    nb_tentatives,
    dernieres_erreurs,
    competences=competences,
)

response = client.chat.complete(
    model=MODEL, messages=[{"role": "user", "content": prompt}]
)

# print("=" * 60)
# print("TEST 2 — Erreur de signe sur fractions")
print("=" * 60)
resultat_1 = parse_diagnostic(response.choices[0].message.content)
print(json.dumps(resultat_1, ensure_ascii=False, indent=2))
# # Appel d'API pour générer l'exercice
# response = client.chat.complete(
#     model=MODEL, messages=[{"role": "user", "content": prompt}]
# )

# print(response.choices[0].message.content)
