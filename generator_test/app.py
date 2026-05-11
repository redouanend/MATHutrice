from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import os
from test_format_generator.QCM import generate_qcm_statement
# from generator_test.fonctions_python.test_entrainement import generate_mixed_test


app = FastAPI()

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
async def home_page(request: Request):
    return templates.TemplateResponse("home.html", {"request": request})


@app.get("/module.html", response_class=HTMLResponse)
async def module_page(request: Request):
    return templates.TemplateResponse("module.html", {"request": request})


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
