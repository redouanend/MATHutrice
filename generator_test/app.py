from fastapi import FastAPI, Request, Depends, UploadFile, File
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    StreamingResponse,
    RedirectResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel
from typing import List as TList, Optional
from urllib.parse import unquote

from contextlib import asynccontextmanager
from sqlmodel import SQLModel, select, delete

from dotenv import load_dotenv

from database import engine, get_session, Session
from fonctions_python.chatbot import (
    chat,
    chat_stream,
    chat_stream_with_history,
    reset_conversation,
)

from apscheduler.schedulers.background import BackgroundScheduler

import models
import msal
import uvicorn
import shutil
import os
import uuid
import json

from datetime import datetime, timedelta

load_dotenv()


# ------------------------------------------------------------------
# Database
# ------------------------------------------------------------------


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


# ------------------------------------------------------------------
# Cleanup — supprime conversations + messages de plus de 24h
# ------------------------------------------------------------------


def cleanup_old_conversations():
    from database import Session as DBSession

    with DBSession(engine) as session:
        cutoff = datetime.utcnow() - timedelta(hours=24)

        old_conv_ids = session.exec(
            select(models.Conversation.conversation_id).where(
                models.Conversation.started_at < cutoff
            )
        ).all()

        for conv_id in old_conv_ids:
            session.exec(
                delete(models.Message).where(models.Message.conversation_id == conv_id)
            )
            session.exec(
                delete(models.Conversation).where(
                    models.Conversation.conversation_id == conv_id
                )
            )

        session.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()

    # Lance le scheduler de nettoyage toutes les heures
    scheduler = BackgroundScheduler()
    scheduler.add_job(cleanup_old_conversations, "interval", hours=1)
    scheduler.start()

    yield

    scheduler.shutdown()


# ------------------------------------------------------------------
# FastAPI app
# ------------------------------------------------------------------

app = FastAPI(lifespan=lifespan)

# Allow frontend requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Session middleware using signed cookies
# Stores authenticated user information securely
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET"),
    https_only=True,
    same_site="lax",
)

# ------------------------------------------------------------------
# Paths
# ------------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app.mount(
    "/static",
    StaticFiles(directory=os.path.join(BASE_DIR, "static")),
    name="static",
)

templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

UPLOAD_DIR = os.path.join(BASE_DIR, "rag_documents")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ------------------------------------------------------------------
# Azure AD configuration
# ------------------------------------------------------------------

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
TENANT_ID = os.getenv("TENANT_ID")

if not CLIENT_ID:
    raise ValueError("CLIENT_ID missing")

if not CLIENT_SECRET:
    raise ValueError("CLIENT_SECRET missing")

if not TENANT_ID:
    raise ValueError("TENANT_ID missing")

REDIRECT_URL = "https://mathutrice-preprod.mde.epf.fr/auth"

SCOPE = ["User.Read"]

AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"


# ------------------------------------------------------------------
# MSAL helper
# ------------------------------------------------------------------


def get_msal_app():
    """
    Creates MSAL confidential client used for OAuth authentication.
    """

    return msal.ConfidentialClientApplication(
        CLIENT_ID,
        authority=AUTHORITY,
        client_credential=CLIENT_SECRET,
    )


# ------------------------------------------------------------------
# Session helper
# ------------------------------------------------------------------


def get_current_user(request: Request):
    """
    Returns current authenticated user from session.
    """

    return request.session.get("user")


# ------------------------------------------------------------------
# LOGIN
# Redirects user to Microsoft login page
# ------------------------------------------------------------------


@app.get("/test_login")
async def login(request: Request):

    msal_app = get_msal_app()

    # Generate unique OAuth state
    # Used to protect against CSRF attacks
    state = str(uuid.uuid4())

    request.session["oauth_state"] = state

    auth_url = msal_app.get_authorization_request_url(
        scopes=SCOPE,
        redirect_uri=REDIRECT_URL,
        state=state,
    )

    return RedirectResponse(auth_url)


# ------------------------------------------------------------------
# AUTH CALLBACK
# Handles Microsoft OAuth response
# ------------------------------------------------------------------


