"""
run_pipeline_batch.py — Pipeline batch pour l'arborescence réelle
==================================================================
Gère la structure :

  dataset/
  ├── Logarithme et exponentielle/
  │   ├── Bases_exponentielle et logarithme.pdf   ← niveau dans le nom
  │   ├── Expert_exponentielle et logarithme.pdf
  │   ├── Solide_exponentielle et logarithme.pdf
  │   └── Cours/                                  ← cours magistral
  │       └── intro_log.pdf
  └── Trigonométrie/
      ├── Astuces de calculs-.pdf                 ← cours (pas de niveau)
      ├── Base/                                   ← sous-dossier niveau
      │   └── exo_cercle.pdf
      ├── Solide/
      └── Expert/

Règles de détection :
  - Notion  → nom du sous-dossier direct de dataset/
  - Niveau  → 1) sous-dossier (Base/Solide/Expert)
              2) préfixe du nom de fichier (Bases_/Solide_/Expert_)
              3) si aucun → doc de cours (type='cours')
  - Cours   → dossier nommé "Cours" ou fichier sans niveau détecté

Usage :
  python run_pipeline_batch.py --dataset ./dataset
  python run_pipeline_batch.py --dataset ./dataset --no-llm
  python run_pipeline_batch.py --dataset ./dataset --force
"""

import sys
import re
import json
import time
import pickle
import logging
import argparse
from pathlib import Path
from datetime import datetime
from collections import Counter

# ── Chemins
_PROJECT_ROOT = Path(__file__).resolve().parent
_RAG_DIR      = _PROJECT_ROOT / "rag"
sys.path.insert(0, str(_RAG_DIR))

from taxonomy import (
    detect_notion, estimate_difficulty, diff_to_niveau,
    detect_type, get_prereqs, validate_metadata,
    NOTIONS, NIVEAUX, NIVEAU_TO_DIFF
)

logging.basicConfig(level=logging.WARNING, format="%(levelname)s | %(message)s")

# ── Config
DEFAULT_DATASET = _PROJECT_ROOT / "dataset"
OUT_DIR         = _RAG_DIR / "output"
STORE_PATH      = OUT_DIR / "vectorstore.pkl"
REGISTRY_PATH   = OUT_DIR / "processed_pdfs.json"


# ══════════════════════════════════════════════════════
# DÉTECTION NOTION + NIVEAU depuis l'arborescence
# ══════════════════════════════════════════════════════

def _norm(s: str) -> str:
    """Normalise une chaîne : minuscules + suppression accents."""
    t = s.lower()
    for src, dst in [
        ('é','e'),('è','e'),('ê','e'),('à','a'),('â','a'),
        ('ô','o'),('î','i'),('ù','u'),('û','u'),('ç','c'),
        ("'", " "),("'", " "),
    ]:
        t = t.replace(src, dst)
    return re.sub(r'\s+', ' ', t).strip()


# Mapping noms de dossiers de notions → notion officielle
FOLDER_TO_NOTION = {
    "fraction - puissance - radicaux"           : "fractions_puissances_radicaux",
    "fraction puissance radicaux"               : "fractions_puissances_radicaux",
    "fractions"                                 : "fractions_puissances_radicaux",
    "fractions - puissances - radicaux"         : "fractions_puissances_radicaux",
    "logarithme et exponentielle"               : "logarithme_exponentielle",
    "logarithme"                                : "logarithme_exponentielle",
    "log et exp"                                : "logarithme_exponentielle",
    "manipulation d expression litterale"       : "expressions_littérales",
    "manipulation d'expression litterale"       : "expressions_littérales",
    "manipulation des expressions litterales"   : "expressions_littérales",
    "expressions litterales"                    : "expressions_littérales",
    "expressions littérales"                    : "expressions_littérales",
    "polynomes + factorisation"                 : "polynômes_factorisation",
    "polynomes factorisation"                   : "polynômes_factorisation",
    "polynomes et factorisation"                : "polynômes_factorisation",
    "polynômes + factorisation"                 : "polynômes_factorisation",
    "resolution d equations et d inequations"   : "équations_inéquations",
    "resolution d equat et d inequat"           : "équations_inéquations",
    "equations et inequations"                  : "équations_inéquations",
    "equations inequations"                     : "équations_inéquations",
    "resolution d equations et inequations"     : "équations_inéquations",
    "trigonometrie"                             : "trigonométrie",
    "trigonométrie"                             : "trigonométrie",
    "analyse dimensionnelle"                    : "analyse_dimensionnelle",
}

