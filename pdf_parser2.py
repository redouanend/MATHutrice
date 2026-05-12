<<<<<<< HEAD
<<<<<<< HEAD
=======
>>>>>>> e731bbf (conversion format markdown réussi avec la librarie Marker)
import fitz
import json
import re
from pathlib import Path
from rich import print as rprint
<<<<<<< HEAD

# Nouvelle API Marker v1+
from marker.converters.pdf import PdfConverter
from marker.models import create_model_dict
from marker.output import text_from_rendered

# ─────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────

PDF_PATH = r"C:\Users\kalfa\MATHutrice-1\dataset\Bases_fractions_puiss_radicaux.pdf"
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)
(OUTPUT_DIR / "chunks").mkdir(exist_ok=True)
(OUTPUT_DIR / "images").mkdir(exist_ok=True)


# ─────────────────────────────────────────
# ÉTAPE 1 : PARSING AVEC MARKER v1+
# ─────────────────────────────────────────

def parse_with_marker(pdf_path: str):
    rprint("[bold blue]📄 Chargement des modèles Marker...[/bold blue]")
    models = create_model_dict()

    rprint("[bold blue]📄 Parsing en cours...[/bold blue]")
    converter = PdfConverter(artifact_dict=models)
    rendered = converter(pdf_path)
    full_text, _, images = text_from_rendered(rendered)

    # Sauvegarder le markdown
    md_path = OUTPUT_DIR / "document_parsed.md"
    md_path.write_text(full_text, encoding="utf-8")
    rprint(f"[green]✅ Markdown sauvegardé → {md_path}[/green]")

    # Sauvegarder les images
    for img_name, img in images.items():
        img_path = OUTPUT_DIR / "images" / img_name
        img.save(str(img_path))
    rprint(f"[green]✅ {len(images)} image(s) extraite(s)[/green]")

    return full_text, images


# ─────────────────────────────────────────
# ÉTAPE 2 : EXTRACTION DES LIENS (PyMuPDF)
# ─────────────────────────────────────────

def extract_links(pdf_path: str) -> dict:
    rprint("[bold blue]🔗 Extraction des liens...[/bold blue]")
    doc = fitz.open(pdf_path)
    links_by_page = {}

    for page in doc:
        page_links = [l["uri"] for l in page.get_links() if l.get("uri")]
        if page_links:
            links_by_page[page.number + 1] = page_links
            rprint(f"  Page {page.number + 1} → {page_links}")

    doc.close()
    total = sum(len(v) for v in links_by_page.values())
    rprint(f"[green]✅ {total} lien(s) trouvé(s)[/green]")
    return links_by_page


# ─────────────────────────────────────────
# ÉTAPE 3 : DÉTECTION DE FORMULES
# ─────────────────────────────────────────

def detect_formula(text: str) -> bool:
    patterns = [
        r'\$.*?\$',
        r'\$\$.*?\$\$',
        r'\\frac',
        r'\\sqrt',
        r'\\sum',
        r'\\int',
        r'\\mathbb',
        r'[ⁿ⁰¹²³⁴⁵⁶⁷⁸⁹]',
        r'[ℕℤℝℚ]',
        r'√',
    ]
    return any(re.search(p, text) for p in patterns)


# ─────────────────────────────────────────
# ÉTAPE 4 : CHUNKING + FUSION
# ─────────────────────────────────────────

def merge_short_chunks(chunks: list, min_size: int = 500) -> list:
    merged = []
    buffer = None
    for chunk in chunks:
        if buffer is None:
            buffer = chunk
        elif len(buffer["full_text"]) < min_size:
            buffer["full_text"]  += "\n\n" + chunk["full_text"]
            buffer["content"]    += "\n\n" + chunk["content"]
            buffer["title"]      += " + " + chunk["title"]
            buffer["metadata"]["has_formula"] = (
                buffer["metadata"]["has_formula"] or chunk["metadata"]["has_formula"]
            )
        else:
            merged.append(buffer)
            buffer = chunk
    if buffer:
        merged.append(buffer)
    return merged


def chunk_markdown(markdown: str, links_by_page: dict) -> list:
    rprint("[bold blue]✂️  Chunking en cours...[/bold blue]")
    chunks = []
    sections = re.split(r'(?=^#{1,3} )', markdown, flags=re.MULTILINE)

    for i, section in enumerate(sections):
        section = section.strip()
        if not section or len(section) < 50:
            continue

        lines  = section.split("\n")
        title  = lines[0].lstrip("#").strip() if lines[0].startswith("#") else "Introduction"
        content = "\n".join(lines[1:]).strip()

        chunks.append({
            "id"       : f"chunk_{i:03d}",
            "title"    : title,
            "content"  : content,
            "full_text": section,
            "metadata" : {
                "source"      : PDF_PATH,
                "chunk_index" : i,
                "has_formula" : detect_formula(section),
                "links"       : [l for links in links_by_page.values() for l in links],
            }
        })

    chunks = merge_short_chunks(chunks)
    rprint(f"[green]✅ {len(chunks)} chunk(s) créé(s)[/green]")
    return chunks


