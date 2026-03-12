from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn
from pydantic import BaseModel

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
async def get_notion(data: Data):
    print(data.notion)


uvicorn.run(app, host="localhost", port=8000)
