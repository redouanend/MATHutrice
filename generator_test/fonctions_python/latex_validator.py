import re

def validate_latex_syntax(text: str) -> tuple[bool, str]:
    """
    Valide la syntaxe LaTeX pour les délimiteurs inline et bloc.
    Retourne (True, "") si valide, sinon (False, "raison de l'erreur").
    """
    # 1. Vérifier l'absence de délimiteurs obsolètes ($ et $$)
    if "$" in text:
        return False, "Présence de délimiteurs obsolètes ($ ou $$) détectés."

    # 2. Vérifier l'équilibre des délimiteurs inline \( ... \)
    # On compte le nombre de \( et de \)
    inline_open = len(re.findall(r"\\\(", text))
    inline_close = len(re.findall(r"\\\)", text))

    if inline_open != inline_close:
        return False, f"Déséquilibre des délimiteurs inline : {inline_open} ouvert(s) vs {inline_close} fermé(s)."

    # 3. Vérifier l'équilibre des délimiteurs de bloc \[ ... \]
    block_open = len(re.findall(r"\\\[", text))
    block_close = len(re.findall(r"\\\]", text))

    if block_open != block_close:
        return False, f"Déséquilibre des délimiteurs de bloc : {block_open} ouvert(s) vs {block_close} fermé(s)."

    return True, ""
