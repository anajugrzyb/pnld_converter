import os
import base64
import re
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
MAX_PACKAGE_SIZE_BYTES = int(1.5 * 1024 ** 3)

app = FastAPI(
    title="PNLD Converter",
    description="API that converts PDFs to PNLD (.pnld) format",
    version="1.2.0"
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
        author_background: Optional[str] = Form(None),
        organizer: Optional[str] = Form(None),
        editor: str = Form(...),
        edition_number: Optional[str] = Form(None),
        editor_address: Optional[str] = Form(None),
        publication_city: Optional[str] = Form(None),
        publication_year: Optional[str] = Form(None),
        isbn: Optional[str] = Form(None),
        catalog_card: Optional[str] = Form(None),
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

    chapters = split_into_logical_units(text)
    if not chapters:
        raise HTTPException(status_code=500, detail="Não foi possível segmentar o PDF em unidades lógicas.")

    authors_list = parse_authors(authors)

    cover_metadata = CoverMetadata(
        collection_title=collection_title.strip() or file.filename,
        book_title=(book_title or "").strip() or None,
        authors=authors_list,
        author_background=(author_background or "").strip() or None,
        organizer=(organizer or "").strip() or None,
        editor=editor.strip() or "Editor não informado",
        edition_number=(edition_number or "").strip() or None,
        editor_address=(editor_address or "").strip() or None,
        publication_city=(publication_city or "").strip() or None,
        publication_year=(publication_year or "").strip() or None,
        isbn=(isbn or "").strip() or None,
        catalog_card=(catalog_card or "").strip() or None,
    )

    html_title = cover_metadata.book_title or cover_metadata.collection_title


    create_structure(base_dir)
    generate_files(base_dir, chapters, html_title, cover_metadata)
    create_pnld_package(base_dir, output_pnld)

    if output_pnld.stat().st_size > MAX_PACKAGE_SIZE_BYTES:
        raise HTTPException(
            status_code=400,
            detail="O pacote PNLD excede o tamanho máximo permitido de 1,5GB."
        )

    return FileResponse(
        output_pnld,
        filename=OUTPUT_NAME,
        media_type="application/zip"
    )


def extract_text_from_pdf(pdf_path: Path) -> str:
    return extract_text(pdf_path)

@dataclass
class Chapter:
    title: str
    paragraphs: list[str]


def parse_authors(authors: Optional[str]) -> list[str]:
    if not authors:
        return []
    parsed = [name.strip() for name in authors.replace("\n", ";").split(";")]
    return [name for name in parsed if name]

def split_into_logical_units(text: str) -> list[Chapter]:
    def is_heading(line: str) -> bool:
        stripped = line.strip()
        if not stripped:
            return False
        if len(stripped) > 120:
            return False
        if re.match(r"cap[íi]tulo\s+\d+", stripped, re.IGNORECASE):
            return True
        if stripped.isupper() and len(stripped.split()) <= 12:
            return True
        return False

    def flush_paragraph(paragraph_lines: list[str], paragraphs: list[str]):
        if paragraph_lines:
            paragraph = " ".join(line.strip() for line in paragraph_lines if line.strip())
            if paragraph:
                paragraphs.append(paragraph)
            paragraph_lines.clear()

    chapters: list[Chapter] = []
    current_title: Optional[str] = None
    current_paragraphs: list[str] = []
    paragraph_buffer: list[str] = []

    for line in text.splitlines():
        if is_heading(line):
            flush_paragraph(paragraph_buffer, current_paragraphs)
            if current_title or current_paragraphs:
                title = current_title or f"Unidade {len(chapters) + 1:02}"
                if current_paragraphs:
                    chapters.append(Chapter(title=title, paragraphs=current_paragraphs))
                current_paragraphs = []
            current_title = line.strip()
            continue

        if not line.strip():
            flush_paragraph(paragraph_buffer, current_paragraphs)
            continue

        paragraph_buffer.append(line)

    flush_paragraph(paragraph_buffer, current_paragraphs)

    if current_title or current_paragraphs:
        title = current_title or f"Unidade {len(chapters) + 1:02}"
        chapters.append(Chapter(title=title, paragraphs=current_paragraphs))

    if not chapters:
        simple_paragraphs = [p for p in text.split("\n\n") if p.strip()]
        if simple_paragraphs:
            chapters.append(Chapter(title="Unidade 01", paragraphs=[p.strip() for p in simple_paragraphs]))

    return chapters


@dataclass
class CoverMetadata:
    collection_title: str
    book_title: Optional[str] = None
    authors: Iterable[str] = field(default_factory=list)
    author_background: Optional[str] = None
    organizer: Optional[str] = None
    editor: str = "Editor não informado"
    edition_number: Optional[str] = None
    editor_address: Optional[str] = None
    publication_city: Optional[str] = None
    publication_year: Optional[str] = None
    isbn: Optional[str] = None
    catalog_card: Optional[str] = None

    expression: str = (
        "Obras de Apoio Pedagógico de natureza teórico-metodológica para Docentes dos Anos Iniciais do Ensino Fundamental"
    )

    def authors_text(self) -> str:
        authors = list(self.authors)
        return ", ".join(authors) if authors else "Autor(es) não informados"

    def isbn_text(self) -> str:
        return self.isbn or "ISBN não informado"

    def author_background_text(self) -> str:
        return (
                self.author_background or "Formação e experiência profissional não informada"
        )

    def edition_text(self) -> str:
        return self.edition_number or "Edição não informada"

    def publication_city_text(self) -> str:
        return self.publication_city or "Local de publicação não informado"

    def publication_year_text(self) -> str:
        return self.publication_year or "Ano de publicação não informado"

    def editor_address_text(self) -> str:
        return self.editor_address or "Endereço do editor não informado"

    def catalog_card_text(self) -> str:
        return self.catalog_card or "Ficha catalográfica não informada"


def generate_html5(
        chapter: Chapter,
        title: str = "PNLD Work",
        cover_metadata: Optional[CoverMetadata] = None,
        include_cover: bool = False,
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

    if include_cover:
        if cover_metadata is None:
            cover_metadata = CoverMetadata(collection_title=title)

        cover_header = soup.new_tag("header", attrs={"class": "pnld-capa"})

        first_cover = soup.new_tag("section", attrs={"class": "capa-primeira", "data-objeto": "2"})
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
        else:
            editor_resp = soup.new_tag("span", attrs={"class": "editor-responsavel"})
            editor_resp.string = f"Editor responsável: {cover_metadata.editor}"
            authors_tag.append(soup.new_tag("br"))
            authors_tag.append(editor_resp)

        first_cover.append(authors_tag)

        editor_tag = soup.new_tag("p", attrs={"class": "creditos-editor"})
        editor_span = soup.new_tag("span", attrs={"class": "editor"})
        editor_span.string = f"Editor: {cover_metadata.editor}"
        editor_tag.append(editor_span)
        first_cover.append(editor_tag)

        cover_header.append(first_cover)

        second_cover = soup.new_tag("section", attrs={"class": "capa-segunda", "data-objeto": "2"})
        cover_header.append(second_cover)

        third_cover = soup.new_tag("section", attrs={"class": "capa-terceira", "data-objeto": "2"})
        cover_header.append(third_cover)

        fourth_cover = soup.new_tag("section", attrs={"class": "capa-quarta", "data-objeto": "2"})
        isbn_paragraph = soup.new_tag("p", attrs={"class": "identificacao-isbn"})
        isbn_span = soup.new_tag("span", attrs={"class": "isbn"})
        isbn_span.string = f"ISBN: {cover_metadata.isbn_text()}"
        isbn_paragraph.append(isbn_span)
        fourth_cover.append(isbn_paragraph)
        cover_header.append(fourth_cover)

        body.append(cover_header)

        folha_rosto = soup.new_tag("section", attrs={"class": "folha-rosto", "data-objeto": "2"})

        face_titles = soup.new_tag("div", attrs={"class": "folha-rosto-titulos"})
        face_collection_title = soup.new_tag("h1", attrs={"class": "titulo-colecao"})
        face_collection_title.string = cover_metadata.collection_title
        face_titles.append(face_collection_title)

        if cover_metadata.book_title:
            face_book_title = soup.new_tag("h2", attrs={"class": "titulo-livro"})
            face_book_title.string = cover_metadata.book_title
            face_titles.append(face_book_title)

        folha_rosto.append(face_titles)

        face_expression = soup.new_tag("p", attrs={"class": "expressao-objeto"})
        face_expression.string = cover_metadata.expression
        folha_rosto.append(face_expression)

        face_authors = soup.new_tag("p", attrs={"class": "creditos-autoria"})
        face_authors.string = f"Autor(es): {cover_metadata.authors_text()}"
        if cover_metadata.organizer:
            organizer_info = soup.new_tag("span", attrs={"class": "organizador"})
            organizer_info.string = f"Organizador: {cover_metadata.organizer}"
            face_authors.append(soup.new_tag("br"))
            face_authors.append(organizer_info)
        folha_rosto.append(face_authors)

        author_background = soup.new_tag("p", attrs={"class": "formacao-experiencia"})
        author_background.string = cover_metadata.author_background_text()
        folha_rosto.append(author_background)

        face_editor = soup.new_tag("p", attrs={"class": "creditos-editor"})
        face_editor.string = f"Editor: {cover_metadata.editor}"
        folha_rosto.append(face_editor)

        edition_info = soup.new_tag("p", attrs={"class": "informacoes-edicao"})
        edition_info.string = (
            f"Edição: {cover_metadata.edition_text()} | "
            f"Local: {cover_metadata.publication_city_text()} | "
            f"Ano: {cover_metadata.publication_year_text()}"
        )
        folha_rosto.append(edition_info)

        verso_folha_rosto = soup.new_tag(
            "section", attrs={"class": "verso=folha-rosto", "data-objeto": "2"}
        )

        catalog_card = soup.new_tag("p", attrs={"class": "ficha-catalografica"})
        catalog_card.string = cover_metadata.catalog_card_text()
        verso_folha_rosto.append(catalog_card)

        editor_info = soup.new_tag("p", attrs={"class": "informacoes-editor"})
        editor_info.string = (
            f"Editor: {cover_metadata.editor} | Endereço: {cover_metadata.editor_address_text()}"
        )
        verso_folha_rosto.append(editor_info)

        body.append(folha_rosto)
        body.append(verso_folha_rosto)

    main = soup.new_tag("main", attrs={"class": "conteudo"})
    heading = soup.new_tag("h2")
    heading.string = chapter.title
    main.append(heading)

    for paragraph in chapter.paragraphs:
        p_tag = soup.new_tag("p")
        p_tag.string = paragraph
        main.append(p_tag)
    body.append(main)

    html.append(body)
    return f"{doctype}\n{str(html)}"


def create_structure(base_path: Path):
    structure = [
        "content",
        "resources/images",
        "resources/audios",
        "resources/videos",
        "resources/styles",
        "resources/scripts",
        "resources/fonts",
    ]
    for folder in structure:
        dir_path = base_path / folder
        dir_path.mkdir(parents=True, exist_ok=True)
        keep_file = dir_path / ".keep"
        keep_file.write_text("", encoding="utf-8")


def generate_files(
        base_path: Path,
        chapters: list[Chapter],
        title: str,
        cover_metadata: Optional[CoverMetadata],
):
    chapter_files: list[str] = []

    for index, chapter in enumerate(chapters, start=1):
        include_cover = index == 1
        html_content = generate_html5(
            chapter,
            title=title,
            cover_metadata=cover_metadata,
            include_cover=include_cover,
        )

        if include_cover:
            (base_path / "index.html").write_text(html_content, encoding="utf-8")

        file_name = f"unidade_{index:02}.html"
        content_file = base_path / "content" / file_name
        content_file.write_text(html_content, encoding="utf-8")
        chapter_files.append(file_name)


    (base_path / "toc.ncx").write_text(default_toc_ncx(title, chapters, chapter_files), encoding="utf-8")
    (base_path / "content.opf").write_text(default_content_opf(title, chapter_files), encoding="utf-8")

    write_placeholder_cover(base_path / "cover.jpg")


def create_pnld_package(base_path: Path, output_zip: Path) -> Path:
    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(base_path):
            for file in files:
                path = Path(root) / file
                zf.write(path, path.relative_to(base_path))
    return output_zip

def default_toc_ncx(title: str, chapters: list[Chapter], chapter_files: list[str]) -> str:
    navpoints = []
    for order, (chapter, file_name) in enumerate(zip(chapters, chapter_files), start=1):
        navpoints.append(
            f"    <navPoint id=\"navpoint-{order}\" playOrder=\"{order}\">\n"
            f"      <navLabel>\n"
            f"        <text>{chapter.title}</text>\n"
            f"      </navLabel>\n"
            f"      <content src=\"content/{file_name}\" />\n"
            f"    </navPoint>"
        )

    navpoints_str = "\n".join(navpoints)

    return (
        "<?xml version='1.0' encoding='UTF-8'?>\n"
        "<ncx xmlns=\"http://www.daisy.org/z3986/2005/ncx/\" version=\"2005-1\">\n"
        "  <head>\n"
        "    <meta name=\"dtb:uid\" content=\"pnld-package\" />\n"
        "    <meta name=\"dtb:depth\" content=\"1\" />\n"
        "    <meta name=\"dtb:totalPageCount\" content=\"0\" />\n"
        "    <meta name=\"dtb:maxPageNumber\" content=\"0\" />\n"
        "  </head>\n"
        "  <docTitle>\n"
        f"    <text>{title}</text>\n"
        "  </docTitle>\n"
        "  <navMap>\n"
        f"{navpoints_str}\n"
        "  </navMap>\n"
        "</ncx>\n"
    )


def default_content_opf(title: str, chapter_files: list[str]) -> str:
    manifest_items = ["    <item id=\"index\" href=\"index.html\" media-type=\"application/xhtml+xml\" />"]
    spine_items = ["    <itemref idref=\"index\" />"]

    for idx, file_name in enumerate(chapter_files, start=1):
        item_id = f"unidade_{idx:02}"
        manifest_items.append(
            f"    <item id=\"{item_id}\" href=\"content/{file_name}\" media-type=\"application/xhtml+xml\" />"
        )
        spine_items.append(f"    <itemref idref=\"{item_id}\" />")

    manifest_items.append("    <item id=\"toc\" href=\"toc.ncx\" media-type=\"application/x-dtbncx+xml\" />")
    manifest_items.append("    <item id=\"cover\" href=\"cover.jpg\" media-type=\"image/jpeg\" />")

    manifest_block = "\n".join(manifest_items)
    spine_block = "\n".join(spine_items)

    return (
        "<?xml version='1.0' encoding='UTF-8'?>\n"
        "<package version=\"2.0\" xmlns=\"http://www.idpf.org/2007/opf\" unique-identifier=\"BookId\">\n"
        "  <metadata xmlns:dc=\"http://purl.org/dc/elements/1.1/\">\n"
        f"    <dc:title>{title}</dc:title>\n"
        "    <dc:identifier id=\"BookId\">pnld-package</dc:identifier>\n"
        "    <dc:language>pt-BR</dc:language>\n"
        "  </metadata>\n"
        "  <manifest>\n"
        f"{manifest_block}\n"
        "  </manifest>\n"
        "  <spine toc=\"toc\">\n"
        f"{spine_block}\n"
        "  </spine>\n"
        "</package>\n"
    )



def write_placeholder_cover(cover_path: Path):
    placeholder_bytes = base64.b64decode(
        """
        /9j/4AAQSkZJRgABAQAAAQABAAD/2wCEAAkGBxAQEBAPEBAVDw8PDw8PDw8PFREPFQ8QFREWFhURFRUYHSggGBolGxUVITEhJSkrLi4uFx8zODMtNygtLisBCgoKDg0OGxAQGy0fHR0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLf/AABEIAKgBLAMBIgACEQEDEQH/xAAbAAACAwEBAQAAAAAAAAAAAAADBAACBQEGB//EADwQAAIBAwIEAwUFBAEEAwAAAAECAwAEEQUSITFBBtQVNcDxBhUiMpHwYnLRFjNCI1JicrLxM0Ny/8QAGgEAAgMBAQAAAAAAAAAAAAAAAAQBAgMFBv/EACMRAAICAgICAgMBAAAAAAAAAAABAhEDIRIxBBNBYRRRYXH/2gAMAwEAAhEDEQA/APqREQEREBERAREQEREBERAREQEREBERAREQEREBERAREQEREBERAREQEREBERAREQEREBERAREQEREBERAREQEREBERAREQEREBERAREQEREBERAREQEREBERAREQEREBERAREQEREBERAREQEREBERAREQEREH//Z
        """
    )
    cover_path.write_bytes(placeholder_bytes)
