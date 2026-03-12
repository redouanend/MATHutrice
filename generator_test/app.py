from flask import Flask, render_template, request, jsonify
from generator_test.test_format_generator.main import genererate_prompt

app = Flask(__name__)


# Route vers le page html qui affiche les bouttons
@app.route("/", methods=["GET"])
def home():
    return render_template("index.html")


# Récupération de la requête contenant le nom de la notion (envoyer par le frontend)
@app.route("/generate_exo", methods=["POST", "GET"])
def get_notion():

    result = request.get_json()
    notion = result["notion"]

    # Test que Jiro a fait (temporaire)
    format = """ {"question": "Texte de la question", "options": ["rép1", "rép2", "rép3", "rép4"],"answer": "bonne reponse exacte""}
        Règles spécifiques :
        - Réponds uniquement avec un JSON valide.
        - "options" doit contenir exactement 4 propositions.
        - Une seule réponse est correcte.
        - La bonne réponse doit être présente dans "options".
        - Ne mets aucun texte hors JSON.
        - Ne mets pas de markdown.
        - Ne mets pas de ```json.
        """

    print(
        genererate_prompt(
            notion,
            format,
        )
    )

    # Fin du test

    # Il faut renvoyer un statut de la requête au frontend pour confirmer si tout s'est bien passé ou pas
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    app.run(debug=True)


# from fastapi import FastAPI, Request
# from fastapi.responses import HTMLResponse
# from fastapi.staticfiles import StaticFiles
# from fastapi.templating import Jinja2Templates

# app = FastAPI()

# app.mount("/static", StaticFiles(directory="static"), name="static")

# templates = Jinja2Templates(directory="/templates")

# @app.get("/")
# async def root():
#     def home():
#     return render_template("index.html")
