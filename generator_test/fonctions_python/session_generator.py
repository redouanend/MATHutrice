"""
session_generator.py — Génère une session d'entraînement mixte (QCM / QRO / SBS)
à partir des scores réels de l'élève en base de données.

Flow :
  1. Vérifier si c'est la première fois (aucune progression en DB pour cette notion)
  2. Si première fois → positionnement : 5 QCM + 3 QRO + 2 SBS
  3. Sinon → entraînement : une question à la fois via generate_exercise_randomly
  4. Les scores sont persistés en DB après chaque réponse via /submit_answer
"""

import copy
import random
from decimal import Decimal
from datetime import datetime

from sqlmodel import Session, select

import models
import sys, os

sys.path.insert(0, os.path.dirname(__file__))
from main import (
    REFERENTIEL,
    generate_mixed_test,
    generate_exercise_randomly,
)
from fonctions_python.scoring import compute_level_and_mastery


# ─── NIVEAU AUTO ──────────────────────────────────────────────────────────────


def deduire_niveau_eleve(notion_data: dict) -> str:
    """
    Déduit le niveau de l'élève pour une notion donnée d'après les scores.

    Règle :
      - Moyenne basique < 0.7           → basique
      - Moyenne basique >= 0.7
        ET moyenne solide < 0.7         → solide
      - Moyenne basique >= 0.7
        ET moyenne solide >= 0.7        → expert
    """

    def moyenne_niveau(niveau: str) -> float:
        comps = [c for c in notion_data["competences"] if c["niveau"] == niveau]
        if not comps:
            return 1.0  # niveau inexistant → considéré acquis
        return sum(c["score"] for c in comps) / len(comps)

    if moyenne_niveau("basique") < 0.7:
        return "basique"
    if moyenne_niveau("solide") < 0.7:
        return "solide"
    return "expert"


# ─── INJECTION SCORES DB ──────────────────────────────────────────────────────


def build_notion_data_with_scores(
    notion_key: str,
    sso_id: str,
    db: Session,
) -> dict:
    """
    Reconstruit le dict notion du REFERENTIEL en remplaçant les scores statiques
    par les vrais scores de l'élève issus de la table progression.

    Si l'élève n'a pas encore de progression pour une compétence → score = 0.5
    (ni acquis, ni lacune avérée).
    """
    if notion_key not in REFERENTIEL:
        raise ValueError(f"Notion inconnue : {notion_key}")

    notion_data = copy.deepcopy(REFERENTIEL[notion_key])
    codes = [c["code"] for c in notion_data["competences"]]

    rows = db.exec(
        select(models.Progression).where(
            models.Progression.sso_id == sso_id,
            models.Progression.competence_id.in_(codes),
        )
    ).all()

    scores_db = {row.competence_id: float(row.score) for row in rows}

    for comp in notion_data["competences"]:
        comp["score"] = scores_db.get(comp["code"], 0.5)

    return notion_data


# ─── VÉRIFICATION PREMIÈRE FOIS ───────────────────────────────────────────────


def is_first_session(notion_key: str, sso_id: str, db: Session) -> bool:
    if notion_key not in REFERENTIEL:
        raise ValueError(f"Notion inconnue : {notion_key}")

    codes = [c["code"] for c in REFERENTIEL[notion_key]["competences"]]

    attempted = db.exec(
        select(models.Progression).where(
            models.Progression.sso_id == sso_id,
            models.Progression.competence_id.in_(codes),
            models.Progression.attempts_count > 0,
        )
    ).first()

    return attempted is None


# ─── INIT PROGRESSION ─────────────────────────────────────────────────────────


def init_progressions_for_user(sso_id: str, db: Session) -> None:
    """
    Initialise les entrées de progression pour toutes les compétences
    du REFERENTIEL pour un nouvel élève.
    Appelé à la première connexion.
    Score initial = 0.5 (niveau intermédiaire inconnu).
    """
    now = datetime.utcnow()
    initial_level, _ = compute_level_and_mastery(0.5, 0)

    for notion_key, notion_data in REFERENTIEL.items():
        for comp in notion_data["competences"]:
            existing = db.exec(
                select(models.Progression).where(
                    models.Progression.sso_id == sso_id,
                    models.Progression.competence_id == comp["code"],
                )
            ).first()

            if existing:
                continue

            prog = models.Progression(
                progression_id=f"{sso_id}_{comp['code']}",
                score=Decimal("0.50"),
                updated_at=now,
                level=initial_level,
                attempts_count=0,
                competence_id=comp["code"],
                sso_id=sso_id,
            )
            db.add(prog)

    db.commit()


# ─── PERSISTANCE SCORE APRÈS RÉPONSE ─────────────────────────────────────────


