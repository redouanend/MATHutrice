"""
utils.py — Petites fonctions utilitaires partagées, sans dépendance métier.
"""


def clamp_score(x):
    """
    Borne une valeur de score dans l'intervalle [0, 1].

    Paramètres
    ----------
    x : float | Decimal | int
        La valeur à borner.

    Retour
    ------
    float
        ``0.0`` si ``x < 0``, ``1.0`` si ``x > 1``, sinon ``float(x)``.
    """
    return max(0.0, min(1.0, float(x)))
