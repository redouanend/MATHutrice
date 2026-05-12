"""
taxonomy.py — Détection de notion et difficulté PAR CONTENU
============================================================
Principe :
  - La notion est détectée depuis le texte du document
  - La difficulté est estimée EXERCICE PAR EXERCICE
  - Pas d'inférence depuis le nom du fichier
  - Un même PDF peut avoir des exercices de niveaux différents
"""

import re

# ══════════════════════════════════════════════════════
# CONSTANTES OFFICIELLES
# ══════════════════════════════════════════════════════

NOTIONS = [
    "trigonométrie",
    "analyse_dimensionnelle",
    "fractions_puissances_radicaux",
    "logarithme_exponentielle",
    "expressions_littérales",
    "polynômes_factorisation",
    "équations_inéquations",
]

NIVEAUX = ["débutant", "intermédiaire", "avancé"]

NIVEAU_TO_DIFF = {"débutant": 1, "intermédiaire": 3, "avancé": 5}
DIFF_TO_NIVEAU = {1:"débutant",2:"débutant",3:"intermédiaire",4:"avancé",5:"avancé"}


def _clean(text):
    t = text.lower()
    # Remplacement lettre par lettre avec replace (évite les erreurs de longueur)
    replacements = [
        ('à','a'),('á','a'),('â','a'),('ä','a'),('æ','ae'),
        ('è','e'),('é','e'),('ê','e'),('ë','e'),
        ('î','i'),('ï','i'),('í','i'),
        ('ô','o'),('ö','o'),('ò','o'),
        ('ù','u'),('ú','u'),('û','u'),('ü','u'),
        ('ç','c'),('ć','c'),('ł','l'),
        ('ñ','n'),('ń','n'),
        ('ś','s'),('š','s'),
        ('ž','z'),('ź','z'),
    ]
    for src, dst in replacements:
        t = t.replace(src, dst)
    return t


# ══════════════════════════════════════════════════════
# DÉTECTION DE NOTION DEPUIS LE CONTENU
# ══════════════════════════════════════════════════════

_NOTION_PATTERNS = {
    "trigonométrie": [
        (3, [r'\bcos\b', r'\bsin\b', r'\btan\b', r'arccos', r'arcsin', r'arctan',
             r'cercle trigon', r'radian', r'lineariser', r'linéariser',
             r'formule.*addition', r'formule.*duplication', r'euler',
             r'sin\(', r'cos\(', r'tan\(']),
        (2, [r'trigonometri', r'trigonométri', r'sinusoide', r'angle', r'cercle unitaire']),
        (1, [r'periodique', r'amplitude']),
    ],
    "analyse_dimensionnelle": [
        (3, [r'analyse dimensionnelle', r'homogeneite', r'homogénéité', r'grandeur physique',
             r'unite.*SI', r'unité.*SI', r'\bSI\b', r'metres?', r'kilogrammes?']),
        (2, [r'dimension\b', r'vecteur vitesse', r'acceleration', r'force\b', r'energie']),
        (1, [r'physique', r'mecanique']),
    ],
    "fractions_puissances_radicaux": [
        (3, [r'fraction', r'numerateur', r'numérateur', r'denominateur', r'dénominateur',
             r'irreductible', r'irréductible', r'pgcd', r'racine carree', r'racine carrée',
             r'exposant', r'puissance', r'simplifier.*fraction', r'radicaux', r'\\frac']),
        (2, [r'quotient', r'diviser']),
        (1, [r'simplifier', r'réduire']),
    ],
    "logarithme_exponentielle": [
        (3, [r'\blog\b', r'\bln\b', r'logarithme', r'exponentielle', r'e\^',
             r'nepérien', r'neperien', r'base.*10', r'log.*base', r'croissance exponentielle']),
        (2, [r'fonction.*log', r'primitive.*exp', r'dérivée.*exp']),
        (1, [r'croissance', r'asymptote']),
    ],
    "expressions_littérales": [
        (3, [r'developper', r'développer', r'identite remarquable', r'identité remarquable',
             r'double distributivite', r'double distributivité',
             r'\(a\+b\)', r'a\^2.*b\^2', r'expression litterale', r'expression littérale']),
        (2, [r'distributivite', r'distributivité', r'developp', r'factoris.*expression']),
        (1, [r'simplifier.*expression', r'calculer.*lettre']),
    ],
    "polynômes_factorisation": [
        (3, [r'polynome', r'polynôme', r'discriminant', r'\bdelta\b', r'Δ',
             r'forme canonique', r'monome', r'monôme', r'trinome', r'trinôme',
             r'coefficient.*x\^', r'degre.*polynome']),
        (2, [r'factoriser', r'degre 2', r'degré 2', r'ax\^2', r'ax²']),
        (1, [r'racines?.*equation', r'solutions?.*polynome']),
    ],
    "équations_inéquations": [
        (3, [r'resoudre', r'résoudre', r'ensemble.*solution', r'S\s*=\s*[{\[]',
             r'inequation', r'inéquation', r'systeme.*equation', r'système.*équation',
             r'resolution\b', r'résolution\b']),
        (2, [r'equation\b', r'équation\b', r'inconnue', r'valeur.*de.*x']),
        (1, [r'egal', r'égal', r'superieur', r'inférieur']),
    ],
}


