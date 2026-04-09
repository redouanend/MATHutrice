"""
verifier.py — Vérification mathématique des QCM via SymPy

Principe :
  Mistral génère une question + 4 options + son answer.
  Ce module tente de recalculer la vraie réponse via SymPy,
  puis compare avec ce que Mistral a fourni.

Résultats possibles pour chaque question :
  - "correct"  : Mistral a la bonne réponse ✅
  - "wrong"    : Mistral s'est trompé, on corrige l'answer ⚠
  - "unverifiable" : SymPy ne peut pas vérifier ce type de question 🔵
"""

import re
import logging
from sympy import (
    sympify, simplify, trigsimp, cancel, cos, sin, tan, pi, sqrt, I,
    Rational, symbols, diff, expand, Abs, arg, conjugate, im, re as Re,
    parse_expr, SympifyError
)
from sympy.parsing.sympy_parser import (
    standard_transformations, implicit_multiplication_application
)

logger = logging.getLogger(__name__)

# Transformations sympy pour parser des expressions comme "2x" → "2*x"
TRANSFORMATIONS = standard_transformations + (implicit_multiplication_application,)

x = symbols('x')


# ─── UTILITAIRES DE PARSING ───────────────────────────────────────────────────

def parse_expression(expr_str: str):
    """
    Tente de parser une chaîne en expression SymPy.
    Gère les notations courantes : "1/2", "sqrt(3)/2", "pi/4", etc.
    Retourne None si le parsing échoue.
    """
    # Nettoyages avant parsing
    s = expr_str.strip()
    s = s.replace("^", "**")       # notation puissance courante
    s = s.replace("√", "sqrt")     # symbole racine carrée unicode
    s = re.sub(r'\bpi\b', 'pi', s) # sécurise pi

    try:
        return parse_expr(s, transformations=TRANSFORMATIONS)
    except (SympifyError, TypeError, SyntaxError):
        return None


def expressions_equal(a_str: str, b_str: str) -> bool:
    """
    Vérifie si deux expressions SymPy sont mathématiquement égales.
    Retourne False en cas d'échec de parsing ou de comparaison.
    """
    a = parse_expression(a_str)
    b = parse_expression(b_str)
    if a is None or b is None:
        return False
    try:
        return simplify(a - b) == 0
    except Exception:
        return False


def find_matching_option(computed, options: list[str]) -> str | None:
    """
    Parmi les 4 options, trouve celle qui est mathématiquement
    égale à l'expression SymPy calculée.
    Retourne l'option (str) ou None si aucune ne correspond.
    """
    for opt in options:
        opt_expr = parse_expression(opt)
        if opt_expr is None:
            continue
        try:
            if simplify(computed - opt_expr) == 0:
                return opt
        except Exception:
            continue
    return None


# ─── DÉTECTEURS DE TYPE DE QUESTION ──────────────────────────────────────────

def detect_question_type(question: str) -> str:
    """
    Détecte le type mathématique d'une question à partir de mots-clés.
    Retourne un identifiant de type pour router vers le bon vérificateur.
    """
    q = question.lower()

    if any(k in q for k in ["dérivée", "dériver", "f'(x)", "d/dx", "derive"]):
        return "derivee"

    if any(k in q for k in ["cos(", "sin(", "tan(", "cos ", "sin ", "tan ",
                              "cosinus", "sinus", "tangente"]):
        return "trigonometrie"

    if any(k in q for k in ["module", "|z|", "argument", "arg(", "conjugué",
                              "partie réelle", "partie imaginaire", "forme algébrique",
                              "nombre complexe", "complexe"]):
        return "complexe"

    if any(k in q for k in ["fraction", "simplif", "/", "pgcd", "irreductible"]):
        return "fraction"

    return "inconnu"


# ─── VÉRIFICATEURS PAR NOTION ────────────────────────────────────────────────

def verify_trigonometrie(question: str, options: list[str], answer: str) -> dict:
    """
    Vérifie les questions de trigonométrie avec valeurs exactes.
    Cherche une expression du type cos(...), sin(...), tan(...) dans la question.
    """
    # Extraction de l'expression trig dans la question
    # Exemple : "Quelle est la valeur de cos(π/3) ?"
    pattern = r"(cos|sin|tan)\s*\(([^)]+)\)"
    match = re.search(pattern, question, re.IGNORECASE)

    if not match:
        return {"status": "unverifiable", "reason": "Expression trig non extraite"}

    func_name = match.group(1).lower()
    arg_str   = match.group(2).strip()

    # Parse l'argument (ex: "π/3", "pi/4", "2π/3")
    arg_str = arg_str.replace("π", "pi").replace("^", "**")
    arg_expr = parse_expression(arg_str)

    if arg_expr is None:
        return {"status": "unverifiable", "reason": f"Argument non parseable : '{arg_str}'"}

    # Calcul SymPy exact
    func_map = {"cos": cos, "sin": sin, "tan": tan}
    try:
        computed = trigsimp(func_map[func_name](arg_expr))
    except Exception as e:
        return {"status": "unverifiable", "reason": f"Calcul SymPy échoué : {e}"}

    # Cherche l'option qui correspond au résultat calculé
    matching = find_matching_option(computed, options)

    if matching is None:
        return {
            "status": "unverifiable",
            "reason": f"Résultat calculé ({computed}) ne correspond à aucune option"
        }

    if matching == answer:
        return {"status": "correct"}
    else:
        return {
            "status": "wrong",
            "computed_answer": matching,
            "reason": f"Mistral dit '{answer}', SymPy calcule '{matching}' ({computed})"
        }


