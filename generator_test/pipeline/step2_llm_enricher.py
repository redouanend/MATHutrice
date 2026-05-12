"""
ÉTAPE 2 — Enrichissement LLM des métadonnées
=============================================
Pour chaque chunk atomique, appelle Claude pour générer :
  - concept         : notion mathématique précise
  - difficulte      : 1 (très facile) → 5 (très difficile)
  - type_exercice   : simplification | calcul | demonstration | qcm | application
  - prerequis       : liste des notions requises
  - lacunes_type    : types d'erreurs fréquentes associées

Ce travail est fait UNE SEULE FOIS à l'indexation.
Les chunks enrichis sont prêts pour la vectorisation.

Sortie : output/chunks_enrichis.json
"""

import json
import time
import re
import urllib.request
import urllib.error
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
OUT_DIR = _THIS_DIR.parent / "rag" / "output"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Prompt système d'enrichissement ────────────────────
SYSTEM_PROMPT = """Tu es un expert en pédagogie mathématique pour étudiants de L1.
Analyse une question mathématique et retourne UNIQUEMENT un objet JSON valide,
sans aucun texte avant ou après, sans backticks, sans markdown.

Le JSON doit avoir exactement ces clés :
{
  "concept": "string — notion mathématique précise (ex: 'fractions algébriques', 'puissances entières négatives')",
  "difficulte": integer entre 1 et 5,
  "type_exercice": "simplification | calcul | demonstration | qcm | application | identite",
  "prerequis": ["liste", "de", "notions", "requises"],
  "lacunes_type": ["types d'erreurs fréquentes chez les L1"],
  "description_courte": "string — une phrase résumant ce que l'étudiant doit faire"
}

Barème de difficulté :
1 = calcul numérique direct, fractions simples
2 = application directe d'une règle, exposants entiers
3 = combinaison de 2-3 règles, fractions algébriques simples
4 = imbrication de plusieurs notions, fractions complexes, radicaux
5 = démonstration, déduction, généralisation avec paramètres"""


def call_llm(chunk_text: str, has_image: bool = False) -> dict | None:
    """
    Appelle l'API Anthropic pour enrichir un chunk.
    Retourne le JSON parsé ou None en cas d'échec.
    """
    context_note = ""
    if has_image:
        context_note = "\n[Note: cette question contient des formules complexes représentées en image]"

    user_msg = f"""Analyse cette question mathématique de niveau L1 :

---
{chunk_text[:1200]}{context_note}
---

Retourne le JSON d'analyse pédagogique."""

    payload = json.dumps({
        "model"      : "claude-sonnet-4-20250514",
        "max_tokens" : 400,
        "system"     : SYSTEM_PROMPT,
        "messages"   : [{"role": "user", "content": user_msg}]
    }).encode('utf-8')

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data    = payload,
        headers = {
            "Content-Type"     : "application/json",
            "anthropic-version": "2023-06-01",
        },
        method = "POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            raw  = data['content'][0]['text'].strip()
            # Nettoyer les éventuels backticks résiduels
            raw  = re.sub(r'^```json?\s*', '', raw)
            raw  = re.sub(r'\s*```$',      '', raw)
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"    ✗ HTTP {e.code}: {body[:120]}")
        return None
    except Exception as e:
        print(f"    ✗ Erreur: {e}")
        return None


def enrich_chunks(chunks: list, delay: float = 0.3) -> list:
    """
    Enrichit chaque chunk avec les métadonnées LLM.
    delay = pause entre les appels (respect rate limit).
    """
    enriched = []
    total    = len(chunks)

    print(f"\n  Enrichissement de {total} chunks...\n")

    for i, chunk in enumerate(chunks):
        cid = chunk['id']
        txt = chunk['text']

        # Skip si déjà enrichi (idempotence)
        if chunk['metadata'].get('llm_enriched'):
            print(f"  [{i+1:2d}/{total}] {cid:35s} ↩ déjà enrichi")
            enriched.append(chunk)
            continue

        # Skip les chunks trop courts (en-têtes, intro)
        if len(txt.strip()) < 30:
            chunk['metadata']['concept']       = 'introduction'
            chunk['metadata']['difficulte']    = 0
            chunk['metadata']['type_exercice'] = 'intro'
            chunk['metadata']['llm_enriched']  = True
            enriched.append(chunk)
            continue

        print(f"  [{i+1:2d}/{total}] {cid:35s} ", end='', flush=True)
        t0  = time.perf_counter()
        res = call_llm(txt, has_image=bool(chunk.get('formula_images')))
        dt  = time.perf_counter() - t0

        if res:
            # Injecter dans les métadonnées
            chunk['metadata']['concept']           = res.get('concept',          'algèbre')
            chunk['metadata']['difficulte']        = res.get('difficulte',       2)
            chunk['metadata']['type_exercice']     = res.get('type_exercice',    'calcul')
            chunk['metadata']['prerequis']         = res.get('prerequis',        [])
            chunk['metadata']['lacunes_type']      = res.get('lacunes_type',     [])
            chunk['metadata']['description_courte']= res.get('description_courte', '')
            chunk['metadata']['llm_enriched']      = True
            diff = chunk['metadata']['difficulte']
            stars = '★' * diff + '☆' * (5 - diff)
            print(f"✓ [{stars}] {chunk['metadata']['concept'][:40]}  ({dt:.1f}s)")
        else:
            # Fallback si l'API est indisponible
            chunk['metadata']['concept']       = _fallback_concept(txt)
            chunk['metadata']['difficulte']    = _fallback_difficulty(txt)
            chunk['metadata']['type_exercice'] = _fallback_type(txt)
            chunk['metadata']['prerequis']     = _fallback_prereqs(txt)
            chunk['metadata']['lacunes_type']  = []
            chunk['metadata']['llm_enriched']  = False   # marqué comme non-enrichi
            print(f"⚠ fallback heuristique")

        enriched.append(chunk)
        if delay > 0 and i < total - 1:
            time.sleep(delay)

    return enriched


