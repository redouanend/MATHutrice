from sqlmodel import SQLModel, Field, Relationship
from typing import Optional, List
from datetime import datetime
from decimal import Decimal





# =========================================================
# 🔗 TABLE DE LIAISON — GENERER (many-to-many)
# Un exercice peut couvrir plusieurs compétences
# =========================================================


class Generer(SQLModel, table=True):
    """
    Table de liaison entre COMPETENCE et EXERCICE.
    Un exercice peut évaluer plusieurs compétences (ex: exercice de développement
    qui touche à la fois "Cercle trigo" et "Formules sin/cos").
    """

    __tablename__ = "generer"

    competence_id: str = Field(foreign_key="competence.competence_id", primary_key=True)
    exercice_id: str = Field(foreign_key="exercice.exercice_id", primary_key=True)


# =========================================================
# 👤 USER
# Stocke tous les comptes de la plateforme (etudiant / admin)
# Pas de password_hash — authentification déléguée au SSO de l'EPF
# sso_id = identifiant unique renvoyé par le provider SSO à chaque connexion
# =========================================================


class User(SQLModel, table=True):
    """
    Compte utilisateur créé automatiquement à la première connexion SSO.
    role = "etudiant" par défaut, "admin" attribué manuellement ou via interface admin.
    last_active = nullable car un compte tout juste créé n'a pas encore de dernière activité.
    """

    __tablename__ = "user_"

    sso_id: str = Field(primary_key=True, max_length=36)
    firstname: str = Field(max_length=50)
    lastname: str = Field(max_length=50)
    created_at: datetime
    last_active: Optional[datetime] = None  # nullable — pas encore connecté
    role: str = Field(max_length=50)  # "etudiant" | "admin"
    email: str = Field(unique=True, max_length=50)

    # Relations
    conversations: List["Conversation"] = Relationship(back_populates="user")
    progressions: List["Progression"] = Relationship(back_populates="user")


# =========================================================
# 📘 NOTION
# Les chapitres du cours OMI (Trigonométrie, Fractions, Algèbre...)
# Remplie une fois par l'admin — données statiques
# =========================================================


class Notion(SQLModel, table=True):
    """
    Chapitre du cours. Pivot central du MCD.
    Une notion contient au moins une compétence (1,n).
    Une notion peut faire l'objet de plusieurs conversations.
    """

    __tablename__ = "notion"

    notion_id: str = Field(primary_key=True, max_length=36)
    title: str = Field(max_length=50)
    description: str  # TEXT — pas de limite de longueur

    # Relations
    competences: List["Competence"] = Relationship(back_populates="notion")
    conversations: List["Conversation"] = Relationship(back_populates="notion")


# =========================================================
# 🧠 COMPETENCE
# Sous-unité d'évaluation d'une notion
# C'est à ce niveau qu'on mesure les lacunes via PROGRESSION
# level = "base" | "solide" | "expert"
# =========================================================


class Competence(SQLModel, table=True):
    """
    Compétence pédagogique appartenant à une notion.
    Le level (base/solide/expert) est une propriété FIXE de la compétence —
    il ne change pas selon l'étudiant. C'est le score dans PROGRESSION qui évolue.
    Un exercice généré sur cette compétence hérite de son level.
    """

    __tablename__ = "competence"

    competence_id: str = Field(primary_key=True, max_length=50)
    title: str = Field(max_length=50)
    description: str  # TEXT
    level: str = Field(max_length=50)  # "base" | "solide" | "expert"

    # FK vers NOTION
    notion_id: str = Field(foreign_key="notion.notion_id", max_length=36)

    # Relations
    notion: Optional[Notion] = Relationship(back_populates="competences")
    progressions: List["Progression"] = Relationship(back_populates="competence")
    exercices: List["Exercice"] = Relationship(
        back_populates="competences",
        link_model=Generer,  # many-to-many via table Generer
    )


# =========================================================
# 💬 CONVERSATION
# Session de travail ouverte par un étudiant sur une notion
# context_type détermine le system prompt envoyé à Claude :
#   - "chat_libre"       → F3 : discussion libre sur la notion
#   - "analyse_exercice" → F4 : analyse de la réponse de l'étudiant
#   - "test_niveau"      → F6 : évaluation du niveau sur la notion
# title = généré automatiquement par Claude après le 1er message
# status = "active" | "archivee"
# =========================================================