def verify_derivee(question: str, options: list[str], answer: str) -> dict:
    """
    Vérifie les questions de dérivation.
    Cherche une expression f(x) = ... dans la question.
    """
    # Extraction de f(x) = expression
    pattern = r"f\s*\(x\)\s*=\s*([^\n,\.?]+)"
    match = re.search(pattern, question, re.IGNORECASE)

    if not match:
        return {"status": "unverifiable", "reason": "Expression f(x) non trouvée"}

    expr_str = match.group(1).strip()
    expr = parse_expression(expr_str)

    if expr is None:
        return {"status": "unverifiable", "reason": f"Expression non parseable : '{expr_str}'"}

    # Calcul de la dérivée
    try:
        computed = diff(expr, x)
        computed = simplify(computed)
    except Exception as e:
        return {"status": "unverifiable", "reason": f"Dérivée échouée : {e}"}

    # Cherche l'option correspondante
    matching = find_matching_option(computed, options)

    if matching is None:
        return {
            "status": "unverifiable",
            "reason": f"Dérivée calculée ({computed}) ne correspond à aucune option"
        }

    if matching == answer:
        return {"status": "correct"}
    else:
        return {
            "status": "wrong",
            "computed_answer": matching,
            "reason": f"Mistral dit '{answer}', SymPy dérive '{matching}' ({computed})"
        }


def verify_fraction(question: str, options: list[str], answer: str) -> dict:
    """
    Vérifie les questions sur les fractions (simplification, opérations).
    Cherche une expression fractionnaire dans la question.
    """
    # Cherche une expression calculable dans la question
    # Exemples : "6/8", "2/3 + 1/4", "(3/5) * (10/9)"
    pattern = r"([\d\s\+\-\*\/\(\)]+\/[\d\s\+\-\*\/\(\)]+)"
    match = re.search(pattern, question)

    if not match:
        return {"status": "unverifiable", "reason": "Expression fractionnaire non trouvée"}

    expr_str = match.group(1).strip()
    expr = parse_expression(expr_str)

    if expr is None:
        return {"status": "unverifiable", "reason": f"Fraction non parseable : '{expr_str}'"}

    try:
        computed = cancel(expr)  # simplifie la fraction au maximum
    except Exception as e:
        return {"status": "unverifiable", "reason": f"Simplification échouée : {e}"}

    matching = find_matching_option(computed, options)

    if matching is None:
        return {
            "status": "unverifiable",
            "reason": f"Résultat ({computed}) ne correspond à aucune option"
        }

    if matching == answer:
        return {"status": "correct"}
    else:
        return {
            "status": "wrong",
            "computed_answer": matching,
            "reason": f"Mistral dit '{answer}', SymPy calcule '{matching}' ({computed})"
        }


def verify_complexe(question: str, options: list[str], answer: str) -> dict:
    """
    Vérifie les questions sur les nombres complexes.
    Cherche z = a + bi dans la question et calcule module/argument/conjugué.
    """
    # Extraction de z = ... (ex: "z = 3 + 4i", "z = 1 - 2i")
    pattern = r"z\s*=\s*([\d\+\-\*\/\s\.ij]+)"
    match = re.search(pattern, question, re.IGNORECASE)

    if not match:
        return {"status": "unverifiable", "reason": "Nombre complexe z non trouvé"}

    z_str = match.group(1).strip()
    z_str = z_str.replace("i", "*I").replace("j", "*I")
    z_expr = parse_expression(z_str)

    if z_expr is None:
        return {"status": "unverifiable", "reason": f"z non parseable : '{z_str}'"}

    # Détermine ce qu'on cherche dans la question
    q = question.lower()
    try:
        if "module" in q or "|z|" in q:
            computed = simplify(Abs(z_expr))
        elif "argument" in q or "arg(" in q:
            computed = simplify(arg(z_expr))
        elif "conjugué" in q or "conjugate" in q:
            computed = conjugate(z_expr)
        elif "partie réelle" in q:
            computed = Re(z_expr)
        elif "partie imaginaire" in q:
            computed = im(z_expr)
        else:
            return {"status": "unverifiable", "reason": "Type de calcul complexe non identifié"}
    except Exception as e:
        return {"status": "unverifiable", "reason": f"Calcul complexe échoué : {e}"}

    matching = find_matching_option(computed, options)

    if matching is None:
        return {
            "status": "unverifiable",
            "reason": f"Résultat ({computed}) ne correspond à aucune option"
        }

    if matching == answer:
        return {"status": "correct"}
    else:
        return {
            "status": "wrong",
            "computed_answer": matching,
            "reason": f"Mistral dit '{answer}', SymPy calcule '{matching}' ({computed})"
        }