# Mapping noms de sous-dossiers → niveau
FOLDER_TO_NIVEAU = {
    "base"          : "débutant",
    "bases"         : "débutant",
    "debutant"      : "débutant",
    "débutant"      : "débutant",
    "solide"        : "intermédiaire",
    "intermediaire" : "intermédiaire",
    "intermédiaire" : "intermédiaire",
    "moyen"         : "intermédiaire",
    "expert"        : "avancé",
    "avance"        : "avancé",
    "avancé"        : "avancé",
    "difficile"     : "avancé",
}

# Niveaux détectables dans les noms de fichiers
FILE_NIVEAU_RE = [
    (r'(?i)^bases?[_\s-]',        "débutant"),
    (r'(?i)[_\s-]bases?[_\s-]',   "débutant"),
    (r'(?i)^debutant[_\s-]',      "débutant"),
    (r'(?i)^solide[_\s-]',        "intermédiaire"),
    (r'(?i)[_\s-]solide[_\s-]',   "intermédiaire"),
    (r'(?i)^expert[_\s-]',        "avancé"),
    (r'(?i)[_\s-]expert[_\s-]',   "avancé"),
    (r'(?i)^avance[_\s-]',        "avancé"),
    # Suffixes
    (r'(?i)[_\s-]bases?$',        "débutant"),
    (r'(?i)[_\s-]solide$',        "intermédiaire"),
    (r'(?i)[_\s-]expert$',        "avancé"),
    # Mots seuls dans le nom
    (r'(?i)\bbase\b',             "débutant"),
    (r'(?i)\bsolide\b',           "intermédiaire"),
    (r'(?i)\bexpert\b',           "avancé"),
]

# Noms de dossiers/fichiers indiquant un cours (pas d'exercices)
COURS_KEYWORDS = re.compile(
    r'(?i)^(cours|rappels?|fiche|astuces?|introduction|intro|'
    r'resume|résumé|synthese|synthèse|notes?|memo|memento|formules?)$'
)


def analyze_pdf_path(pdf_path: Path, dataset_root: Path) -> dict:
    """
    Analyse le chemin d'un PDF dans l'arborescence et retourne :
      - notion    : notion officielle
      - niveau    : débutant / intermédiaire / avancé / None
      - doc_type  : 'exercices' ou 'cours'
    """
    try:
        # Chemin relatif depuis dataset/
        rel = pdf_path.relative_to(dataset_root)
        parts = rel.parts  # ex: ('Trigonométrie', 'Base', 'exo.pdf')
    except ValueError:
        parts = pdf_path.parts

    # ── Notion : 1er dossier sous dataset/
    notion = None
    if len(parts) >= 1:
        notion_folder = parts[0]
        notion = FOLDER_TO_NOTION.get(_norm(notion_folder))
        # Fallback : chercher dans la notion officielle la plus proche
        if not notion:
            for key, val in FOLDER_TO_NOTION.items():
                if key in _norm(notion_folder) or _norm(notion_folder) in key:
                    notion = val
                    break

    # ── Type de document : cours ou exercices
    doc_type = "exercices"
    for part in parts[1:]:
        stem = Path(part).stem if '.' in part else part
        if COURS_KEYWORDS.match(_norm(stem)):
            doc_type = "cours"
            break

    # ── Niveau : chercher dans les dossiers intermédiaires (hors notion et fichier)
    niveau = None
    for part in parts[1:-1]:  # Exclure le dossier notion et le fichier
        n = FOLDER_TO_NIVEAU.get(_norm(part))
        if n:
            niveau = n
            break

    # ── Si pas dans les dossiers → chercher dans le nom du fichier
    if not niveau:
        filename_stem = pdf_path.stem + " "  # espace pour les regex de suffixe
        for pattern, niv in FILE_NIVEAU_RE:
            if re.search(pattern, filename_stem):
                niveau = niv
                break

    # ── Si toujours pas de niveau → cours ou document non classifié
    if not niveau:
        doc_type = "cours"

    return {
        "notion"    : notion or "non_identifiée",
        "niveau"    : niveau,
        "doc_type"  : doc_type,
    }