@app.get("/auth")
async def auth_callback(
    request: Request,
    code: str = None,
    state: str = None,
    error: str = None,
    session: Session = Depends(get_session),
):

    # Handle Azure authentication errors
    if error:
        return HTMLResponse(
            f"<h2>❌ Erreur Azure</h2><pre>{error}</pre>",
            status_code=400,
        )

    # Verify OAuth state
    # Prevents CSRF attacks
    # desactivé en préprod — marche sur un seul nom de domaine
    # saved_state = request.session.get("oauth_state")
    # if not state or state != saved_state:
    #     return HTMLResponse("<h2>❌ Invalid OAuth state</h2>", status_code=400)

    msal_app = get_msal_app()

    # Exchange authorization code for token
    result = msal_app.acquire_token_by_authorization_code(
        code,
        scopes=SCOPE,
        redirect_uri=REDIRECT_URL,
    )

    # Handle token errors
    if "error" in result:
        return HTMLResponse(
            f"""
            <h2>❌ Erreur token</h2>
            <pre>{json.dumps(result, indent=2)}</pre>
            """,
            status_code=400,
        )

    # Extract user claims
    claims = result.get("id_token_claims", {})

    email = claims.get("email") or claims.get("preferred_username")

    # Restrict access to EPF domains only
    if not email or not email.endswith(("@epfedu.fr", "@epf.fr")):
        return HTMLResponse(
            """
            <h2>⛔ Accès refusé</h2>
            <p>Adresse EPF obligatoire.</p>
            """,
            status_code=403,
        )

    name = claims.get("name", "Unknown User")

    now = datetime.utcnow()

    # Search user in database
    existing_user = session.exec(
        select(models.User).where(models.User.email == email)
    ).first()

    # Existing user
    if existing_user:
        existing_user.last_active = now

        session.add(existing_user)
        session.commit()

        role = existing_user.role

    # First login → create default student
    else:
        new_user = models.User(
            sso_id=str(uuid.uuid4()),
            name=name,
            email=email,
            role="Student",
            created_at=now,
            last_active=now,
        )

        session.add(new_user)
        session.commit()

        role = "Student"

    # Store authenticated user in session
    request.session["user"] = {
        "email": email,
        "name": name,
        "role": role,
        "impersonate": False,
    }

    # Redirect depending on role
    if role in ("Teacher", "Admin"):
        return RedirectResponse("/teacher", status_code=302)

    return RedirectResponse("/", status_code=302)


# ------------------------------------------------------------------
# LOGOUT
# Clears local session and Microsoft session
# ------------------------------------------------------------------


@app.get("/logout")
async def logout(request: Request):

    request.session.clear()

    logout_url = (
        f"https://login.microsoftonline.com/"
        f"{TENANT_ID}/oauth2/v2.0/logout"
        f"?post_logout_redirect_uri="
        f"https://mathutrice-preprod.mde.epf.fr/test_login"
    )

    return RedirectResponse(logout_url)


# ------------------------------------------------------------------
# STOP IMPERSONATE
# Restores original admin session
# ------------------------------------------------------------------


@app.get("/impersonate/stop")
async def stop_impersonate(request: Request):

    current_user = get_current_user(request)

    if not current_user:
        return RedirectResponse("/test_login")

    if not current_user.get("impersonate"):
        return RedirectResponse("/")

    admin_email = current_user.get("real_admin")

    request.session["user"] = {
        "email": admin_email,
        "name": admin_email,
        "role": "Admin",
        "impersonate": False,
    }

    return RedirectResponse("/teacher")


# ------------------------------------------------------------------
# IMPERSONATE
# Allows admin to simulate another user
# DEV / ADMIN ONLY
# ------------------------------------------------------------------


@app.get("/impersonate/{email}")
async def impersonate(
    request: Request,
    email: str,
    session: Session = Depends(get_session),
):

    current_user = get_current_user(request)

    # Only admins can impersonate
    if not current_user or current_user.get("role") != "Admin":
        return HTMLResponse(
            "<h2>⛔ Accès refusé</h2>",
            status_code=403,
        )

    email = unquote(email)

    target = session.exec(select(models.User).where(models.User.email == email)).first()

    # Default role if user does not exist
    target_role = target.role if target else "Student"

    request.session["user"] = {
        "email": email,
        "name": target.name if target else email,
        "role": target_role,
        "impersonate": True,
        "real_admin": current_user["email"],
    }

    if target_role in ("Teacher", "Admin"):
        return RedirectResponse("/teacher", status_code=302)

    return RedirectResponse("/", status_code=302)


# ------------------------------------------------------------------
# TEACHER PAGE
# Teacher/Admin only
# ------------------------------------------------------------------


@app.get("/teacher", response_class=HTMLResponse)
async def teacher_page(request: Request):

    user = get_current_user(request)

    if not user:
        return RedirectResponse("/test_login")

    if user.get("role") not in ("Teacher", "Admin"):
        return RedirectResponse("/")

    return templates.TemplateResponse(
        "upload.html",
        {"request": request},
    )


# ------------------------------------------------------------------
# PDF Upload
# Teacher/Admin only
# ------------------------------------------------------------------


