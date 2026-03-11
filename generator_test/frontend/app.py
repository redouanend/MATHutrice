from flask import Flask, render_template, request, jsonify


app = Flask(__name__)


# Route vers le page html qui affiche les bouttons
@app.route("/", methods=["GET"])
def home():
    return render_template("index.html")


# Récupération de la requête contenant le nom de la notion (envoyer par le frontend)
@app.route("/generate_exo", methods=["POST"])
def get_notion():

    result = request.get_json()
    notion = result["notion"]

    # Il faut renvoyer un statu de la requête au front
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    app.run(debug=True)


# from fastapi import FastAPI, Request
# from fastapi.responses import HTMLResponse
# from fastapi.staticfiles import StaticFiles
# from fastapi.templating import Jinja2Templates

# app = FastAPI()

# app.mount("/static", StaticFiles(directory="../static"), name="static")

# templates = Jinja2Templates(directory="../templates")
