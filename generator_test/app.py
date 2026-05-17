from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
from test_format_generator.QCM import generate_qcm_statement
from contextlib import asynccontextmanager
from database import engine, get_session, Session
from sqlmodel import SQLModel, select
import models
import os




def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield


app = FastAPI(lifespan=lifespan)

# ── CORS (permet au HTML servi statiquement d'appeler l'API) ──────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Chemins ───────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app.mount(
    "/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static"
)
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))





# ── Pages HTML existantes ─────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
async def home_page(request: Request, session: Session = Depends(get_session)):
    notions = session.exec(select(models.Notion.notion_id, models.Notion.title)).all()
    return templates.TemplateResponse("home.html", {"request": request,"notions" : notions})


@app.get("/module.html", response_class=HTMLResponse)
async def module_page(request: Request, id: str, session: Session = Depends(get_session)):
    notion = session.exec(
        select(models.Notion.title, models.Notion.description).where(models.Notion.notion_id == id)
    ).first()
    return templates.TemplateResponse("module.html", {"request":request, "notion":notion} )


@app.get("/index", response_class=HTMLResponse)
async def index_page(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/qcm", response_class=HTMLResponse)
async def qcm_page(request: Request):
    return templates.TemplateResponse("qcm.html", {"request": request})


# ── Modèles Pydantic ──────────────────────────────────────────────────────────


class Data(BaseModel):
    notion: str


class QCMRequest(BaseModel):
    notion: str = "trigonométrie"
    niveau: str = "intermédiaire"
    n: int = 9


# ── Endpoint existant (conservé tel quel) ─────────────────────────────────────


# @app.post("/generate_exo", include_in_schema=True)
# async def get_notion(request: Request, data: Data):
#     questions = generate_mixed_test(
#         notion=data.notion,
#         niveau="intermédiaire",
#         n_qcm=2,
#         n_qro=2,
#         n_steps=1,
#     )
#     return templates.TemplateResponse(
#         "qcm.html",
#         {
#             "request": request,
#             "questions": questions,
#             "notion": data.notion,
#             "niveau": "intermédiaire",
#         },
#     )


# ── NOUVEL ENDPOINT : génère N questions QCM en JSON pur ─────────────────────
#
#   POST /generate_qcm
#   Body JSON : { "notion": "trigonométrie", "niveau": "intermédiaire", "n": 9 }
#
#   Retourne :
#   {
#     "ok": true,
#     "notion": "trigonométrie",
#     "niveau": "intermédiaire",
#     "questions": [
#       { "question": "...", "options": ["...", "...", "...", "..."], "answer": "..." },
#       ...
#     ]
#   }


@app.post("/generate_qcm")
async def generate_qcm_endpoint(data: QCMRequest):
    questions = []
    errors = []

    for i in range(data.n):
        try:
            qcm = generate_qcm_statement(notion=data.notion, niveau=data.niveau)
            questions.append(qcm)
        except Exception as e:
            errors.append({"index": i, "error": str(e)})

    if not questions:
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": "Aucune question générée",
                "details": errors,
            },
        )

    return {
        "ok": True,
        "notion": data.notion,
        "niveau": data.niveau,
        "questions": questions,
        "errors": errors,
    }


# ── Lancement ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(app)