# ── Heuristiques de fallback (si API indisponible) ─────

def _fallback_concept(text: str) -> str:
    t = text.lower()
    if re.search(r'\\frac|fraction|\/', t):        return 'fractions'
    if re.search(r'puissance|exposant|\^|3\^',t):  return 'puissances'
    if re.search(r'√|racine|radical|sqrt',   t):   return 'radicaux'
    if re.search(r'simplif',                  t):  return 'simplification_algébrique'
    if re.search(r'qcm|unique|cocher',        t):  return 'qcm_algèbre'
    return 'calcul_algébrique'


def _fallback_difficulty(text: str) -> int:
    score = 1
    if re.search(r'\\frac\{[^}]+\\frac', text): score += 2   # frac imbriqué
    elif re.search(r'\\frac',             text): score += 1   # frac simple
    if re.search(r'[ⁿ𝑛𝑘]',               text): score += 1   # paramètre général
    if re.search(r'√|\\sqrt',             text): score += 1   # radical
    if re.search(r'déduire|montrer|démontrer', text.lower()): score += 1
    return min(score, 5)


def _fallback_type(text: str) -> str:
    t = text.lower()
    if re.search(r'qcm|unique|cocher|bonne\s+réponse', t): return 'qcm'
    if re.search(r'simplif|réduire',                   t): return 'simplification'
    if re.search(r'montrer|démontrer|justif',           t): return 'demonstration'
    if re.search(r'calculer|que\s+vaut|valeur',         t): return 'calcul'
    if re.search(r'exprimer|écrire|mettre\s+sous',      t): return 'application'
    return 'calcul'


def _fallback_prereqs(text: str) -> list:
    prereqs = []
    t = text.lower()
    if re.search(r'fraction|\\frac', t):   prereqs.append('fractions')
    if re.search(r'exposant|\^|puissance', t): prereqs.append('puissances')
    if re.search(r'√|racine|radical', t):  prereqs.append('radicaux')
    if re.search(r'algèbre|factori|développ', t): prereqs.append('algèbre_de_base')
    return prereqs


# ══════════════════════════════════════════════════════
# PIPELINE PRINCIPAL
# ══════════════════════════════════════════════════════

def run(chunks_path: str = None, delay: float = 0.3):
    if chunks_path is None:
        chunks_path = OUT_DIR / 'chunks_atomiques.json'

    print("=" * 60)
    print("  ÉTAPE 2 — Enrichissement LLM des métadonnées")
    print("=" * 60)

    with open(chunks_path, 'r', encoding='utf-8') as f:
        chunks = json.load(f)

    t0      = time.perf_counter()
    chunks  = enrich_chunks(chunks, delay=delay)
    elapsed = time.perf_counter() - t0

    # Stats
    llm_ok   = sum(1 for c in chunks if c['metadata'].get('llm_enriched'))
    fallback = len(chunks) - llm_ok
    diffs    = [c['metadata']['difficulte'] for c in chunks
                if c['metadata'].get('difficulte')]

    out = OUT_DIR / 'chunks_enrichis.json'
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 60}")
    print(f"  Temps total          : {elapsed:.1f}s")
    print(f"  Chunks enrichis LLM  : {llm_ok}/{len(chunks)}")
    print(f"  Chunks fallback      : {fallback}/{len(chunks)}")
    if diffs:
        avg = sum(diffs) / len(diffs)
        print(f"  Difficulté moyenne   : {avg:.1f}/5")
    print(f"  Sauvegardé           : {out}")
    print(f"{'=' * 60}")

    # Aperçu
    print(f"\n  APERÇU DES CHUNKS ENRICHIS :")
    for c in chunks[:20]:
        m    = c['metadata']
        diff = m.get('difficulte', 0)
        stars= ('★' * diff + '☆' * (5-diff)) if isinstance(diff, int) else '?'
        src  = '✓LLM' if m.get('llm_enriched') else '~heur'
        print(f"  {src} [{stars}] {c['id']:30s} "
              f"| {str(m.get('concept',''))[:30]:30s} "
              f"| {m.get('type_exercice',''):15s}")

    return chunks


if __name__ == '__main__':
    run()