def detect_notion(text: str, full_doc_text: str = "") -> str:
    """Détecte la notion depuis le contenu. Utilise full_doc_text en appoint."""
    search = _clean(text + " " + full_doc_text[:600])
    scores = {n: 0 for n in NOTIONS}
    for notion, levels in _NOTION_PATTERNS.items():
        for weight, patterns in levels:
            for p in patterns:
                if re.search(_clean(p), search):
                    scores[notion] += weight
    best       = max(scores, key=lambda k: scores[k])
    best_score = scores[best]
    if best_score < 2:
        return "non_identifiée"
    return best


# ══════════════════════════════════════════════════════
# ESTIMATION DE DIFFICULTÉ PAR EXERCICE (1-5)
# ══════════════════════════════════════════════════════

_EASY_PATTERNS = [
    r'(?i)définition\b',
    r'(?i)compléter le tableau',
    r'(?i)remplir le tableau',
    r'(?i)placer.*cercle',
    r'(?i)donner la valeur',
    r'(?i)calculer\s+\w+\s*=\s*\d',
    r'(?i)valeur de (sin|cos|tan)\s*\(',
]

_MEDIUM_PATTERNS = [
    r'(?i)simplifier',
    r'(?i)résoudre.*\[',
    r'(?i)vérifier que',
    r'(?i)retrouver',      # +1 (max score = 3 sans hard patterns)
    r'(?i)déduire',        # +1
    r'(?i)formule\b',
    r'(?i)factoriser',
    r'(?i)développer',
]

# Plafond : sans hard patterns, le score medium ne peut pas dépasser 3
_MAX_SCORE_WITHOUT_HARD = 3

_HARD_PATTERNS = [
    r'(?i)pour tout|∀|quel que soit',
    r'(?i)démontrer\s+(que|par)',
    r'(?i)généraliser',
    r'n\s*∈\s*ℕ\*?|k\s*∈\s*ℕ',
    r'(?i)si et seulement si',
    r'(?i)par récurrence',
    r'(?i)cos\^n|sin\^n|cos[ⁿn]\(|cosn\(',
    r'√cos|√sin|racine.*cos|racine.*sin',
    r'(?i)résoudre.*dans\s*ℝ\b',
    r'(?i)linéariser\s+\w+\^[3-9n]',
    r'∑|∏|∫|∀|∃',
]

_NOTION_DIFF_BONUS = {
    "trigonométrie"             : 1,
    "logarithme_exponentielle"  : 1,
    "analyse_dimensionnelle"    : 0,
    "fractions_puissances_radicaux": 0,
    "expressions_littérales"    : 0,
    "polynômes_factorisation"   : 0,
    "équations_inéquations"     : 0,
}


def estimate_difficulty(text: str, notion: str = "") -> int:
    """
    Estime la difficulté d'un exercice de 1 à 5.
      1-2 → débutant
      3   → intermédiaire
      4-5 → avancé
    """
    score = 2  # base

    # Exercice clairement basique → forcer à 1
    easy_hits = sum(1 for p in _EASY_PATTERNS if re.search(p, text))
    # 1 hit fort suffit pour forcer débutant (ex: "définition" ou "remplir tableau")
    strong_easy = bool(re.search(r'(?i)définition\b|remplir.*tableau|compléter.*tableau|donner la définition', text))
    if easy_hits >= 1 or strong_easy:
        score = 1

    # Indicateurs médiums
    has_hard = any(re.search(p, text) for p in _HARD_PATTERNS)
    for p in _MEDIUM_PATTERNS:
        if re.search(p, text):
            score += 1

    # Plafonner à 3 si aucun indicateur hard
    if not has_hard:
        score = min(score, 3)

    # Indicateurs difficiles
    for p in _HARD_PATTERNS:
        if re.search(p, text):
            score += 2

    # Bonus notion
    score += _NOTION_DIFF_BONUS.get(notion, 0)

    return max(1, min(5, score))


def diff_to_niveau(diff: int) -> str:
    return DIFF_TO_NIVEAU.get(diff, "intermédiaire")


# ══════════════════════════════════════════════════════
# TYPE D'EXERCICE
# ══════════════════════════════════════════════════════

