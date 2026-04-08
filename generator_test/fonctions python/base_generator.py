"""
base_generator.py — Logique commune à tous les formats de questions

Contient :
  - Configuration Mistral (client, modèle, retries)
  - clean_json()       : nettoyage de la réponse brute
  - parse_json()       : parsing JSON avec message d'erreur clair
  - call_mistral()     : appel API avec retry automatique
  - run_test()         : boucle de test console + score final (générique)
  - display_score()    : affichage du score final

Chaque fichier de format (qcm, qro, trous) importe ce module
et n'ajoute que ce qui lui est spécifique :
  - build_prompt()
  - parse_and_validate()
  - generate_question()
  - ask_question()
"""

import os
import re
import json
import logging
from mistralai import Mistral

# ─── CONFIG ───────────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

API_KEY = os.getenv("MISTRAL_API_KEY", "fOTxUhR9dDPIsmNOCRIxggr0Erhew4yk")
MODEL = "mistral-small"
MAX_RETRIES = 3

client = Mistral(api_key=API_KEY)


# ─── UTILITAIRES JSON ─────────────────────────────────────────────────────────


def clean_json(raw: str) -> str:
    """
    Nettoie la réponse brute de Mistral.
    Supprime les balises markdown ```json / ``` que Mistral ajoute parfois
    malgré les instructions explicites dans le prompt.
    """
    return re.sub(r"```json|```", "", raw).strip()


def parse_json(raw: str) -> dict:
    """
    Nettoie puis parse la réponse brute en dict Python.
    Lève ValueError avec un message clair si le JSON est invalide.
    """
    cleaned = clean_json(raw)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON invalide : {e} | Reçu : {cleaned[:200]}")

    if not isinstance(data, dict):
        raise ValueError("La réponse n'est pas un objet JSON.")

    return data


# ─── APPEL MISTRAL AVEC RETRY ─────────────────────────────────────────────────


def call_mistral(
    prompt: str, notion: str, parse_and_validate, post_process=None
) -> dict | None:
    """
    Appelle Mistral avec retry automatique (MAX_RETRIES tentatives).

    Paramètres :
      prompt           : le prompt complet à envoyer
      notion           : nom de la notion (pour les logs)
      parse_and_validate : fonction spécifique au format qui valide le dict
      post_process     : fonction optionnelle appliquée après validation
                         (ex: apply_verification pour QCM)

    Retourne le dict validé (et post-traité si besoin), ou None si échec.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.chat.complete(
                model=MODEL, messages=[{"role": "user", "content": prompt}]
            )
            raw = response.choices[0].message.content
            question = parse_and_validate(raw)

            if post_process:
                question = post_process(question)

            logger.info(f"Question prête (tentative {attempt}/{MAX_RETRIES})")
            return question

        except ValueError as e:
            logger.warning(f"Tentative {attempt}/{MAX_RETRIES} échouée — {e}")
            if attempt == MAX_RETRIES:
                logger.error(
                    f"Abandon après {MAX_RETRIES} tentatives pour notion='{notion}'"
                )
                return None


# ─── GÉNÉRATION D'UN TEST (générique) ─────────────────────────────────────────


def generate_test(
    notion: str, niveau: str, n: int, fonction_generer_format_voulu
) -> list[dict]:
    """
    Génère un test de n questions en appelant fonction_generer_format_voulu à chaque itération.
    Les questions qui échouent après MAX_RETRIES sont ignorées (pas de plantage).

    Paramètres :
      fonction_generer_format_voulu : fonction (notion, niveau) -> dict | None
                                      fournie par chaque fichier de format
    """
    questions = []
    logger.info(f"Génération de {n} questions | notion='{notion}' | niveau='{niveau}'")

    for i in range(n):
        logger.info(f"Question {i + 1}/{n}...")
        question = fonction_generer_format_voulu(notion, niveau)
        if question:
            questions.append(question)
        else:
            logger.warning(
                f"Question {i + 1} ignorée (échec après {MAX_RETRIES} tentatives)."
            )

    logger.info(f"{len(questions)}/{n} questions générées avec succès.")
    return questions


def generate_test(
    notion: str,
    niveau: str,
    nb_par_format: list[int],
    fonctions_generatrices: list,
) -> list[dict]:
    """
    Génère un test avec plusieurs formats de questions.

    Paramètres :
      nb_par_format : liste d'entiers, ex. [2, 3, 1]
      fonctions_generatrices : liste de fonctions de même taille
    """


# SCORE FINAL (générique)


def display_score(score: int, total: int, format_label: str) -> None:
    """Affiche le score final dans le terminal."""
    print(f"\n{'═' * 50}")
    print(f"  RÉSULTAT FINAL — {format_label}")
    print(f"  {score}/{total} correctes")

    if total == 0:
        print("  Aucune question n'a pu être générée.")
        print(f"{'═' * 50}\n")
        return

    percentage = round(score / total * 100)
    print(f"  Score : {percentage}%  ", end="")

    if percentage == 100:
        print("🏆 Parfait !")
    elif percentage >= 70:
        print("👍 Bien joué !")
    elif percentage >= 50:
        print("📚 Continue tes révisions.")
    else:
        print("💪 Il faut retravailler cette notion.")

    print(f"{'═' * 50}\n")


# ─── HEADER DE TEST (générique) ───────────────────────────────────────────────

# def print_test_header(total: int, format_label: str) -> None:
#     """Affiche l'en-tête du test dans le terminal."""
#     print(f"\n{'═' * 50}")
#     print(f"  TEST {format_label} — {total} question(s)")
#     print(f"{'═' * 50}")


# def print_question_header(index: int, total: int, extra: str = "") -> None:
#     """Affiche l'en-tête d'une question individuelle."""
#     print(f"\n{'─' * 50}")
#     label = f"  Question {index}/{total}"
#     if extra:
#         label += f"  [{extra}]"
#     print(label)
#     print(f"{'─' * 50}")