def persist_score_update(
    sso_id: str,
    competences_dict: dict,  # { "tr01": True, "tr04": False }
    question_type: str,  # "QCM" | "QRO" | "SBS"
    question_niveau: str,  # "basique" | "solide" | "expert"
    db: Session,
) -> dict:
    """
    Applique les règles de scoring de update_scores() et persiste
    les nouveaux scores en base de données.

    Retourne, par code de compétence, un dict
    ``{"score": float, "level": str, "mastered": bool}`` — le Level et le
    flag Maîtrisé sont calculés via ``compute_level_and_mastery`` (source de
    vérité unique) sur le Score clampé et l'``attempts_count`` mis à jour.
    """
    from fonctions_python.base_generator import update_scores

    # On construit un mini-REFERENTIEL local pour update_scores
    # (on ne veut pas modifier le REFERENTIEL global)
    local_ref = copy.deepcopy(REFERENTIEL)

    # Injecter les scores actuels de la DB dans le local_ref
    codes = list(competences_dict.keys())
    rows = db.exec(
        select(models.Progression).where(
            models.Progression.sso_id == sso_id,
            models.Progression.competence_id.in_(codes),
        )
    ).all()
    scores_db = {row.competence_id: float(row.score) for row in rows}

    for notion_data in local_ref.values():
        for comp in notion_data["competences"]:
            if comp["code"] in scores_db:
                comp["score"] = scores_db[comp["code"]]

    # Map niveau compétence → niveau question (pour update_scores)
    # update_scores attend "facile" | "intermediaire" | "difficile"
    niveau_map = {
        "basique": "facile",
        "solide": "intermediaire",
        "expert": "difficile",
    }
    q_niveau = niveau_map.get(question_niveau, "intermediaire")

    question_format = {
        "type": question_type.upper(),
        "niveau": q_niveau,
    }

    updated_ref, _, nouveaux_scores = update_scores(
        local_ref, question_format, competences_dict
    )

    # Clamp scores entre 0.0 et 1.0 et persister
    now = datetime.utcnow()

    results = {}

    for code, new_score in nouveaux_scores.items():
        clamped = max(0.0, min(1.0, new_score))

        prog = db.exec(
            select(models.Progression).where(
                models.Progression.sso_id == sso_id,
                models.Progression.competence_id == code,
            )
        ).first()

        attempts_count = (prog.attempts_count + 1) if prog else 1
        level, mastered = compute_level_and_mastery(clamped, attempts_count)

        if prog:
            prog.score = Decimal(str(round(clamped, 2)))
            prog.updated_at = now
            prog.attempts_count = attempts_count
            prog.level = level
        else:
            # Sécurité : créer si absent (ne devrait pas arriver après init)
            prog = models.Progression(
                progression_id=f"{sso_id}_{code}",
                score=Decimal(str(round(clamped, 2))),
                updated_at=now,
                level=level,
                attempts_count=attempts_count,
                competence_id=code,
                sso_id=sso_id,
            )

        db.add(prog)

        results[code] = {
            "score": clamped,
            "level": level,
            "mastered": mastered,
        }

    db.commit()

    return results


# ─── GÉNÉRATION POSITIONNEMENT ────────────────────────────────────────────────


def generate_positioning_session(notion_key: str, sso_id: str, db: Session) -> dict:
    """
    Génère le test de positionnement sur les 3 niveaux.
    Distribution : 1 basique (3 questions) + 1 solide (6 questions) + 1 expert (2 questions)
    Adapté au nombre de compétences par niveau dans le REFERENTIEL.
    """
    notion_data = build_notion_data_with_scores(notion_key, sso_id, db)
    notion_nom = notion_data["notion_nom"]

    q_basique = generate_mixed_test(
        notion=notion_key,
        niveau="basique",
        n_qcm=1,
        n_qro=1,
        n_steps=1,
        notion_data_override=notion_data,
    )
    q_solide = generate_mixed_test(
        notion=notion_key,
        niveau="solide",
        n_qcm=3,
        n_qro=2,
        n_steps=1,
        notion_data_override=notion_data,
    )
    q_expert = generate_mixed_test(
        notion=notion_key,
        niveau="expert",
        n_qcm=1,
        n_qro=1,
        n_steps=0,
        notion_data_override=notion_data,
    )

    questions = q_basique + q_solide + q_expert

    # Dédupliquer par compétence
    seen = set()
    unique_questions = []
    for q in questions:
        comp_code = (q.get("competence_cible") or {}).get("code", "")
        key = comp_code + q.get("type", "")
        if key not in seen:
            seen.add(key)
            unique_questions.append(q)
    questions = unique_questions
    random.shuffle(questions)

    return {
        "session_type": "positionnement",
        "notion_nom": notion_nom,
        "notion_key": notion_key,
        "niveau_eleve": "mixte",
        "questions": questions,
    }


# ─── GÉNÉRATION QUESTION ENTRAÎNEMENT ─────────────────────────────────────────


def generate_next_question(notion_key: str, sso_id: str, db: Session) -> dict:
    """
    Génère une seule question pour la phase d'entraînement.
    Le type (qcm/qro/sbs) est choisi aléatoirement.
    Le niveau est déduit des scores actuels de l'élève.
    """
    notion_data = build_notion_data_with_scores(notion_key, sso_id, db)
    niveau_eleve = deduire_niveau_eleve(notion_data)

    # On reconstruit un mini-REFERENTIEL avec les scores injectés
    # pour que generate_exercise_randomly les utilise
    local_ref = copy.deepcopy(REFERENTIEL)
    local_ref[notion_key] = notion_data

    questions = generate_exercise_randomly(local_ref, niveau_eleve, notion_key)

    return {
        "session_type": "entrainement",
        "notion_nom": notion_data["notion_nom"],
        "notion_key": notion_key,
        "niveau_eleve": niveau_eleve,
        "questions": questions,
    }