@app.post("/upload/pdf")
async def upload_pdf(
    request: Request,
    files: TList[UploadFile] = File(...),
):

    user = get_current_user(request)

    if not user:
        return JSONResponse(
            status_code=401,
            content={"detail": "Non connecté"},
        )

    if user.get("role") not in ("Teacher", "Admin"):
        return JSONResponse(
            status_code=403,
            content={"detail": "Accès refusé"},
        )

    email_prefix = user["email"].replace("@", "_at_")

    saved = []

    for file in files:
        if file.content_type != "application/pdf":
            continue

        filename = f"{email_prefix}__{file.filename}"

        dest = os.path.join(UPLOAD_DIR, filename)

        with open(dest, "wb") as f:
            shutil.copyfileobj(file.file, f)

        saved.append(file.filename)

    return {
        "ok": True,
        "message": f"{len(saved)} fichier(s) uploadé(s).",
        "files": saved,
    }


# ------------------------------------------------------------------
# PDF List
# Admin sees all files
# Teacher sees only own files
# ------------------------------------------------------------------


@app.get("/upload/list")
async def list_pdfs(request: Request):

    user = get_current_user(request)

    if not user:
        return JSONResponse(
            status_code=401,
            content={"detail": "Non connecté"},
        )

    if user.get("role") not in ("Teacher", "Admin"):
        return JSONResponse(
            status_code=403,
            content={"detail": "Accès refusé"},
        )

    email_prefix = user["email"].replace("@", "_at_")

    files = []

    for filename in os.listdir(UPLOAD_DIR):
        if not filename.endswith(".pdf"):
            continue

        # Teachers only see their own files
        if user.get("role") == "Teacher" and not filename.startswith(email_prefix):
            continue

        path = os.path.join(UPLOAD_DIR, filename)

        stat = os.stat(path)

        parts = filename.split("__", 1)

        display_name = parts[1] if len(parts) == 2 else filename

        uploader = parts[0].replace("_at_", "@") if len(parts) == 2 else "unknown"

        files.append(
            {
                "name": display_name,
                "uploader": uploader,
                "size": f"{stat.st_size / (1024 * 1024):.1f} MB",
                "date": datetime.fromtimestamp(stat.st_mtime).strftime(
                    "%d/%m/%Y %H:%M"
                ),
            }
        )

    files.sort(
        key=lambda x: x["date"],
        reverse=True,
    )

    return {
        "ok": True,
        "files": files,
    }


# ------------------------------------------------------------------
# HOME
# Student/Admin access
# ------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def home_page(
    request: Request,
    session: Session = Depends(get_session),
):

    user = get_current_user(request)

    if not user:
        return RedirectResponse("/test_login")

    # Teacher cannot access student pages
    if user.get("role") == "Teacher":
        return RedirectResponse("/teacher")

    notions = session.exec(select(models.Notion.notion_id, models.Notion.title)).all()

    return templates.TemplateResponse(
        "home.html",
        {
            "request": request,
            "notions": notions,
            "name": user.get("name").split(" ")[0],
        },
    )


# ------------------------------------------------------------------
# MODULE PAGE
# Student/Admin access
# ------------------------------------------------------------------


@app.get("/module", response_class=HTMLResponse)
async def module_page(
    request: Request,
    id: str,
    session: Session = Depends(get_session),
):

    user = get_current_user(request)

    if not user:
        return RedirectResponse("/test_login")

    if user.get("role") == "Teacher":
        return RedirectResponse("/teacher")

    notion = session.exec(
        select(
            models.Notion.notion_id,  # <-- Add this line
            models.Notion.title,
            models.Notion.description,
        ).where(models.Notion.notion_id == id)
    ).first()

    return templates.TemplateResponse(
        "module.html",
        {
            "request": request,
            "notion": notion,
        },
    )


# ------------------------------------------------------------------
# CHAT PAGE
# Student/Admin access
# ------------------------------------------------------------------


@app.get("/chat", response_class=HTMLResponse)
async def chat_page(
    request: Request,
    session: Session = Depends(get_session),
):

    user = get_current_user(request)

    if not user:
        return RedirectResponse("/test_login")

    if user.get("role") == "Teacher":
        return RedirectResponse("/teacher")

    notions = session.exec(select(models.Notion.notion_id, models.Notion.title)).all()

    return templates.TemplateResponse(
        "chat.html",
        {
            "request": request,
            "notions": notions,
        },
    )


# ------------------------------------------------------------------
# QCM PAGE
# Student/Admin access
# ------------------------------------------------------------------


@app.get("/qcm", response_class=HTMLResponse)
async def qcm_page(request: Request):

    user = get_current_user(request)

    if not user:
        return RedirectResponse("/test_login")

    if user.get("role") == "Teacher":
        return RedirectResponse("/teacher")

    return templates.TemplateResponse(
        "qcm.html",
        {"request": request},
    )


# ------------------------------------------------------------------
# Pydantic models
# ------------------------------------------------------------------


class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None


