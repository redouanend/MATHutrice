"""
scoring.py — Source de vérité unique pour le Level (bucket UI) et le flag
« Compétence maîtrisée » d'une Compétence.

Level et Maîtrisé se déduisent tous les deux du Score et du nombre de
tentatives (`attempts_count`) d'une Progression. Cette logique était
auparavant dupliquée (avec des seuils divergents) dans le chemin de
persistance, le seeding initial et le frontend. `compute_level_and_mastery`
est désormais le seul endroit où ces seuils sont définis.

Voir CONTEXT.md (« Level », « Compétence maîtrisée ») et
docs/adr/0001-damped-step-scoring-update.md.
"""

from fonctions_python.utils import clamp_score

# Seuils Level (bucket d'affichage, dérivé du Score seul)
LEVEL_FAIBLE_MAX = 0.4  # score < 0.4           → faible
LEVEL_MOYEN_MAX = 0.75  # 0.4 ≤ score < 0.75    → moyen
#                         score ≥ 0.75          → avance

# Seuils « Compétence maîtrisée » (Score ET track record)
MASTERY_SCORE_MIN = 0.8
MASTERY_ATTEMPTS_MIN = 3


def compute_level_and_mastery(score, attempts_count):
    """
    Calcule le Level et le flag Maîtrisé d'une Compétence.

    Paramètres
    ----------
    score : float | Decimal | int
        Le Score de la Compétence. Borné dans [0, 1] via ``clamp_score``.
    attempts_count : int
        Le nombre de fois où la Compétence a été tentée (après prise en
        compte de la réponse courante s'il y en a une).

    Retour
    ------
    (level, mastered) : tuple[str, bool]
        level    : "faible" (score < 0.4)
                 | "moyen"  (0.4 ≤ score < 0.75)
                 | "avance" (score ≥ 0.75)
        mastered : True ssi score ≥ 0.8 ET attempts_count ≥ 3
    """
    score = clamp_score(score)

    if score < LEVEL_FAIBLE_MAX:
        level = "faible"
    elif score < LEVEL_MOYEN_MAX:
        level = "moyen"
    else:
        level = "avance"

    mastered = score >= MASTERY_SCORE_MIN and attempts_count >= MASTERY_ATTEMPTS_MIN

    return level, mastered