# ─────────────────────────────────────────
# ÉTAPE 5 : SAUVEGARDE + VÉRIFICATION
# ─────────────────────────────────────────

def save_and_verify(chunks: list):
    output_path = OUTPUT_DIR / "chunks" / "chunks.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)

    avg = int(sum(len(c['full_text']) for c in chunks) / len(chunks)) if chunks else 0

    rprint(f"\n[bold green]✅ {len(chunks)} chunks sauvegardés → {output_path}[/bold green]")
    rprint("\n[bold]📊 RÉSUMÉ[/bold]")
    rprint(f"  Total chunks     : {len(chunks)}")
    rprint(f"  Avec formules    : {sum(1 for c in chunks if c['metadata']['has_formula'])}")
    rprint(f"  Avec liens       : {sum(1 for c in chunks if c['metadata']['links'])}")
    rprint(f"  Longueur moy.    : {avg} caractères")

    rprint("\n[bold]🔍 Aperçu du premier chunk :[/bold]")
    if chunks:
        c = chunks[0]
        rprint(f"  Titre   : {c['title']}")
        rprint(f"  Contenu : {c['full_text'][:400]}...")
        rprint(f"  Métas   : {c['metadata']}")


# ─────────────────────────────────────────
# PIPELINE PRINCIPAL
# ─────────────────────────────────────────

def run_pipeline(pdf_path: str):
    rprint(f"\n[bold magenta]🚀 Pipeline RAG — Marker v1[/bold magenta]\n")

    full_text, images = parse_with_marker(pdf_path)
    links             = extract_links(pdf_path)
    chunks            = chunk_markdown(full_text, links)
    save_and_verify(chunks)

    rprint("\n[bold magenta]🎉 Pipeline terminé ![/bold magenta]")
    return chunks


if __name__ == "__main__":
    run_pipeline(PDF_PATH)
=======
import os
import warnings
warnings.filterwarnings("ignore") # Pour masquer les petits avertissements de PyTorch/HuggingFace
=======
>>>>>>> e731bbf (conversion format markdown réussi avec la librarie Marker)

# Nouvelle API Marker v1+
from marker.converters.pdf import PdfConverter
from marker.models import create_model_dict
from marker.output import text_from_rendered

# ─────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────

PDF_PATH = r"C:\Users\kalfa\MATHutrice-1\dataset\Bases_fractions_puiss_radicaux.pdf"
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)
(OUTPUT_DIR / "chunks").mkdir(exist_ok=True)
(OUTPUT_DIR / "images").mkdir(exist_ok=True)


# ─────────────────────────────────────────
# ÉTAPE 1 : PARSING AVEC MARKER v1+
# ─────────────────────────────────────────

def parse_with_marker(pdf_path: str):
    rprint("[bold blue]📄 Chargement des modèles Marker...[/bold blue]")
    models = create_model_dict()

    rprint("[bold blue]📄 Parsing en cours...[/bold blue]")
    converter = PdfConverter(artifact_dict=models)
    rendered = converter(pdf_path)
    full_text, _, images = text_from_rendered(rendered)

    # Sauvegarder le markdown
    md_path = OUTPUT_DIR / "document_parsed.md"
    md_path.write_text(full_text, encoding="utf-8")
    rprint(f"[green]✅ Markdown sauvegardé → {md_path}[/green]")

    # Sauvegarder les images
    for img_name, img in images.items():
        img_path = OUTPUT_DIR / "images" / img_name
        img.save(str(img_path))
    rprint(f"[green]✅ {len(images)} image(s) extraite(s)[/green]")

    return full_text, images


# ─────────────────────────────────────────
# ÉTAPE 2 : EXTRACTION DES LIENS (PyMuPDF)
# ─────────────────────────────────────────

def extract_links(pdf_path: str) -> dict:
    rprint("[bold blue]🔗 Extraction des liens...[/bold blue]")
    doc = fitz.open(pdf_path)
    links_by_page = {}

    for page in doc:
        page_links = [l["uri"] for l in page.get_links() if l.get("uri")]
        if page_links:
            links_by_page[page.number + 1] = page_links
            rprint(f"  Page {page.number + 1} → {page_links}")

    doc.close()
    total = sum(len(v) for v in links_by_page.values())
    rprint(f"[green]✅ {total} lien(s) trouvé(s)[/green]")
    return links_by_page