# ------------------------------------------------------------------
# CONVERSATIONS — liste les conversations de l'utilisateur
# ------------------------------------------------------------------


@app.get("/conversations")
async def list_conversations(
    request: Request,
    session: Session = Depends(get_session),
):
    user = get_current_user(request)

    if not user:
        return JSONResponse(status_code=401, content={"detail": "Non connecté"})

    sso_id = session.exec(
        select(models.User.sso_id).where(models.User.email == user["email"])
    ).first()

    if not sso_id:
        return JSONResponse(
            status_code=404, content={"detail": "Utilisateur introuvable"}
        )

    conversations = session.exec(
        select(models.Conversation)
        .where(models.Conversation.sso_id == sso_id)
        .order_by(models.Conversation.updated_at.desc())
    ).all()

    return {
        "ok": True,
        "conversations": [
            {
                "id": c.conversation_id,
                "title": c.title,
                "updated_at": c.updated_at.isoformat(),
                "started_at": c.started_at.isoformat(),
            }
            for c in conversations
        ],
    }


# ------------------------------------------------------------------
# CONVERSATIONS — charge une conversation complète
# ------------------------------------------------------------------


@app.get("/conversations/{conversation_id}")
async def get_conversation(
    request: Request,
    conversation_id: str,
    session: Session = Depends(get_session),
):
    user = get_current_user(request)

    if not user:
        return JSONResponse(status_code=401, content={"detail": "Non connecté"})

    conv = session.exec(
        select(models.Conversation).where(
            models.Conversation.conversation_id == conversation_id
        )
    ).first()

    if not conv:
        return JSONResponse(
            status_code=404, content={"detail": "Conversation introuvable"}
        )

    messages = session.exec(
        select(models.Message)
        .where(models.Message.conversation_id == conversation_id)
        .order_by(models.Message.sent_at.asc())
    ).all()

    return {
        "ok": True,
        "conversation": {
            "id": conv.conversation_id,
            "title": conv.title,
        },
        "messages": [{"role": m.role, "content": m.content} for m in messages],
    }


# ------------------------------------------------------------------
# Chat streaming endpoint
# Sauvegarde les messages en DB + historique 10 derniers messages
# ------------------------------------------------------------------


@app.post("/chat/stream")
async def chat_stream_endpoint(
    request: Request,
    data: ChatRequest,
    session: Session = Depends(get_session),
):
    user = get_current_user(request)

    if not user:
        return JSONResponse(status_code=401, content={"detail": "Non connecté"})

    sso_id = session.exec(
        select(models.User.sso_id).where(models.User.email == user["email"])
    ).first()

    now = datetime.utcnow()
    conversation_id = data.conversation_id

    # Nouvelle conversation si pas d'ID fourni
    if not conversation_id:
        conversation_id = str(uuid.uuid4())
        title = data.message[:47] + "..." if len(data.message) > 47 else data.message
        new_conv = models.Conversation(
            conversation_id=conversation_id,
            title=title,
            status="active",
            context_type="chat_libre",
            started_at=now,
            updated_at=now,
            sso_id=sso_id,
        )
        session.add(new_conv)
        session.commit()

    # Sauvegarde le message user
    user_msg = models.Message(
        message_id=str(uuid.uuid4()),
        role="user",
        content=data.message,
        sent_at=now,
        conversation_id=conversation_id,
    )
    session.add(user_msg)
    session.commit()

    # Récupère les 10 derniers messages pour le contexte Mistral
    all_messages = session.exec(
        select(models.Message)
        .where(models.Message.conversation_id == conversation_id)
        .order_by(models.Message.sent_at.asc())
    ).all()

    history = [{"role": m.role, "content": m.content} for m in all_messages[-10:]]

    full_response = []

    def generate():
        for chunk in chat_stream_with_history(history):
            full_response.append(chunk)
            yield f"data: {chunk}\n\n"

        # Envoie le conversation_id au frontend
        yield f"data: [CONV_ID:{conversation_id}]\n\n"
        yield "data: [DONE]\n\n"

        # Sauvegarde la réponse assistant en DB
        assistant_msg = models.Message(
            message_id=str(uuid.uuid4()),
            role="assistant",
            content="".join(full_response),
            sent_at=datetime.utcnow(),
            conversation_id=conversation_id,
        )
        session.add(assistant_msg)

        # Met à jour updated_at de la conversation
        conv = session.exec(
            select(models.Conversation).where(
                models.Conversation.conversation_id == conversation_id
            )
        ).first()
        if conv:
            conv.updated_at = datetime.utcnow()
            session.add(conv)

        session.commit()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ------------------------------------------------------------------
# Chat reset (legacy)
# ------------------------------------------------------------------