# ─── POINT D'ENTRÉE PRINCIPAL ─────────────────────────────────────────────────

def verify_question(q: dict) -> dict:
    """
    Vérifie une question QCM via SymPy.
    
    Input  : dict avec clés 'question', 'options', 'answer'
    Output : dict avec clé 'status' parmi :
               - "correct"      : réponse de Mistral validée
               - "wrong"        : réponse corrigée dans 'computed_answer'
               - "unverifiable" : SymPy ne peut pas vérifier
             + clé 'reason' (optionnelle) pour debug

    Comportement en cas d'erreur inattendue :
    Retourne "unverifiable" plutôt que de planter.
    """
    question = q["question"]
    options  = q["options"]
    answer   = q["answer"]

    question_type = detect_question_type(question)
    logger.debug(f"Type détecté : {question_type} | Question : {question[:60]}...")

    verifiers = {
        "trigonometrie": verify_trigonometrie,
        "derivee":       verify_derivee,
        "fraction":      verify_fraction,
        "complexe":      verify_complexe,
    }

    if question_type not in verifiers:
        return {"status": "unverifiable", "reason": "Notion non couverte par SymPy"}

    try:
        result = verifiers[question_type](question, options, answer)
    except Exception as e:
        logger.warning(f"Erreur inattendue dans verify_{question_type} : {e}")
        result = {"status": "unverifiable", "reason": f"Erreur interne : {e}"}

    # Log du résultat
    status = result["status"]
    if status == "correct":
        logger.info(f"✅ Vérifié correct")
    elif status == "wrong":
        logger.warning(f"⚠  Réponse corrigée : '{answer}' → '{result.get('computed_answer')}'")
    else:
        logger.debug(f"🔵 Non vérifiable : {result.get('reason', '')}")

    return result


def apply_verification(q: dict) -> dict:
    """
    Applique la vérification et retourne la question potentiellement corrigée.
    
    - Si correct     → retourne la question inchangée
    - Si wrong       → corrige l'answer avec la valeur SymPy + ajoute flag 'corrected'
    - Si unverifiable → retourne la question inchangée + ajoute flag 'unverified'
    """
    result = verify_question(q)

    if result["status"] == "correct":
        return {**q, "verified": True}

    elif result["status"] == "wrong":
        corrected = {**q, "answer": result["computed_answer"], "verified": True, "corrected": True}
        logger.warning(
            f"Question corrigée automatiquement : "
            f"'{q['answer']}' → '{result['computed_answer']}'"
        )
        return corrected

    else:  # unverifiable
        return {**q, "verified": False, "unverified_reason": result.get("reason", "")}


# ─── TESTS UNITAIRES RAPIDES ─────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s | %(message)s")

    test_cases = [
        # ✅ Trigonométrie correcte
        {
            "question": "Quelle est la valeur de cos(π/3) ?",
            "options": ["1/2", "sqrt(3)/2", "0", "1"],
            "answer": "1/2"
        },
        # ❌ Trigonométrie fausse (Mistral hallucine)
        {
            "question": "Quelle est la valeur de cos(π/2) ?",
            "options": ["0", "1", "-1", "1/2"],
            "answer": "1"  # ← faux, doit être corrigé en "0"
        },
        # ✅ Dérivée correcte
        {
            "question": "Quelle est la dérivée de f(x) = x**2 + 3*x ?",
            "options": ["2*x + 3", "x**2", "2*x", "3*x"],
            "answer": "2*x + 3"
        },
        # ✅ Fraction correcte
        {
            "question": "Simplifiez la fraction 6/8.",
            "options": ["3/4", "2/3", "1/2", "4/6"],
            "answer": "3/4"
        },
    ]

    print("\n" + "═" * 60)
    print("  TESTS UNITAIRES — verifier.py")
    print("═" * 60)

    for i, q in enumerate(test_cases, 1):
        print(f"\nTest {i} : {q['question']}")
        result = apply_verification(q)
        corrected = result.get("corrected", False)
        verified  = result.get("verified", False)

        if corrected:
            print(f"  ⚠  CORRIGÉE → nouvelle answer : '{result['answer']}'")
        elif verified:
            print(f"  ✅ VALIDÉE  → answer : '{result['answer']}'")
        else:
            print(f"  🔵 NON VÉRIFIABLE → {result.get('unverified_reason', '')}")

    print("\n" + "═" * 60 + "\n")
