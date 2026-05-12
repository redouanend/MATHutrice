"""
router_generation.py — Router FastAPI pour la génération RAG
=============================================================
À ajouter dans ton app FastAPI existante :

  from router_generation import router as generation_router
  app.include_router(generation_router, prefix="/api/v1")

Le bridge RAG est chargé une seule fois au démarrage de l'app
via le lifespan ou app.on_event("startup").
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
import logging

from rag_bridge import RAGBridge, EleveContext, get_bridge

logger = logging.getLogger(__name__)
router = APIRouter(tags=["génération"])


# ── Schémas Pydantic ───────────────────────────────────

class GenerateRequest(BaseModel):
    notion       : str  = Field(..., example="fractions")
    niveau       : str  = Field("intermédiaire",
                                 example="débutant|intermédiaire|avancé")
    n            : int  = Field(3, ge=1, le=10)
    # Profil élève (optionnel — si non fourni, profil neutre)
    eleve_id     : Optional[str]  = None
    eleve_niveau : Optional[int]  = Field(None, ge=1, le=5)
    lacunes      : Optional[list] = []


class EvaluationResult(BaseModel):
    """Résultat d'une question pour la détection de lacunes."""
    chunk_id : Optional[str] = None
    notion   : Optional[str] = None
    score    : int = Field(..., ge=0, le=100)
    format   : str = "qcm"


class LacunesRequest(BaseModel):
    eleve_id  : str
    resultats : list[EvaluationResult]


# ── Helper ─────────────────────────────────────────────

def _build_eleve(req: GenerateRequest) -> EleveContext:
    niveau_map = {"débutant": 1, "intermédiaire": 3, "avancé": 5}
    return EleveContext(
        eleve_id = req.eleve_id or "anonymous",
        niveau   = req.eleve_niveau or niveau_map.get(req.niveau, 2),
        lacunes  = req.lacunes or [],
    )


# ── Endpoints ──────────────────────────────────────────

@router.post("/generate/qcm")
def generate_qcm(req: GenerateRequest,
                 bridge: RAGBridge = Depends(get_bridge)):
    """Génère des QCM ancrés dans les exercices du cours (RAG)."""
    eleve = _build_eleve(req)
    questions = bridge.generate_qcm(req.notion, req.niveau, req.n, eleve)
    if not questions:
        raise HTTPException(502, "Aucune question générée (erreur LLM)")
    return {"questions": questions, "rag_active": bridge._ready}


@router.post("/generate/qro")
def generate_qro(req: GenerateRequest,
                 bridge: RAGBridge = Depends(get_bridge)):
    """Génère des QRO ancrés dans les exercices du cours (RAG)."""
    eleve = _build_eleve(req)
    questions = bridge.generate_qro(req.notion, req.niveau, req.n, eleve)
    if not questions:
        raise HTTPException(502, "Aucune question générée")
    return {"questions": questions, "rag_active": bridge._ready}


@router.post("/generate/steps")
def generate_steps(req: GenerateRequest,
                   bridge: RAGBridge = Depends(get_bridge)):
    """Génère des exercices étape par étape (RAG)."""
    eleve = _build_eleve(req)
    questions = bridge.generate_steps(req.notion, req.niveau, req.n, eleve)
    if not questions:
        raise HTTPException(502, "Aucun exercice généré")
    return {"questions": questions, "rag_active": bridge._ready}


@router.post("/generate/trous")
def generate_trous(req: GenerateRequest,
                   bridge: RAGBridge = Depends(get_bridge)):
    """Génère des exercices à trous (RAG)."""
    eleve = _build_eleve(req)
    questions = bridge.generate_trous(req.notion, req.niveau, req.n, eleve)
    if not questions:
        raise HTTPException(502, "Aucun exercice généré")
    return {"questions": questions, "rag_active": bridge._ready}


@router.post("/generate/mixed")
def generate_mixed(req: GenerateRequest,
                   bridge: RAGBridge = Depends(get_bridge)):
    """
    Génère un test mixte (QCM + QRO + Steps).
    n est distribué uniformément entre les 3 formats.
    """
    eleve  = _build_eleve(req)
    n_each = max(1, req.n // 3)
    test   = []

    for fmt, gen_fn in [
        ("qcm",   bridge.generate_qcm),
        ("qro",   bridge.generate_qro),
        ("steps", bridge.generate_steps),
    ]:
        qs = gen_fn(req.notion, req.niveau, n_each, eleve)
        for q in qs:
            q["type"] = fmt
        test.extend(qs)

    return {"questions": test, "total": len(test), "rag_active": bridge._ready}


@router.post("/lacunes/detect")
def detect_lacunes(req: LacunesRequest,
                   bridge: RAGBridge = Depends(get_bridge)):
    """
    Analyse les résultats d'un test et identifie les lacunes de l'élève.
    Les lacunes sont ensuite sauvegardées en PostgreSQL (à faire côté app).
    """
    resultats = [r.model_dump() for r in req.resultats]
    lacunes   = bridge.detect_lacunes(resultats)
    return {
        "eleve_id"  : req.eleve_id,
        "lacunes"   : lacunes,
        "nb_lacunes": len(lacunes),
    }


@router.get("/rag/stats")
def rag_stats(bridge: RAGBridge = Depends(get_bridge)):
    """Stats du vectorstore (pour le dashboard admin)."""
    return bridge.stats()


# ── Intégration dans l'app principale ─────────────────
"""
Dans ton main FastAPI (app.py ou main_api.py) :

  from fastapi import FastAPI
  from contextlib import asynccontextmanager
  from rag_bridge import get_bridge
  from router_generation import router as gen_router

  @asynccontextmanager
  async def lifespan(app: FastAPI):
      # Précharge le RAG au démarrage (une seule fois)
      get_bridge()
      yield

  app = FastAPI(lifespan=lifespan)
  app.include_router(gen_router, prefix="/api/v1")
"""