@app.post("/chat/reset")
async def chat_reset_endpoint():

    reset_conversation()

    return {
        "ok": True,
        "message": "Conversation reinitialisee",
    }


# ------------------------------------------------------------------
# Chat complete response (legacy)
# ------------------------------------------------------------------


@app.post("/chat/complete")
async def chat_complete_endpoint(data: ChatRequest):

    try:
        response = chat(data.message)

        return {
            "ok": True,
            "response": response,
        }

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": str(e),
            },
        )


# ------------------------------------------------------------------
# SESSION — reset scores d'une notion pour un élève
# Remet tous les attempts_count à 0 et scores à 0.5
# pour déclencher un nouveau positionnement
# ------------------------------------------------------------------


class ResetRequest(BaseModel):
    notion_key: str


@app.post("/session/reset")
async def reset_session_endpoint(
    request: Request,
    data: ResetRequest,
    session: Session = Depends(get_session),
):
    user = get_current_user(request)
    if not user:
        return JSONResponse(status_code=401, content={"detail": "Non connecté"})

    sso_id = session.exec(
        select(models.User.sso_id).where(models.User.email == user["email"])
    ).first()

    if not sso_id:
        return JSONResponse(
            status_code=404, content={"detail": "Utilisateur introuvable"}
        )

    try:
        from fonctions_python.main import REFERENTIEL
        from fonctions_python.scoring import compute_level_and_mastery
        from decimal import Decimal

        if data.notion_key not in REFERENTIEL:
            return JSONResponse(
                status_code=400, content={"ok": False, "error": "Notion inconnue"}
            )

        codes = [c["code"] for c in REFERENTIEL[data.notion_key]["competences"]]
        now = datetime.utcnow()
        reset_level, _ = compute_level_and_mastery(0.5, 0)

        rows = session.exec(
            select(models.Progression).where(
                models.Progression.sso_id == sso_id,
                models.Progression.competence_id.in_(codes),
            )
        ).all()

        for prog in rows:
            prog.score = Decimal("0.50")
            prog.level = reset_level
            prog.attempts_count = 0
            prog.updated_at = now
            session.add(prog)

        session.commit()
        return {"ok": True}

    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

        # ------------------------------------------------------------------


# Pydantic models — Session
# ------------------------------------------------------------------


class SessionRequest(BaseModel):
    notion_key: str


class SubmitAnswerRequest(BaseModel):
    notion_key: str
    competences_dict: dict  # { "tr01": True, "tr04": False }
    question_type: str  # "QCM" | "QRO" | "SBS"
    question_niveau: str  # "basique" | "solide" | "expert"


class EvaluateQRORequest(BaseModel):
    question: str
    correct_answer: str
    user_answer: str


# ------------------------------------------------------------------
# SESSION PAGE
# ------------------------------------------------------------------


@app.get("/session", response_class=HTMLResponse)
async def session_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/test_login")
    if user.get("role") == "Teacher":
        return RedirectResponse("/teacher")
    return templates.TemplateResponse("session.html", {"request": request})


# ------------------------------------------------------------------
# CHECK PREMIÈRE SESSION
# Retourne si c'est la première fois sur cette notion
# ------------------------------------------------------------------


@app.get("/session/check")
async def check_session(
    request: Request,
    notion_key: str,
    session: Session = Depends(get_session),
):
    user = get_current_user(request)
    if not user:
        return JSONResponse(status_code=401, content={"detail": "Non connecté"})

    sso_id = session.exec(
        select(models.User.sso_id).where(models.User.email == user["email"])
    ).first()

    if not sso_id:
        return JSONResponse(
            status_code=404, content={"detail": "Utilisateur introuvable"}
        )

    from fonctions_python.session_generator import is_first_session

    first = is_first_session(notion_key, sso_id, session)

    # Vérifier si training a déjà été lancé
    progress_id = f"{sso_id}_{notion_key}"
    notion_prog = session.exec(
        select(models.NotionProgress).where(
            models.NotionProgress.progress_id == progress_id
        )
    ).first()
    training_started = notion_prog.training_started if notion_prog else False

    return {"ok": True, "first_session": first, "training_started": training_started}


# ------------------------------------------------------------------
# GÉNÉRATION POSITIONNEMENT
# Première session : 5 QCM + 3 QRO + 2 SBS
# ------------------------------------------------------------------


@app.post("/session/positioning")
async def positioning_endpoint(
    request: Request,
    data: SessionRequest,
    session: Session = Depends(get_session),
):
    user = get_current_user(request)
    if not user:
        return JSONResponse(status_code=401, content={"detail": "Non connecté"})

    sso_id = session.exec(
        select(models.User.sso_id).where(models.User.email == user["email"])
    ).first()

    if not sso_id:
        return JSONResponse(
            status_code=404, content={"detail": "Utilisateur introuvable"}
        )

    try:
        from fonctions_python.session_generator import generate_positioning_session

        result = generate_positioning_session(data.notion_key, sso_id, session)
        return {"ok": True, **result}
    except ValueError as e:
        return JSONResponse(status_code=400, content={"ok": False, "error": str(e)})
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})


