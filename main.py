import os
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pdfminer.high_level import extract_text
from bs4 import BeautifulSoup

TEMP_DIR = Path("temp")
BASE_FOLDER_NAME = "pnld_project"
OUTPUT_NAME = "converted_work.pnld"

app = FastAPI(
    title="PNLD Converter",
    description="API that converts PDFs to PNLD (.pnld) format",
    version="1.0.0"
)

@app.get("/")
def home():
    return {"message": "PNLD Converter API is ready! Upload a PDF to /convert"}


@app.post("/convert")
async def convert_pdf(
    file: UploadFile = File(...),
    collection_title: str = Form(...),
    book_title: Optional[str] = Form(None),
    authors: Optional[str] = Form(None),
    organizer: Optional[str] = Form(None),
    editor: str = Form(...),
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please upload a valid PDF file.")

    temp_dir = TEMP_DIR
    base_dir = temp_dir / BASE_FOLDER_NAME
    output_pnld = temp_dir / OUTPUT_NAME

    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    base_dir.mkdir(parents=True, exist_ok=True)

    pdf_path = base_dir / file.filename
    with open(pdf_path, "wb") as f:
        f.write(await file.read())

    try:
        text = extract_text_from_pdf(pdf_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    authors_list = parse_authors(authors)
    cover_metadata = CoverMetadata(
        collection_title=collection_title.strip() or file.filename,
        book_title=(book_title or "").strip() or None,
        authors=authors_list,
        organizer=(organizer or "").strip() or None,
        editor=editor.strip() or "Editor não informado",
    )

    html_title = cover_metadata.book_title or cover_metadata.collection_title
    html_content = generate_html5(
        text,
        title=html_title,
        cover_metadata=cover_metadata,
    )

    create_structure(base_dir)
    generate_files(base_dir, html_content)
    create_pnld_package(base_dir, output_pnld)

    return FileResponse(
        output_pnld,
        filename=OUTPUT_NAME,
        media_type="application/zip"
    )


def extract_text_from_pdf(pdf_path: Path) -> str:
    return extract_text(pdf_path)

def parse_authors(authors: Optional[str]) -> list[str]:
    if not authors:
        return []
    parsed = [name.strip() for name in authors.replace("\n", ";").split(";")]
    return [name for name in parsed if name]


@dataclass
class CoverMetadata:
    """Metadata required to build the first cover of an Objeto 2 work."""

    collection_title: str
    book_title: Optional[str] = None
    authors: Iterable[str] = field(default_factory=list)
    organizer: Optional[str] = None
    editor: str = "Editor não informado"

    expression: str = (
        "Obras de Apoio Pedagógico de natureza teórico-metodológica para Docentes "
        "dos Anos Iniciais do Ensino Fundamental"
    )

    def authors_text(self) -> str:
        authors = list(self.authors)
        return ", ".join(authors) if authors else "Autor(es) não informados"


def generate_html5(
    text: str,
    title: str = "PNLD Work",
    cover_metadata: Optional[CoverMetadata] = None,
) -> str:
    soup = BeautifulSoup("", "html.parser")
    doctype = "<!DOCTYPE html>"

    html = soup.new_tag("html", lang="pt-br")
    head = soup.new_tag("head")
    head.append(soup.new_tag("meta", charset="UTF-8"))
    head.append(
        soup.new_tag("meta", attrs={"name": "robots", "content": "noindex, nofollow"})
    )

    title_tag = soup.new_tag("title")
    title_tag.string = title
    head.append(title_tag)
    html.append(head)
    body = soup.new_tag("body", attrs={"class": "pnld-obra"})

    if cover_metadata is None:
        cover_metadata = CoverMetadata(collection_title=title)

    cover_header = soup.new_tag("header", attrs={"class": "pnld-capa"})
    first_cover = soup.new_tag(
        "section", attrs={"class": "capa-primeira", "data-objeto": "2"}
    )

    collection_title_tag = soup.new_tag("h1", attrs={"class": "titulo-colecao"})
    collection_title_tag.string = cover_metadata.collection_title
    first_cover.append(collection_title_tag)

    if cover_metadata.book_title:
        book_title_tag = soup.new_tag("h2", attrs={"class": "titulo-livro"})
        book_title_tag.string = cover_metadata.book_title
        first_cover.append(book_title_tag)

    expression_tag = soup.new_tag("p", attrs={"class": "expressao-objeto"})
    expression_tag.string = cover_metadata.expression
    first_cover.append(expression_tag)

    authors_tag = soup.new_tag("p", attrs={"class": "creditos-autoria"})
    authors_span = soup.new_tag("span", attrs={"class": "autores"})
    authors_span.string = f"Autor(es): {cover_metadata.authors_text()}"
    authors_tag.append(authors_span)

    if cover_metadata.organizer:
        organizer_span = soup.new_tag("span", attrs={"class": "organizador"})
        organizer_span.string = f"Organizador: {cover_metadata.organizer}"
        authors_tag.append(soup.new_tag("br"))
        authors_tag.append(organizer_span)

    first_cover.append(authors_tag)

    editor_tag = soup.new_tag("p", attrs={"class": "creditos-editor"})
    editor_span = soup.new_tag("span", attrs={"class": "editor"})
    editor_span.string = f"Editor: {cover_metadata.editor}"
    editor_tag.append(editor_span)
    first_cover.append(editor_tag)

    cover_header.append(first_cover)
    body.append(cover_header)

    main = soup.new_tag("main", attrs={"class": "conteudo"})
    main.string = text
    body.append(main)
    html.append(body)

    return f"{doctype}\n{str(html)}"


def create_structure(base_path: Path):
    structure = [
        "content",
        "resources/images",
        "resources/styles",
        "resources/scripts",
        "resources/fonts"
    ]
    for folder in structure:
        dir_path = base_path / folder
        dir_path.mkdir(parents=True, exist_ok=True)
        keep_file = dir_path / ".keep"
        keep_file.write_text("", encoding="utf-8")


def generate_files(base_path: Path, html_content: str):
    (base_path / "index.html").write_text(html_content, encoding="utf-8")

def create_pnld_package(base_path: Path, output_zip: Path) -> Path:
    """Create a PNLD package as a ZIP archive and return its location."""

    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(base_path):
            for file in files:
                path = Path(root) / file
                zf.write(path, path.relative_to(base_path))

    return output_zip
