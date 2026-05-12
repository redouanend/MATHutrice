from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn
from pydantic import BaseModel
from test_format_generator.QCM import generate_qcm_statement

app = FastAPI()

app.mount("/static", StaticFiles(directory="generator_test/static"), name="static")

templates = Jinja2Templates(directory="generator_test/templates")


@app.get("/", include_in_schema=True)
async def page_home(request: Request):
    return templates.TemplateResponse(request, "index.html")


class Data(BaseModel):
    notion: str


# Récupération de la requête contenant le nom de la notion (envoyer par le frontend)
@app.post("/generate_exo", include_in_schema=True)
async def get_notion(request: Request, data: Data):
    qcm_data = generate_qcm_statement(data.notion, niveau="légendaire")

    return templates.TemplateResponse(
        "qcm.html", {"request": request, "questions": [qcm_data]}
    )


uvicorn.run(app, host="localhost", port=8000)