# ─────────────────────────────────────────
# ÉTAPE 3 : DÉTECTION DE FORMULES
# ─────────────────────────────────────────

def detect_formula(text: str) -> bool:
    patterns = [
        r'\$.*?\$',
        r'\$\$.*?\$\$',
        r'\\frac',
        r'\\sqrt',
        r'\\sum',
        r'\\int',
        r'\\mathbb',
        r'[ⁿ⁰¹²³⁴⁵⁶⁷⁸⁹]',
        r'[ℕℤℝℚ]',
        r'√',
    ]
    return any(re.search(p, text) for p in patterns)


# ─────────────────────────────────────────
# ÉTAPE 4 : CHUNKING + FUSION
# ─────────────────────────────────────────

def merge_short_chunks(chunks: list, min_size: int = 500) -> list:
    merged = []
    buffer = None
    for chunk in chunks:
        if buffer is None:
            buffer = chunk
        elif len(buffer["full_text"]) < min_size:
            buffer["full_text"]  += "\n\n" + chunk["full_text"]
            buffer["content"]    += "\n\n" + chunk["content"]
            buffer["title"]      += " + " + chunk["title"]
            buffer["metadata"]["has_formula"] = (
                buffer["metadata"]["has_formula"] or chunk["metadata"]["has_formula"]
            )
        else:
            merged.append(buffer)
            buffer = chunk
    if buffer:
        merged.append(buffer)
    return merged


def chunk_markdown(markdown: str, links_by_page: dict) -> list:
    rprint("[bold blue]✂️  Chunking en cours...[/bold blue]")
    chunks = []
    sections = re.split(r'(?=^#{1,3} )', markdown, flags=re.MULTILINE)

    for i, section in enumerate(sections):
        section = section.strip()
        if not section or len(section) < 50:
            continue

        lines  = section.split("\n")
        title  = lines[0].lstrip("#").strip() if lines[0].startswith("#") else "Introduction"
        content = "\n".join(lines[1:]).strip()

        chunks.append({
            "id"       : f"chunk_{i:03d}",
            "title"    : title,
            "content"  : content,
            "full_text": section,
            "metadata" : {
                "source"      : PDF_PATH,
                "chunk_index" : i,
                "has_formula" : detect_formula(section),
                "links"       : [l for links in links_by_page.values() for l in links],
            }
        })

    chunks = merge_short_chunks(chunks)
    rprint(f"[green]✅ {len(chunks)} chunk(s) créé(s)[/green]")
    return chunks


# ─────────────────────────────────────────
# ÉTAPE 5 : SAUVEGARDE + VÉRIFICATION
# ─────────────────────────────────────────

def save_and_verify(chunks: list):
    output_path = OUTPUT_DIR / "chunks" / "chunks.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)

    avg = int(sum(len(c['full_text']) for c in chunks) / len(chunks)) if chunks else 0

    rprint(f"\n[bold green]✅ {len(chunks)} chunks sauvegardés → {output_path}[/bold green]")
    rprint("\n[bold]📊 RÉSUMÉ[/bold]")
    rprint(f"  Total chunks     : {len(chunks)}")
    rprint(f"  Avec formules    : {sum(1 for c in chunks if c['metadata']['has_formula'])}")
    rprint(f"  Avec liens       : {sum(1 for c in chunks if c['metadata']['links'])}")
    rprint(f"  Longueur moy.    : {avg} caractères")

    rprint("\n[bold]🔍 Aperçu du premier chunk :[/bold]")
    if chunks:
        c = chunks[0]
        rprint(f"  Titre   : {c['title']}")
        rprint(f"  Contenu : {c['full_text'][:400]}...")
        rprint(f"  Métas   : {c['metadata']}")


# ─────────────────────────────────────────
# PIPELINE PRINCIPAL
# ─────────────────────────────────────────

def run_pipeline(pdf_path: str):
    rprint(f"\n[bold magenta]🚀 Pipeline RAG — Marker v1[/bold magenta]\n")

    full_text, images = parse_with_marker(pdf_path)
    links             = extract_links(pdf_path)
    chunks            = chunk_markdown(full_text, links)
    save_and_verify(chunks)

    rprint("\n[bold magenta]🎉 Pipeline terminé ![/bold magenta]")
    return chunks


if __name__ == "__main__":
<<<<<<< HEAD
    main()
>>>>>>> 21dc059 (Création of the BDV branch)
=======
    run_pipeline(PDF_PATH)
>>>>>>> e731bbf (conversion format markdown réussi avec la librarie Marker)