# ------------------------------------------------------------------
# GÉNÉRATION QUESTION ENTRAÎNEMENT
# Une question à la fois, niveau déduit des scores DB
# ------------------------------------------------------------------


@app.post("/session/next")
async def next_question_endpoint(
    request: Request,
    data: SessionRequest,
    session: Session = Depends(get_session),
):
    user = get_current_user(request)
    if not user:
        return JSONResponse(status_code=401, content={"detail": "Non connecté"})

    sso_id = session.exec(
        select(models.User.sso_id).where(models.User.email == user["email"])
    ).first()

    if not sso_id:
        return JSONResponse(
            status_code=404, content={"detail": "Utilisateur introuvable"}
        )

    try:
        from fonctions_python.session_generator import generate_next_question

        result = generate_next_question(data.notion_key, sso_id, session)
        return {"ok": True, **result}
    except ValueError as e:
        return JSONResponse(status_code=400, content={"ok": False, "error": str(e)})
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})


# ------------------------------------------------------------------
# SOUMETTRE UNE RÉPONSE — met à jour la progression en DB
# ------------------------------------------------------------------


@app.post("/session/submit")
async def submit_answer_endpoint(
    request: Request,
    data: SubmitAnswerRequest,
    session: Session = Depends(get_session),
):
    user = get_current_user(request)
    if not user:
        return JSONResponse(status_code=401, content={"detail": "Non connecté"})

    sso_id = session.exec(
        select(models.User.sso_id).where(models.User.email == user["email"])
    ).first()

    if not sso_id:
        return JSONResponse(
            status_code=404, content={"detail": "Utilisateur introuvable"}
        )

    try:
        from fonctions_python.session_generator import persist_score_update

        result = persist_score_update(
            sso_id=sso_id,
            competences_dict=data.competences_dict,
            question_type=data.question_type,
            question_niveau=data.question_niveau,
            db=session,
        )
        return {
            "ok": True,
            "new_scores": {code: r["score"] for code, r in result.items()},
            "mastery": {
                code: {"level": r["level"], "mastered": r["mastered"]}
                for code, r in result.items()
            },
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})


# ------------------------------------------------------------------
# ÉVALUATION QRO — LLM-as-judge via qro_generator
# ------------------------------------------------------------------


@app.post("/session/evaluate_qro")
async def evaluate_qro_endpoint(
    request: Request,
    data: EvaluateQRORequest,
):
    user = get_current_user(request)
    if not user:
        return JSONResponse(status_code=401, content={"detail": "Non connecté"})

    try:
        from fonctions_python.type_questions.qro_generator import evaluate_answer

        q = {"question": data.question, "correct_answer": data.correct_answer}
        correct, feedback = evaluate_answer(q, data.user_answer)
        return {"ok": True, "correct": correct, "feedback": feedback}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

        # ------------------------------------------------------------------


# SESSION — question ciblée sur une compétence spécifique# ------------------------------------------------------------------
# SESSION — feedback progressif via LLM_as_Evaluator
# ------------------------------------------------------------------


class FeedbackRequest(BaseModel):
    question: str
    correct_answer: str
    user_answer: str
    attempt: int
    competence: dict
    notion_nom: str
    notion_key: Optional[str] = None
    question_type: str


