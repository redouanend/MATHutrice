"""
Tests de la source de vérité unique Level / Maîtrisé
(`compute_level_and_mastery`) et de son câblage dans le chemin de
persistance et le seeding initial.
"""

from decimal import Decimal

import pytest
from sqlmodel import select

import models
from fonctions_python.scoring import compute_level_and_mastery
from fonctions_python.session_generator import (
    init_progressions_for_user,
    persist_score_update,
)
from fonctions_python.main import REFERENTIEL


# ─── Unitaire : compute_level_and_mastery ────────────────────────────────────


@pytest.mark.parametrize(
    "score, expected_level",
    [
        (0.0, "faible"),
        (0.39, "faible"),
        (0.399, "faible"),
        (0.4, "moyen"),          # borne basse incluse dans "moyen"
        (0.5, "moyen"),
        (0.749, "moyen"),
        (0.75, "avance"),        # borne haute incluse dans "avance"
        (0.9, "avance"),
        (1.0, "avance"),
    ],
)
def test_level_thresholds(score, expected_level):
    level, _ = compute_level_and_mastery(score, attempts_count=99)
    assert level == expected_level


def test_level_boundary_exactly_0_4():
    assert compute_level_and_mastery(0.4, 99)[0] == "moyen"
    # juste en dessous
    assert compute_level_and_mastery(0.3999999, 99)[0] == "faible"


def test_level_boundary_exactly_0_75():
    assert compute_level_and_mastery(0.75, 99)[0] == "avance"
    assert compute_level_and_mastery(0.7499999, 99)[0] == "moyen"


@pytest.mark.parametrize(
    "score, attempts, expected",
    [
        (0.8, 3, True),          # les deux conditions réunies
        (0.85, 5, True),
        (1.0, 3, True),
        (0.8, 2, False),         # score OK mais pas assez de tentatives
        (0.8, 0, False),
        (0.79, 100, False),      # tentatives OK mais score trop bas
        (0.799, 3, False),
        (0.3, 10, False),
    ],
)
def test_mastery_requires_score_and_attempts(score, attempts, expected):
    _, mastered = compute_level_and_mastery(score, attempts)
    assert mastered is expected


def test_accepts_decimal_score():
    level, mastered = compute_level_and_mastery(Decimal("0.80"), 3)
    assert level == "avance"
    assert mastered is True


# ─── Intégration : seeding initial ──────────────────────────────────────────


def test_init_progressions_seeds_level_via_helper(db):
    init_progressions_for_user("student-1", db)

    progs = db.exec(
        select(models.Progression).where(models.Progression.sso_id == "student-1")
    ).all()

    assert progs, "des progressions doivent être créées"
    for prog in progs:
        expected_level, _ = compute_level_and_mastery(
            float(prog.score), prog.attempts_count
        )
        assert prog.level == expected_level == "moyen"
        assert prog.attempts_count == 0


# ─── Intégration : persist_score_update ─────────────────────────────────────


def _first_competence(niveau):
    for notion_data in REFERENTIEL.values():
        for comp in notion_data["competences"]:
            if comp["niveau"] == niveau:
                return comp
    raise AssertionError(f"aucune compétence de niveau {niveau} dans le REFERENTIEL")


def test_persist_score_update_level_agrees_with_helper(db):
    init_progressions_for_user("student-2", db)
    comp = _first_competence("basique")

    result = persist_score_update(
        sso_id="student-2",
        competences_dict={comp["code"]: True},
        question_type="QCM",
        question_niveau="basique",
        db=db,
    )

    prog = db.exec(
        select(models.Progression).where(
            models.Progression.sso_id == "student-2",
            models.Progression.competence_id == comp["code"],
        )
    ).first()

    expected_level, expected_mastered = compute_level_and_mastery(
        float(prog.score), prog.attempts_count
    )
    # la ligne persistée est cohérente avec le helper
    assert prog.level == expected_level
    # le payload renvoyé (lu par le frontend) l'est aussi
    assert result[comp["code"]]["level"] == expected_level
    assert result[comp["code"]]["mastered"] is expected_mastered


def test_mastery_is_gated_by_attempts_count(db):
    """
    Score ≥ 0.8 dès la 2e tentative (0.5 + 0.2 + 0.2), mais « maîtrisée »
    ne s'allume qu'à la 3e — c'est bien attempts_count qui fait barrage.
    """
    init_progressions_for_user("student-3", db)
    comp = _first_competence("basique")
    code = comp["code"]

    def submit():
        return persist_score_update(
            sso_id="student-3",
            competences_dict={code: True},
            question_type="QCM",
            question_niveau="basique",
            db=db,
        )[code]

    r1 = submit()
    assert r1["score"] == pytest.approx(0.7)
    assert r1["mastered"] is False

    r2 = submit()
    assert r2["score"] >= 0.8          # seuil de score franchi
    assert r2["mastered"] is False     # ... mais seulement 2 tentatives

    r3 = submit()
    assert r3["score"] >= 0.8
    assert r3["mastered"] is True      # 3 tentatives + score ≥ 0.8

    prog = db.exec(
        select(models.Progression).where(
            models.Progression.sso_id == "student-3",
            models.Progression.competence_id == code,
        )
    ).first()
    assert prog.attempts_count == 3


def test_persist_score_update_flips_first_session(db):
    """attempts_count passe à > 0 → is_first_session doit devenir faux."""
    from fonctions_python.session_generator import is_first_session

    init_progressions_for_user("student-4", db)

    # trouver la notion qui contient la compétence basique choisie
    comp = _first_competence("basique")
    notion_key = next(
        k
        for k, data in REFERENTIEL.items()
        if any(c["code"] == comp["code"] for c in data["competences"])
    )

    assert is_first_session(notion_key, "student-4", db) is True

    persist_score_update(
        sso_id="student-4",
        competences_dict={comp["code"]: True},
        question_type="QCM",
        question_niveau="basique",
        db=db,
    )

    assert is_first_session(notion_key, "student-4", db) is False