# ══════════════════════════════════════════════════════
# TRAITEMENT D'UN PDF
# ══════════════════════════════════════════════════════

def process_pdf(pdf_path: Path, dataset_root: Path,
                out_dir: Path, use_llm: bool) -> list[dict]:
    """
    Traite un PDF et retourne ses chunks enrichis avec
    notion, niveau et doc_type issus de l'arborescence.
    """
    from step1_docling_chunker import run as run_step1
    from step2_llm_enricher import enrich_chunks
    from step2_llm_enricher import (
        _fallback_concept, _fallback_difficulty,
        _fallback_type, _fallback_prereqs
    )

    # ── Métadonnées depuis l'arborescence (source de vérité)
    path_meta = analyze_pdf_path(pdf_path, dataset_root)
    notion    = path_meta["notion"]
    niveau    = path_meta["niveau"]
    doc_type  = path_meta["doc_type"]

    # ── Chunking atomique
    # Passer la notion et le doc_type depuis l'arborescence
    chunks = run_step1(str(pdf_path), notion_override=notion, doc_type=doc_type)

    # ── Enrichissement LLM ou heuristiques
    if use_llm:
        chunks = enrich_chunks(chunks, delay=0.3)
    else:
        for c in chunks:
            txt = c["text"]
            c["metadata"]["concept"]       = _fallback_concept(txt)
            c["metadata"]["type_exercice"] = _fallback_type(txt)
            c["metadata"]["prerequis"]     = _fallback_prereqs(txt)
            c["metadata"]["llm_enriched"]  = False

    # ── Injecter les métadonnées de l'arborescence dans chaque chunk
    diff_default = NIVEAU_TO_DIFF.get(niveau, 3) if niveau else None

    for c in chunks:
        m = c["metadata"]

        # Notion depuis l'arborescence (priorité sur détection contenu)
        m["notion"]    = notion

        # Type de document
        m["doc_type"]  = doc_type

        # Source
        m["pdf_source"]   = pdf_path.name
        m["pdf_path"]     = str(pdf_path)
        m["pdf_rel_path"] = str(pdf_path.relative_to(dataset_root))

        # Niveau : depuis l'arborescence si disponible
        # sinon estimé par contenu (déjà calculé dans step1)
        if niveau:
            m["niveau"] = niveau
            # Difficulté : conserver celle de step1 si cohérente avec le niveau,
            # sinon ajuster pour rester dans la plage du niveau
            diff_step1 = m.get("difficulte", 0) or 0
            diff_range = {
                "débutant"      : (1, 2),
                "intermédiaire" : (2, 4),
                "avancé"        : (3, 5),
            }.get(niveau, (1, 5))
            # Si step1 est hors plage → utiliser la valeur par défaut du niveau
            if not (diff_range[0] <= diff_step1 <= diff_range[1]):
                m["difficulte"] = diff_default
            m["niveau"] = diff_to_niveau(m["difficulte"])
        # Si pas de niveau (cours) → garder estimation contenu

        c["metadata"] = validate_metadata(m)

    return chunks


# ══════════════════════════════════════════════════════
# REGISTRE (reprise après interruption)
# ══════════════════════════════════════════════════════

def load_registry(path: Path) -> dict:
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_registry(registry: dict, path: Path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)

def pdf_fingerprint(p: Path) -> str:
    s = p.stat()
    return f"{p.name}_{s.st_size}_{int(s.st_mtime)}"


