import dash
from dash import html, dcc, Input, Output, State
import dash_bootstrap_components as dbc

from test_ia import client, MODEL, messages

############################ REQUIREMENTS ###########################
# pip install dash
# pip install dash_bootstrap_components
#####################################################################

# =====================
# App initialization
# =====================
app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.VAPOR],
)
app.title = "MathTutrice"

# =====================
# Styles
# =====================
CHAT_CONTAINER_STYLE = {
    "height": "65vh",
    "width": "100%",
    "overflowY": "auto",
    "padding": "10px",
    "backgroundColor": "#f6f2ff",
    "borderRadius": "12px",
    "fontFamily": "Poppins, sans-serif",
}

USER_BUBBLE = {
    "backgroundColor": "#c2abed",
    "color": "white",
    "padding": "10px 20px",
    "borderRadius": "15px",
    "maxWidth": "75%",
    "marginLeft": "auto",
    "marginTop": "10px",
    "fontSize": "20px",
    "fontFamily": "Poppins, sans-serif",
}

BOT_BUBBLE = {
    "backgroundColor": "white",
    "color": "#3d246c",
    "padding": "10px 14px",
    "borderRadius": "15px",
    "maxWidth": "75%",
    "border": "2px solid #e0d7f5",
    "fontSize": "20px",
    "fontFamily": "Poppins, sans-serif",
}


WELCOME_MESSAGE = html.Div(
    "Bonjour 👋 Je suis MathTutrice, votre assistant IA en mathématiques. Posez-moi une question sur n'importe quelle notion !",
    style=BOT_BUBBLE,
    # className="mb-3",
)


# =====================
# Layout
# =====================
app.layout = dbc.Container(
    fluid=True,
    children=[
        dcc.Store(id="pending-response"),
        dbc.Row(
            dbc.Col(
                html.H2(
                    "GenBot. by Génération IA",
                    className="text-center",
                    style={
                        "color": "#ffffff",
                        "marginTop": "20px",
                        "marginBottom": "20px",
                        "fontFamily": "Poppins, sans-serif",
                    },
                )
            )
        ),
        dbc.Row(
            dbc.Col(
                html.Div(
                    id="chat-window",
                    children=[WELCOME_MESSAGE],  # 👈 message affiché dès l’ouverture
                    style=CHAT_CONTAINER_STYLE,
                )
            )
        ),
        dbc.Row(
            [
                dbc.Col(
                    dcc.Input(
                        id="user-input",
                        type="text",
                        placeholder="Posez votre question à MathTutrice...",
                        # className="form-control",
                    ),
                    width=10,
                    style={
                        "marginTop": "10px",
                        "borderRadius": "15px 0 0 15px",
                        "fontSize": "20px",
                        "padding": "10px",
                        "color": "#3d246c",
                        "fontFamily": "Poppins, sans-serif",
                    },
                ),
                dbc.Col(
                    dbc.Button(
                        "Envoyer",
                        id="send-button",
                        color="primary",
                        className="w-100",
                    ),
                    width=2,
                    style={
                        "marginTop": "10px",
                        "borderRadius": "15px",
                        "padding": "10px",
                        "fontFamily": "Poppins, sans-serif",
                    },
                ),
            ],
            className="mt-3",
        ),
    ],
)


# =====================
# Callback
# =====================
@app.callback(
    Output("chat-window", "children", allow_duplicate=True),
    Output("pending-response", "data"),
    Output("user-input", "value"),
    Input("send-button", "n_clicks"),
    Input("user-input", "n_submit"),
    State("user-input", "value"),
    State("chat-window", "children"),
    prevent_initial_call=True,
)
def user_message(n_clicks, n_submit, user_input, chat_history):

    if not user_input:
        return chat_history, None, ""

    if chat_history is None:
        chat_history = []

    # message utilisateur instantané
    chat_history.append(html.Div(user_input, style=USER_BUBBLE, className="mb-2"))

    # message "GenBot écrit..."
    chat_history.append(
        html.Div(
            "MathTutrice écrit...",
            style={**BOT_BUBBLE, "fontStyle": "italic", "color": "#888"},
            className="mb-3",
            key="typing",
        )
    )

    messages.append({"role": "user", "content": user_input})

    return chat_history, "go", ""


@app.callback(
    Output("chat-window", "children"),
    Input("pending-response", "data"),
    State("chat-window", "children"),
    prevent_initial_call=True,
)
def bot_response(trigger, chat_history):

    if trigger != "go":
        return chat_history

    response = client.chat.complete(model=MODEL, messages=messages)
    bot_reply = response.choices[0].message.content
    bot_reply = f"$${bot_reply}$$"  # pour activer MathJax
    messages.append({"role": "assistant", "content": bot_reply})

    # retirer "GenBot écrit..."
    chat_history = [c for c in chat_history if getattr(c, "key", None) != "typing"]

    chat_history.append(
        html.Div(
            dcc.Markdown(bot_reply, mathjax=True, style={"whiteSpace": "pre-wrap", "wordWrap": "break-word","overflowWrap": "break-word"}),
            style=BOT_BUBBLE,
            className="mb-3",
        )
    )

    return chat_history

    # Message utilisateur
    # chat_history.append(html.Div(user_input, style=USER_BUBBLE, className="mb-2"))

    # messages.append({"role": "user", "content": user_input})

    # response = client.chat.complete(
    #     model=MODEL,
    #     messages=messages,
    # )

    # bot_reply = response.choices[0].message.content
    # messages.append({"role": "assistant", "content": bot_reply})

    # # Message bot
    # chat_history.append(
    #     html.Div(
    #         dcc.Markdown(
    #             bot_reply,
    #             style={"whiteSpace": "pre-wrap"},
    #         ),
    #         style=BOT_BUBBLE,
    #         className="mb-3",
    #     )
    # )
    # return chat_history, ""  # vide le champ texte


# =====================
# Run server
# =====================
if __name__ == "__main__":
    app.run(debug=True)