@app.post("/session/feedback")
async def feedback_endpoint(
    request: Request,
    data: FeedbackRequest,
    session: Session = Depends(get_session),
):
    user = get_current_user(request) or {"email": "test@epf.fr"}

    try:
        from fonctions_python.base_generator import client, MODEL
        from fonctions_python.main import REFERENTIEL

        instructions = {
            1: "Donne un indice court et orientant (2 phrases max). Ne donne pas la methode, juste une piste de reflexion.",
            2: "Explique la methode a suivre sans donner le resultat. Rappelle la definition ou la regle cle. 3-4 phrases.",
            3: "Donne une explication complete avec la formule ou la regle exacte. C'est la derniere chance. 4-5 phrases.",
        }

        instruction = instructions[min(data.attempt, 3)]
        prompt = (
            "Tu es un tuteur de mathematiques pour etudiants de premiere annee.\n"
            "Tentative " + str(data.attempt) + "/3.\n\n"
            "Question : " + data.question + "\n"
            "Reponse eleve : " + data.user_answer + "\n"
            "Competence : "
            + data.competence.get("nom", "")
            + " niveau "
            + data.competence.get("niveau", "")
            + "\n\n"
            "Consigne : " + instruction + "\n"
            "Ne donne JAMAIS la bonne reponse. Utilise le tu. Sois concis. Pas de JSON ni balises.\n"
        )

        response = client.chat.complete(
            model=MODEL, messages=[{"role": "user", "content": prompt}]
        )
        feedback = response.choices[0].message.content.strip()

        cross_module_reco = None
        if data.attempt >= 2 and data.notion_key:
            try:
                from lacune_evaluation.LLM_as_Evaluator import (
                    diagnostiquer_depuis_competence,
                )

                result_diag = diagnostiquer_depuis_competence(
                    notion=data.notion_nom,
                    niveau=data.competence.get("niveau", "basique"),
                    enonce=data.question,
                    reponse_correcte=data.correct_answer,
                    reponse_etudiant=data.user_answer,
                    competence_cible=data.competence,
                    nb_tentatives=data.attempt,
                )
                diag = result_diag.get("diagnostic", {}).get("diagnostic", {})
                lacunaires = diag.get("competences_lacunaires", [])
                notion_codes_courants = [
                    c["code"]
                    for c in REFERENTIEL.get(data.notion_key, {}).get("competences", [])
                ]
                for lac in lacunaires:
                    if (
                        lac.get("source") == "detectee_passe2"
                        and lac.get("code") not in notion_codes_courants
                    ):
                        notion_trouvee = None
                        notion_nom_trouvee = None
                        for nkey, ndata in REFERENTIEL.items():
                            if nkey == data.notion_key:
                                continue
                            for c in ndata["competences"]:
                                if c["code"] == lac.get("code"):
                                    notion_trouvee = nkey
                                    notion_nom_trouvee = ndata["notion_nom"]
                                    break
                            if notion_trouvee:
                                break
                        if notion_trouvee:
                            sso_id = session.exec(
                                select(models.User.sso_id).where(
                                    models.User.email == user["email"]
                                )
                            ).first()
                            if sso_id:
                                reco_id = f"{sso_id}_{data.notion_key}_{notion_trouvee}"
                                existing = session.exec(
                                    select(models.ModuleRecommendation).where(
                                        models.ModuleRecommendation.recommendation_id
                                        == reco_id
                                    )
                                ).first()
                                if existing:
                                    existing.count += 1
                                    existing.updated_at = datetime.utcnow()
                                    session.add(existing)
                                    cross_module_reco = {
                                        "notion_key": notion_trouvee,
                                        "notion_nom": notion_nom_trouvee,
                                        "count": existing.count,
                                    }
                                else:
                                    session.add(
                                        models.ModuleRecommendation(
                                            recommendation_id=reco_id,
                                            sso_id=sso_id,
                                            notion_source=data.notion_key,
                                            notion_lacunaire=notion_trouvee,
                                            notion_lacunaire_nom=notion_nom_trouvee,
                                            count=1,
                                            updated_at=datetime.utcnow(),
                                        )
                                    )
                                session.commit()
                        break
            except Exception as reco_err:
                print("Reco error:", reco_err)

        return {
            "ok": True,
            "feedback": feedback,
            "can_retry": data.attempt < 3,
            "cross_module_reco": cross_module_reco,
        }

    except Exception as e:
        import traceback

        print("FEEDBACK ERROR:", traceback.format_exc())
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})


# ------------------------------------------------------------------
# SESSION — question ciblée sur une compétence spécifique
# ------------------------------------------------------------------


class NextTargetedRequest(BaseModel):
    notion_key: str
    competence_code: str


@app.post("/session/next_targeted")
async def next_targeted_endpoint(
    request: Request,
    data: NextTargetedRequest,
    session: Session = Depends(get_session),
):
    user = get_current_user(request)
    if not user:
        return JSONResponse(status_code=401, content={"detail": "Non connecté"})

    sso_id = session.exec(
        select(models.User.sso_id).where(models.User.email == user["email"])
    ).first()
    if not sso_id:
        return JSONResponse(
            status_code=404, content={"detail": "Utilisateur introuvable"}
        )

    try:
        from fonctions_python.session_generator import build_notion_data_with_scores
        from fonctions_python.main import REFERENTIEL
        import random

        if data.notion_key not in REFERENTIEL:
            return JSONResponse(
                status_code=400, content={"ok": False, "error": "Notion inconnue"}
            )

        notion_data = build_notion_data_with_scores(data.notion_key, sso_id, session)
        notion_nom = notion_data["notion_nom"]

        # Trouver la compétence ciblée
        comp = next(
            (
                c
                for c in notion_data["competences"]
                if c["code"] == data.competence_code
            ),
            None,
        )
        if not comp:
            return JSONResponse(
                status_code=400, content={"ok": False, "error": "Compétence inconnue"}
            )

        # Générer QCM ou QRO aléatoirement
        qtype = random.choice(["qcm", "qro"])

        if qtype == "qcm":
            from fonctions_python.type_questions.qcm_generator import generate_qcm

            question = generate_qcm(notion_data, comp)
            question["type"] = "qcm"
        else:
            from fonctions_python.type_questions.qro_generator import generate_qro

            question = generate_qro(notion_data, comp)
            question["type"] = "qro"

        question["notion_nom"] = notion_nom

        return {"ok": True, "questions": [question], "notion_nom": notion_nom}

    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})


