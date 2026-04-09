from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import uvicorn
import os
from test_format_generator.QCM import generate_qcm_statement
from templates.test_temporaire import generate_mixed_test


app = FastAPI()

# ── Chemin absolu pour éviter les problèmes de chemins ──
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Data(BaseModel):
    notion: str


# Static
app.mount(
    "/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static"
)

# Templates (on peut tous les regrouper dans un seul dossier si possible)
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


# ── PAGE 1 : home.html
@app.get("/", response_class=HTMLResponse)
async def home_page(request: Request):
    return templates.TemplateResponse("home.html", {"request": request})


# ── PAGE 2 : module.html
@app.get("/module.html", response_class=HTMLResponse)
async def module_page(request: Request):
    return templates.TemplateResponse("module.html", {"request": request})


# ── PAGE 3 : index.html
@app.get("/index", response_class=HTMLResponse)
async def index_page(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/generate_exo")
async def get_notion(request: Request, data: Data):
    # Génère les questions avec la même logique que main.py
    qcm_data = generate_mixed_test(
        notion=data.notion,
        niveau="intermédiaire",  # ou récupéré de data
        n_qcm=5,
        n_qro=2,
        n_steps=1,
    )
    return templates.TemplateResponse(
        "qcm.html", {"request": request, "questions": qcm_data}
    )


# ── API
class Data(BaseModel):
    notion: str


@app.post("/generate_exo", include_in_schema=True)
async def get_notion(request: Request, data: Data):
    qcm_data = generate_qcm_statement(data.notion, niveau="Intermédiaire")
    print(qcm_data)
    return templates.TemplateResponse(
        "qcm.html", {"request": request, "questions": qcm_data}
    )


if __name__ == "__main__":
    uvicorn.run(app, host="localhost", port=8000)
