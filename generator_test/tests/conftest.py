"""
Fixtures partagées pour la suite de tests.

Seam (cf. issue #11) : appels directs de fonctions contre une vraie `Session`
SQLModel adossée à un moteur SQLite en mémoire — les mêmes objets que les
routes FastAPI passent aujourd'hui. Pas de mock : rien dans le scoring
n'appelle Mistral.
"""

import os
import sys

GEN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for path in (GEN_ROOT, os.path.join(GEN_ROOT, "fonctions_python")):
    if path not in sys.path:
        sys.path.insert(0, path)

import pytest
from sqlmodel import SQLModel, Session, create_engine
from sqlalchemy.pool import StaticPool

import models  # noqa: F401  — enregistre les tables sur SQLModel.metadata


@pytest.fixture
def db():
    """Une Session liée à un moteur SQLite en mémoire, schéma créé."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