# ------------------------------------------------------------------
# Run app
# ------------------------------------------------------------------


# ------------------------------------------------------------------
# SESSION — marquer l'entraînement comme commencé (par notion)
# ------------------------------------------------------------------


class TrainingStartedRequest(BaseModel):
    notion_key: str


@app.post("/session/training_started")
async def mark_training_started(
    request: Request,
    data: TrainingStartedRequest,
    session: Session = Depends(get_session),
):
    user = get_current_user(request) or {"email": "test@epf.fr"}
    sso_id = session.exec(
        select(models.User.sso_id).where(models.User.email == user["email"])
    ).first()
    if not sso_id:
        return JSONResponse(
            status_code=404, content={"detail": "Utilisateur introuvable"}
        )
    try:
        progress_id = f"{sso_id}_{data.notion_key}"
        existing = session.exec(
            select(models.NotionProgress).where(
                models.NotionProgress.progress_id == progress_id
            )
        ).first()
        if existing:
            existing.training_started = True
            existing.updated_at = datetime.utcnow()
            session.add(existing)
        else:
            session.add(
                models.NotionProgress(
                    progress_id=progress_id,
                    sso_id=sso_id,
                    notion_key=data.notion_key,
                    training_started=True,
                    updated_at=datetime.utcnow(),
                )
            )
        session.commit()
        return {"ok": True}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})


# ------------------------------------------------------------------
# SESSION — check si training_started (intégré dans /session/check)
# ------------------------------------------------------------------

# Modifier /session/check pour retourner aussi training_started
# (voir endpoint check_session ci-dessus — on patch son return)


# ------------------------------------------------------------------
# SESSION — génération test d'évaluation (10/15/20 questions)
# ------------------------------------------------------------------


class EvaluationRequest(BaseModel):
    notion_key: str
    n_questions: int = 10  # 10 | 15 | 20


@app.post("/session/evaluation")
async def evaluation_endpoint(
    request: Request,
    data: EvaluationRequest,
    session: Session = Depends(get_session),
):
    user = get_current_user(request) or {"email": "test@epf.fr"}
    sso_id = session.exec(
        select(models.User.sso_id).where(models.User.email == user["email"])
    ).first()
    if not sso_id:
        return JSONResponse(
            status_code=404, content={"detail": "Utilisateur introuvable"}
        )

    try:
        from fonctions_python.session_generator import build_notion_data_with_scores
        from fonctions_python.main import generate_mixed_test
        import random

        n = max(5, min(20, data.n_questions))

        # Distribution adaptée aux compétences disponibles par niveau
        # basique: peu de compétences → 20%
        # solide: beaucoup → 50%
        # expert: moyen → 30%
        n_bas = max(1, round(n * 0.2))
        n_sol = max(1, round(n * 0.5))
        n_exp = max(1, n - n_bas - n_sol)

        def split(total):
            if total <= 0:
                return 0, 0, 0
            qcm = max(1, round(total * 0.5))
            qro = max(1, round(total * 0.3))
            sbs = max(0, total - qcm - qro)
            return qcm, qro, sbs

        notion_data = build_notion_data_with_scores(data.notion_key, sso_id, session)
        notion_nom = notion_data["notion_nom"]

        q_bas = generate_mixed_test(
            notion=data.notion_key,
            niveau="basique",
            n_qcm=split(n_bas)[0],
            n_qro=split(n_bas)[1],
            n_steps=split(n_bas)[2],
            notion_data_override=notion_data,
        )
        q_sol = generate_mixed_test(
            notion=data.notion_key,
            niveau="solide",
            n_qcm=split(n_sol)[0],
            n_qro=split(n_sol)[1],
            n_steps=split(n_sol)[2],
            notion_data_override=notion_data,
        )
        q_exp = generate_mixed_test(
            notion=data.notion_key,
            niveau="expert",
            n_qcm=split(n_exp)[0],
            n_qro=split(n_exp)[1],
            n_steps=split(n_exp)[2],
            notion_data_override=notion_data,
        )

        questions = q_bas + q_sol + q_exp

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
            "ok": True,
            "questions": questions,
            "notion_nom": notion_nom,
            "n_questions": len(questions),
        }

    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
    )