class Conversation(SQLModel, table=True):
    """
    Une conversation = une session de travail sur UNE notion précise.
    On ne mélange pas les notions dans une même conversation pour garder
    le contexte Claude cohérent.
    La sidebar "derniers chats" de l'interface affiche les conversations
    triées par updated_at.
    """

    __tablename__ = "conversation"

    conversation_id: str = Field(primary_key=True, max_length=50)
    context_type: str = Field(
        max_length=50
    )  # "chat_libre" | "analyse_exercice" | "test_niveau"
    status: str = Field(max_length=50)  # "active" | "archivee"
    started_at: datetime
    updated_at: datetime
    title: str = Field(max_length=50)  # résumé auto-généré par Claude

    # FK
    notion_id: str = Field(foreign_key="notion.notion_id", max_length=36)
    sso_id: str = Field(foreign_key="user_.sso_id", max_length=36)

    # Relations
    user: Optional[User] = Relationship(back_populates="conversations")
    notion: Optional[Notion] = Relationship(back_populates="conversations")
    messages: List["Message"] = Relationship(back_populates="conversation")


# =========================================================
# ✉️ MESSAGE
# Chaque ligne du dialogue dans une conversation
# role = "user" | "assistant" — format exact attendu par l'API Claude
# pour reconstruire l'historique à chaque appel
# =========================================================


class Message(SQLModel, table=True):
    """
    Un message appartient à exactement une conversation.
    Pour appeler Claude, on reconstruit la liste des messages :
        messages = [{"role": m.role, "content": m.content} for m in conversation.messages]
    """

    __tablename__ = "message"

    message_id: str = Field(primary_key=True, max_length=50)
    role: str = Field(max_length=50)  # "user" | "assistant"
    content: str  # TEXT — pas de limite
    sent_at: datetime

    # FK
    conversation_id: str = Field(
        foreign_key="conversation.conversation_id", max_length=50
    )

    # Relations
    conversation: Optional[Conversation] = Relationship(back_populates="messages")


# =========================================================
# 📊 PROGRESSION
# Score de l'étudiant par compétence — source de vérité des lacunes
# score initialisé à 1.0 à l'inscription (pas de lacune supposée)
# mis à jour après chaque exercice selon les réponses
# score < 0.5 → lacune détectée (pas de table séparée, c'est juste un état)
# UNIQUE(competence_id, sso_id) → un seul score par étudiant par compétence
# =========================================================


class Progression(SQLModel, table=True):
    """
    Agrégat par (étudiant, compétence).
    C'est cette table qui alimente le tableau de bord :
        score = 0.3 → affiché "30%" avec indicateur rouge (lacune)
        score = 0.8 → affiché "80%" avec indicateur vert (acquis)
    level = déduit du score : "faible" | "moyen" | "avancé"
    attempts_count = incrémenté après chaque exercice tenté sur cette compétence
    """

    __tablename__ = "progression"

    progression_id: str = Field(primary_key=True, max_length=50)
    score: Decimal = Field(
        max_digits=3,
        decimal_places=2,  # NUMERIC(3,2) → 0.00 à 1.00
    )
    updated_at: datetime
    level: str = Field(max_length=50)  # "faible" | "moyen" | "avance"
    attempts_count: int  # nombre total de tentatives

    # FK
    competence_id: str = Field(foreign_key="competence.competence_id", max_length=50)
    sso_id: str = Field(foreign_key="user_.sso_id", max_length=36)

    # Relations
    competence: Optional[Competence] = Relationship(back_populates="progressions")
    user: Optional[User] = Relationship(back_populates="progressions")


# =========================================================
# 🧪 EXERCICE
# Généré par Claude et stocké pour réutilisation
# Avant de générer, FastAPI vérifie si un exercice existe déjà
# sur cette compétence que cet étudiant n'a pas encore fait
# → évite de régénérer et économise des tokens Anthropic
# hints = indices progressifs donnés à l'étudiant si besoin (F5)
# solution = stockée en interne uniquement pour que Claude vérifie
#            la réponse — jamais affichée directement à l'étudiant
# =========================================================


class Exercice(SQLModel, table=True):
    """
    Exercice généré par Claude, stocké dès sa création.
    Lié à une ou plusieurs compétences via la table Generer.
    Le level de l'exercice = le level de sa/ses compétence(s).
    """

    __tablename__ = "exercice"

    exercice_id: str = Field(primary_key=True, max_length=50)
    statement: str  # TEXT — énoncé de l'exercice
    solution: str  # TEXT — solution interne pour Claude
    generated_at: datetime
    hints: Optional[str] = None  # TEXT nullable — indices progressifs F5

    # Relations (many-to-many via Generer)
    competences: List[Competence] = Relationship(
        back_populates="exercices", link_model=Generer
    )