# ══════════════════════════════════════════════════════
# PIPELINE BATCH PRINCIPAL
# ══════════════════════════════════════════════════════

def run_batch(dataset_dir: Path = DEFAULT_DATASET,
              use_llm: bool = True,
              resume: bool = True,
              force: bool = False):

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "chunks_by_pdf").mkdir(exist_ok=True)

    # ── Trouver tous les PDFs récursivement
    pdf_files = sorted(dataset_dir.rglob("*.pdf"))
    if not pdf_files:
        print(f"\n  ❌ Aucun PDF trouvé dans : {dataset_dir.resolve()}")
        return

    print("\n" + "═" * 65)
    print(f"  📁  PIPELINE BATCH — {len(pdf_files)} PDF(s)")
    print(f"  Dataset : {dataset_dir.resolve()}")
    print(f"  LLM     : {'oui' if use_llm else 'non (heuristiques)'}")
    print("═" * 65)

    # ── Pré-visualisation de la structure détectée
    print("\n  Structure détectée :")
    notion_counts = Counter()
    niveau_counts = Counter()
    type_counts   = Counter()
    for pdf in pdf_files:
        m = analyze_pdf_path(pdf, dataset_dir)
        notion_counts[m["notion"]] += 1
        niveau_counts[str(m["niveau"])] += 1
        type_counts[m["doc_type"]] += 1
    for notion, n in notion_counts.most_common():
        print(f"    {notion:40s} : {n} PDF(s)")
    print(f"\n  Niveaux  : {dict(niveau_counts)}")
    print(f"  Types    : {dict(type_counts)}")
    print()

    # ── Charger ou créer le store ChromaDB ──────────────────
    from step3_vectorstore import ChromaVectorStore, CHROMA_DIR
    chroma_path = CHROMA_DIR

    if chroma_path.exists() and any(chroma_path.iterdir()) and resume and not force:
        print("  Chargement du vectorstore ChromaDB existant...")
        store = ChromaVectorStore.load(chroma_dir=chroma_path)
    else:
        print("  Création d'un nouveau vectorstore ChromaDB...")
        print("  Embedder : Solon FR (OrdalieTech) — sémantique académique")
        store = ChromaVectorStore(chroma_dir=chroma_path)

    registry = load_registry(REGISTRY_PATH) if resume else {}

    # ── Résultats
    results = {"total": len(pdf_files), "ok": 0, "skip": 0, "err": 0,
               "chunks": 0, "pdfs": []}
    t_total = time.perf_counter()

    # ── Traiter chaque PDF
    for i, pdf_path in enumerate(pdf_files, 1):
        fp = pdf_fingerprint(pdf_path)
        path_meta = analyze_pdf_path(pdf_path, dataset_dir)
        rel_path  = str(pdf_path.relative_to(dataset_dir))

        # Skip si déjà traité
        if resume and not force and fp in registry:
            print(f"  [{i:2d}/{len(pdf_files)}] ↩ {rel_path}")
            results["skip"] += 1
            continue

        niveau_str = path_meta["niveau"] or "—"
        print(f"\n  [{i:2d}/{len(pdf_files)}] 📄 {rel_path}")
        print(f"     notion   : {path_meta['notion']}")
        print(f"     niveau   : {niveau_str}  |  type : {path_meta['doc_type']}")

        t_pdf = time.perf_counter()
        try:
            chunks = process_pdf(pdf_path, dataset_dir, OUT_DIR, use_llm)

            # Sauvegarder les chunks de ce PDF
            safe_name = re.sub(r'[^\w\-.]', '_', pdf_path.stem)
            chunk_out = OUT_DIR / "chunks_by_pdf" / f"{safe_name}_chunks.json"
            with open(chunk_out, "w", encoding="utf-8") as f:
                json.dump(chunks, f, ensure_ascii=False, indent=2)

            store.add(chunks)
            dt = time.perf_counter() - t_pdf

            registry[fp] = {
                "pdf"          : rel_path,
                "notion"       : path_meta["notion"],
                "niveau"       : niveau_str,
                "doc_type"     : path_meta["doc_type"],
                "chunks"       : len(chunks),
                "processed_at" : datetime.now().isoformat(),
            }

            results["ok"]     += 1
            results["chunks"] += len(chunks)
            results["pdfs"].append({
                "rel_path": rel_path,
                "notion"  : path_meta["notion"],
                "niveau"  : niveau_str,
                "doc_type": path_meta["doc_type"],
                "chunks"  : len(chunks),
                "temps"   : f"{dt:.1f}s",
            })

            # Afficher distribution difficulté pour ce PDF
            diffs = Counter(c["metadata"]["difficulte"] for c in chunks
                            if c["metadata"].get("difficulte"))
            diff_str = " | ".join(f"diff{d}:×{n}" for d,n in sorted(diffs.items()))
            print(f"     ✓ {len(chunks)} chunks  [{diff_str}]  {dt:.1f}s")

        except Exception as e:
            import traceback
            print(f"     ✗ ERREUR : {e}")
            print(f"     Traceback complet :")
            traceback.print_exc()
            results["err"] += 1
            continue

        # Sauvegarde intermédiaire
        store.save()  # ChromaDB : persistance automatique
        save_registry(registry, REGISTRY_PATH)

    # ── Sauvegarde finale
    store.save()  # ChromaDB : persistance automatique
    save_registry(registry, REGISTRY_PATH)
    with open(OUT_DIR / "chunks_all.json", "w", encoding="utf-8") as f:
        json.dump(store.chunks, f, ensure_ascii=False, indent=2)

    elapsed = time.perf_counter() - t_total

    # ── Rapport final
    print(f"\n{'═' * 65}")
    print(f"  📊  RAPPORT FINAL")
    print(f"{'═' * 65}")
    print(f"  ⏱  Temps total          : {elapsed:.1f}s")
    print(f"  📄  PDFs traités         : {results['ok']}/{results['total']}")
    print(f"  ↩  Skippés              : {results['skip']}")
    print(f"  ✗  Erreurs              : {results['err']}")
    print(f"  📦  Chunks totaux store  : {len(store)}")
    print(f"  📦  Chunks ajoutés       : {results['chunks']}")

    print(f"\n  Détail par notion :")
    by_notion = Counter(p["notion"] for p in results["pdfs"])
    for notion, n in by_notion.most_common():
        chunks_n = sum(p["chunks"] for p in results["pdfs"] if p["notion"]==notion)
        print(f"    {notion:40s} : {n} PDF(s)  {chunks_n} chunks")

    print(f"\n  Détail par PDF :")
    for p in results["pdfs"]:
        print(f"    {p['rel_path']:55s} {p['chunks']:3d} chunks  "
              f"[{p['niveau']:15s}]  {p['temps']}")

    print(f"\n  Fichiers générés :")
    for fp2 in [STORE_PATH, REGISTRY_PATH, OUT_DIR/"chunks_all.json"]:
        if fp2.exists():
            print(f"    ✓ {fp2.name}  ({fp2.stat().st_size//1024} KB)")

    print(f"{'═' * 65}\n")
    return store


# ══════════════════════════════════════════════════════
# ARGPARSE
# ══════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Pipeline batch — indexe l'arborescence dataset/"
    )
    parser.add_argument(
        "--dataset", type=Path, default=DEFAULT_DATASET,
        help=f"Dossier dataset racine (défaut: {DEFAULT_DATASET})"
    )
    parser.add_argument("--no-llm",  action="store_true",
                        help="Heuristiques au lieu du LLM")
    parser.add_argument("--force",   action="store_true",
                        help="Retraiter tous les PDFs")
    parser.add_argument("--no-resume", action="store_true",
                        help="Ne pas reprendre depuis le registre")
    args = parser.parse_args()

    run_batch(
        dataset_dir = args.dataset,
        use_llm     = not args.no_llm,
        resume      = not args.no_resume,
        force       = args.force,
    )