_TYPE_PATTERNS = [
    ("qcm",            [r'(?i)une\s+unique\s+réponse', r'(?i)cocher', r'(?i)bonne\s+réponse']),
    ("démonstration",  [r'(?i)démontrer', r'(?i)montrer\s+que', r'(?i)prouver',
                        r'(?i)vérifier\s+que', r'(?i)justifier\s+que']),
    ("application",    [r'(?i)en\s+déduire', r'(?i)utiliser\s+la\s+formule', r'(?i)appliquer']),
    ("simplification", [r'(?i)simplifier', r'(?i)réduire', r'(?i)linéariser',
                        r'(?i)factoriser', r'(?i)développer', r'(?i)exprimer\s+sous']),
    ("equation",       [r'(?i)résoudre', r'(?i)trouver\s+.{0,20}\s+x\b',
                        r'(?i)ensemble.*solution']),
    ("calcul",         [r'(?i)calculer', r'(?i)que\s+vaut', r'(?i)déterminer\s+la\s+valeur',
                        r'(?i)compléter', r'(?i)remplir']),
]


def detect_type(text: str) -> str:
    for label, patterns in _TYPE_PATTERNS:
        for p in patterns:
            if re.search(p, text):
                return label
    return "calcul"


# ══════════════════════════════════════════════════════
# PRÉREQUIS PAR NOTION
# ══════════════════════════════════════════════════════

_NOTION_PREREQS = {
    "trigonométrie"               : ["cercle_trigonométrique", "valeurs_remarquables", "radians"],
    "analyse_dimensionnelle"      : ["unités_SI", "algèbre_de_base"],
    "fractions_puissances_radicaux": ["opérations_de_base", "PGCD"],
    "logarithme_exponentielle"    : ["fonctions_de_base", "dérivées"],
    "expressions_littérales"      : ["opérations_de_base", "priorités_opératoires"],
    "polynômes_factorisation"     : ["expressions_littérales", "équations_premier_degré"],
    "équations_inéquations"       : ["expressions_littérales", "opérations_de_base"],
}


def get_prereqs(notion: str) -> list:
    return _NOTION_PREREQS.get(notion, [])


# ══════════════════════════════════════════════════════
# VALIDATION MÉTADONNÉES
# ══════════════════════════════════════════════════════

def validate_metadata(metadata: dict) -> dict:
    if metadata.get("notion") not in NOTIONS:
        metadata["notion"] = "non_identifiée"
    if not metadata.get("difficulte"):
        metadata["difficulte"] = estimate_difficulty(
            metadata.get("text_preview", ""),
            metadata.get("notion", "")
        )
    metadata["niveau"] = diff_to_niveau(metadata["difficulte"])
    return metadata


# ══════════════════════════════════════════════════════
# TEST RAPIDE
# ══════════════════════════════════════════════════════

if __name__ == "__main__":
    tests = [
        ("Calculer cos(π/8) et sin(π/8)",                          "trigonométrie",                2),
        ("Donner la définition d'un radian. Remplir le tableau.",   "trigonométrie",                1),
        ("Résoudre dans ℝ : 2sin²(x) + 3sin(x) - 2 ≥ 0",          "trigonométrie",                3),
        ("Linéariser cosⁿ(x) pour tout n ∈ ℕ",                    "trigonométrie",                5),
        ("Résoudre √cos x + √sin x = 1",                           "trigonométrie",                5),
        ("Simplifier la fraction 6/15 + 3/10",                     "fractions_puissances_radicaux",2),
        ("Résoudre l'équation 3x + 5 = 14",                        "équations_inéquations",        2),
        ("Factoriser P(x) = x² - 5x + 6. Utiliser le discriminant","polynômes_factorisation",      3),
        ("Calculer log(100) + ln(e²)",                             "logarithme_exponentielle",     2),
        ("Analyser l'homogénéité de F = m·a (SI)",                 "analyse_dimensionnelle",       3),
    ]

    print("=" * 65)
    print("  TEST TAXONOMIE — Détection par contenu")
    print("=" * 65)
    ok_n = ok_d = 0
    for text, exp_n, exp_d in tests:
        notion = detect_notion(text)
        diff   = estimate_difficulty(text, notion)
        niveau = diff_to_niveau(diff)
        n_ok = "✅" if notion == exp_n else "❌"
        d_ok = "✅" if abs(diff - exp_d) <= 1 else "⚠️ "
        if n_ok == "✅": ok_n += 1
        if d_ok == "✅": ok_d += 1
        print(f"\n  {n_ok}{d_ok} {text[:55]}")
        print(f"     notion : {notion} (attendu: {exp_n})")
        print(f"     diff   : {diff}/5 [{niveau}] (attendu: ~{exp_d})")
    print(f"\n  Notions : {ok_n}/{len(tests)} ✅")
    print(f"  Diff    : {ok_d}/{len(tests)} ✅")
    print("=" * 65)
