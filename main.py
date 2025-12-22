import os
import base64
import re
import shutil
import zipfile
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional
from uuid import uuid4
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pdfminer.high_level import extract_text
from bs4 import BeautifulSoup

TEMP_DIR = Path("temp")
BASE_FOLDER_NAME = "pnld_project"
OUTPUT_NAME = "converted_work.pnld"
MAX_PACKAGE_SIZE_BYTES = int(1.5 * 1024 ** 3)
OPF_VERSION = "3.0"

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
        page_map: Optional[str] = Form(None),
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
    parsed_page_map = parse_page_map(page_map)

    generate_files(
        base_dir,
        chapters,
        html_title,
        cover_metadata,
        page_map=parsed_page_map,
    )
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
    raw_text = extract_text(pdf_path)
    normalized_lines = [
        line.strip() for line in raw_text.splitlines()
    ]
    return "\n".join(normalized_lines)


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

def _build_base_html(title: str) -> tuple[BeautifulSoup, Any, Any, str]:
    soup = BeautifulSoup("", "html.parser")

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

    body = soup.new_tag("body", attrs={"class": "pnld-obra", "lang": "pt-BR"})
    html.append(body)

    doctype = "<!DOCTYPE html>"
    return soup, html, body, doctype


def generate_cover_section(soup: BeautifulSoup, cover_metadata: CoverMetadata):
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

    return cover_header


def generate_front_matter(soup: BeautifulSoup, cover_metadata: CoverMetadata):
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
        "section", attrs={"class": "verso-folha-rosto", "data-objeto": "2"}
    )

    catalog_card = soup.new_tag("p", attrs={"class": "ficha-catalografica"})
    catalog_card.string = cover_metadata.catalog_card_text()
    verso_folha_rosto.append(catalog_card)

    editor_info = soup.new_tag("p", attrs={"class": "informacoes-editor"})
    editor_info.string = (
        f"Editor: {cover_metadata.editor} | Endereço: {cover_metadata.editor_address_text()}"
    )
    verso_folha_rosto.append(editor_info)

    return folha_rosto, verso_folha_rosto

def generate_content_html(
        chapter: Chapter,
        title: str = "PNLD Work",
) -> str:
    soup, html, body, doctype = _build_base_html(title)

    main = soup.new_tag("main", attrs={"class": "conteudo", "role": "main"})

    header = soup.new_tag("header")
    book_heading = soup.new_tag("h1")
    book_heading.string = title
    header.append(book_heading)
    main.append(header)

    chapter_section = soup.new_tag("section", attrs={"aria-label": chapter.title})
    heading = soup.new_tag("h2")
    heading.string = chapter.title
    chapter_section.append(heading)

    for paragraph in chapter.paragraphs:
        p_tag = soup.new_tag("p")
        p_tag.string = paragraph
        chapter_section.append(p_tag)

    main.append(chapter_section)
    body.append(main)

    return f"{doctype}\n{str(html)}"

def generate_pre_textual_html(title: str, cover_metadata: CoverMetadata) -> str:
    soup, html, body, doctype = _build_base_html(title)
    main = soup.new_tag("main", attrs={"class": "conteudo", "role": "main"})

    header = soup.new_tag("header")
    heading = soup.new_tag("h1")
    heading.string = title
    header.append(heading)
    main.append(header)

    pre_textual_section = soup.new_tag("section", attrs={"aria-label": "Materiais pré-textuais"})
    section_heading = soup.new_tag("h2")
    section_heading.string = "Materiais pré-textuais"
    pre_textual_section.append(section_heading)

    resumo = soup.new_tag("p")
    resumo.string = (
        "Esta seção reúne informações editoriais e de autoria fornecidas para a obra."
        )
    pre_textual_section.append(resumo)

    autores = soup.new_tag("p")
    autores.string = f"Autor(es): {cover_metadata.authors_text()}"
    pre_textual_section.append(autores)

    contexto = soup.new_tag("p")
    contexto.string = cover_metadata.author_background_text()
    pre_textual_section.append(contexto)

    edicao = soup.new_tag("p")
    edicao.string = (
        f"Edição: {cover_metadata.edition_text()} | Local: {cover_metadata.publication_city_text()} | "
        f"Ano: {cover_metadata.publication_year_text()}"
    )
    pre_textual_section.append(edicao)

    main.append(pre_textual_section)

    body.append(main)
    return f"{doctype}\n{str(html)}"

def generate_index_html(title: str, cover_metadata: CoverMetadata, toc_entries: list[tuple[str, str, str]]) -> str:
    soup, html, body, doctype = _build_base_html(title)

    head = soup.head or html.find("head")

    description_parts = ["PNLD", cover_metadata.collection_title]
    if cover_metadata.book_title:
        description_parts.append(cover_metadata.book_title)
    description_content = " - ".join(description_parts)

    if cover_metadata.authors:
        author_content = ", ".join(cover_metadata.authors)
    elif cover_metadata.organizer:
        author_content = cover_metadata.organizer
    else:
        author_content = "Equipe editorial"

    charset_meta = head.find("meta", attrs={"charset": True}) or soup.new_tag(
        "meta", charset="UTF-8"
    )
    title_tag = head.title or soup.new_tag("title")
    title_tag.string = title

    description_meta = head.find("meta", attrs={"name": "description"})
    if description_meta:
        description_meta["content"] = description_content
    else:
        description_meta = soup.new_tag(
            "meta", attrs={"name": "description", "content": description_content}
        )

    author_meta = head.find("meta", attrs={"name": "author"})
    if author_meta:
        author_meta["content"] = author_content
    else:
        author_meta = soup.new_tag("meta", attrs={"name": "author", "content": author_content})

    robots_meta = head.find("meta", attrs={"name": "robots"})
    if robots_meta:
        robots_meta["content"] = "noindex, nofollow"
    else:
        robots_meta = soup.new_tag(
            "meta", attrs={"name": "robots", "content": "noindex, nofollow"}
        )

    other_head_elements = [
        child
        for child in list(head.children)
        if child not in {charset_meta, title_tag, description_meta, author_meta, robots_meta}
    ]

    head.clear()
    head.extend([charset_meta, title_tag, description_meta, author_meta, robots_meta])
    head.extend(other_head_elements)

    for existing_nav in body.find_all("nav"):
        existing_nav.decompose()

    main = soup.new_tag("main", attrs={"role": "main"})
    header = soup.new_tag("header", attrs={"class": "cabecalho-obra"})
    main_heading = soup.new_tag("h1")
    main_heading.string = title
    header.append(main_heading)
    main.append(header)

    cover_header = generate_cover_section(soup, cover_metadata)
    main.append(cover_header)

    folha_rosto, verso_folha_rosto = generate_front_matter(soup, cover_metadata)
    main.append(folha_rosto)
    main.append(verso_folha_rosto)

    apresentacao = soup.new_tag("section", attrs={"class": "apresentacao", "data-objeto": "2", "aria-label": "Apresentação"})
    apresentacao_heading = soup.new_tag("h2")
    apresentacao_heading.string = "Apresentação"
    apresentacao.append(apresentacao_heading)
    apresentacao_paragraph = soup.new_tag("p")
    apresentacao_paragraph.string = cover_metadata.expression
    apresentacao.append(apresentacao_paragraph)
    main.append(apresentacao)

    body.append(main)

    nav = soup.new_tag("nav", id="toc", role="doc-toc", attrs={"aria-label": "Sumário"})
    nav_heading = soup.new_tag("h2")
    nav_heading.string = "Sumário"
    nav.append(nav_heading)

    toc_list = soup.new_tag("ul")
    for entry_title, href, page_number in toc_entries:
        li = soup.new_tag("li")
        link = soup.new_tag("a", href=href)
        link.string = entry_title
        li.append(link)

        page_span = soup.new_tag("span", attrs={"class": "toc-page"})
        page_span.string = page_number
        li.append(page_span)

        toc_list.append(li)
    nav.append(toc_list)
    body.append(nav)
    return f"{doctype}\n{str(html)}"

def to_roman(number: int) -> str:
    mapping = [
        (1000, "M"),
        (900, "CM"),
        (500, "D"),
        (400, "CD"),
        (100, "C"),
        (90, "XC"),
        (50, "L"),
        (40, "XL"),
        (10, "X"),
        (9, "IX"),
        (5, "V"),
        (4, "IV"),
        (1, "I"),
    ]

    result = ""
    remaining = max(0, number)
    for value, symbol in mapping:
        while remaining >= value:
            result += symbol
            remaining -= value
    return result or str(number)


def build_page_anchor_id(display_number: str) -> str:
    safe_display = re.sub(r"[^A-Za-z0-9_-]+", "-", str(display_number)).strip("-") or "page"
    return f"page-{safe_display}"


def normalize_page_info(raw_page_info: Any) -> tuple[str, bool, Optional[int]]:
    is_manual_professor = False
    page_number_value: Any = raw_page_info
    if isinstance(raw_page_info, dict):
        is_manual_professor = bool(
            raw_page_info.get("mp")
            or raw_page_info.get("is_mp")
            or raw_page_info.get("manual_do_professor")
        )
        for key in ("number", "numero", "page", "pagina", "value"):
            if key in raw_page_info:
                page_number_value = raw_page_info[key]
                break

    try:
        numeric_page = int(page_number_value)
    except (TypeError, ValueError):
        numeric_page = None

    display_number = (
        to_roman(numeric_page) if is_manual_professor and numeric_page is not None else str(page_number_value)
    )

    return display_number, is_manual_professor, numeric_page


def extract_primary_page_reference(page_map_for_file: dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    if not page_map_for_file:
        return None, None

    best_display: Optional[str] = None
    best_anchor: Optional[str] = None
    best_numeric: Optional[int] = None

    for _, raw_page_info in page_map_for_file.items():
        display_number, _, numeric_page = normalize_page_info(raw_page_info)
        anchor_id = build_page_anchor_id(display_number)

        if best_display is None:
            best_display, best_anchor, best_numeric = display_number, anchor_id, numeric_page
            continue

        if numeric_page is not None and (best_numeric is None or numeric_page < best_numeric):
            best_display, best_anchor, best_numeric = display_number, anchor_id, numeric_page

    return best_display, best_anchor



def inject_page_numbers(html: str, page_map: dict[str, Any]) -> str:
    if not page_map:
        return html

    soup = BeautifulSoup(html, "html.parser")
    body = soup.body or soup

    for marker, raw_page_info in page_map.items():
        marker_node = None

        for text_node in body.find_all(string=True):
            if marker in text_node:
                marker_node = text_node
                break

        if marker_node is None:
            continue

        display_number, is_manual_professor, _ = normalize_page_info(raw_page_info)

        aria_label = f"Página {display_number}"
        if is_manual_professor:
            aria_label = f"{aria_label} – Manual do Professor"

        page_break = soup.new_tag("p", role="doc-pagebreak", attrs={"aria-label": aria_label})
        page_label_span = soup.new_tag("span", attrs={"class": "page-label visually-hidden"})
        page_label_span.string = "Página"
        page_number_span = soup.new_tag("span", attrs={"class": "page-number"})
        page_number_span.string = display_number
        page_break.extend([page_label_span, page_number_span])

        page_break["id"] = build_page_anchor_id(display_number)

        if is_manual_professor:
            mp_suffix_span = soup.new_tag("span", attrs={"class": "mp-suffix visually-hidden"})
            mp_suffix_span.string = "MP"
            page_break.append(mp_suffix_span)

        marker_parent = marker_node.parent
        if marker_parent and marker_parent.parent:
            logical_container = next(
                (ancestor for ancestor in marker_node.parents if
                 getattr(ancestor, "name", "") in {"section", "article"}),
                None,
            )

            if logical_container is not None:
                logical_container.insert(0, page_break)
            else:
                top_level_block = next(
                    (
                        ancestor
                        for ancestor in marker_node.parents
                        if getattr(ancestor, "parent", None) is body and ancestor is not body
                    ),
                    None,
                )

                if top_level_block is not None:
                    top_level_block.insert_before(page_break)
                else:
                    body.insert(0, page_break)
        else:
            body.insert(0, page_break)

        cleaned_text = marker_node.replace(marker, "")
        if cleaned_text.strip():
            marker_node.replace_with(cleaned_text)
        else:
            marker_node.extract()

    return str(soup)


def parse_page_map(raw_page_map: Optional[str]) -> dict[str, dict[str, Any]]:
    if not raw_page_map:
        return {}

    try:
        parsed = json.loads(raw_page_map)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="page_map deve ser um JSON válido.")

    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="page_map deve ser um objeto JSON.")

    normalized: dict[str, dict[str, Any]] = {}
    for file_name, mapping in parsed.items():
        if isinstance(mapping, dict):
            normalized[file_name] = mapping
    return normalized


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


def generate_files(
        base_path: Path,
        chapters: list[Chapter],
        title: str,
        cover_metadata: Optional[CoverMetadata],
        page_map: Optional[dict[str, dict[str, Any]]] = None,
):
    effective_page_map = page_map or {}

    def find_page_map_for(file_name: str) -> dict[str, Any]:
        return effective_page_map.get(file_name) or effective_page_map.get(f"content/{file_name}") or {}

    content_dir = base_path / "content"
    toc_entries: list[tuple[str, str, str]] = []

    pre_textual_file = content_dir / "pre_textual.html"
    pre_textual_html = generate_pre_textual_html(title, cover_metadata or CoverMetadata(collection_title=title))
    pre_textual_page_map = find_page_map_for(pre_textual_file.name)
    pre_textual_file.write_text(
        inject_page_numbers(pre_textual_html, pre_textual_page_map),
        encoding="utf-8",
    )
    pre_textual_page, pre_textual_anchor = extract_primary_page_reference(pre_textual_page_map)
    pre_textual_href = f"content/{pre_textual_file.name}"
    if pre_textual_anchor:
        pre_textual_href = f"{pre_textual_href}#{pre_textual_anchor}"
    toc_entries.append(("Materiais pré-textuais", pre_textual_href, pre_textual_page or "—"))
    chapter_files: list[str] = []

    for index, chapter in enumerate(chapters, start=1):
        html_content = generate_content_html(
            chapter,
            title=title,
        )

        file_name = f"capitulo_{index:02}.html"
        content_file = content_dir / file_name
        chapter_page_map = find_page_map_for(file_name)
        content_file.write_text(
            inject_page_numbers(html_content, find_page_map_for(file_name)),
            inject_page_numbers(html_content, chapter_page_map),
            encoding="utf-8",
        )
        chapter_files.append(file_name)
        chapter_page, chapter_anchor = extract_primary_page_reference(chapter_page_map)
        chapter_href = f"content/{file_name}"
        if chapter_anchor:
            chapter_href = f"{chapter_href}#{chapter_anchor}"
        toc_entries.append((chapter.title, chapter_href, chapter_page or "—"))

    if cover_metadata is None:
        cover_metadata = CoverMetadata(collection_title=title)

    identifier = _build_unique_identifier(cover_metadata)

    index_html = generate_index_html(title, cover_metadata, toc_entries)
    (base_path / "index.html").write_text(
        inject_page_numbers(index_html, effective_page_map.get("index.html", {})),
        encoding="utf-8",
    )

    all_content_files = [pre_textual_file.name] + chapter_files

    (base_path / "toc.ncx").write_text(
        generate_toc_ncx(title, chapters, identifier),
        encoding="utf-8",
    )
    (base_path / "content.opf").write_text(
        default_content_opf(title, all_content_files, cover_metadata, identifier),
        encoding="utf-8",
    )

    write_placeholder_cover(base_path / "cover")


def create_pnld_package(base_path: Path, output_zip: Path) -> Path:
    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(base_path):
            for file in files:
                path = Path(root) / file
                zf.write(path, path.relative_to(base_path))
    return output_zip

def generate_toc_ncx(title: str, chapters: list[Chapter], package_uid: str) -> str:
    navpoints = []
    navpoints.append(
        "    <navPoint id=\"navpoint-1\" playOrder=\"1\">\n"
        "      <navLabel>\n"
        "        <text>Materiais pré-textuais</text>\n"
        "      </navLabel>\n"
        "      <content src=\"content/pre_textual.html\" />\n"
        "    </navPoint>"
    )

    for chapter_number, chapter in enumerate(chapters, start=1):
        chapter_order = chapter_number + 1
        navpoints.append(
            f"    <navPoint id=\"navpoint-{chapter_order}\" playOrder=\"{chapter_order}\">\n"
            f"      <navLabel>\n"
            f"        <text>{chapter.title}</text>\n"
            f"      </navLabel>\n"
            f"      <content src=\"content/capitulo_{chapter_number:02}.html\" />\n"
            f"    </navPoint>"
        )

    navpoints_str = "\n".join(navpoints)

    return (
        "<?xml version='1.0' encoding='UTF-8'?>\n"
        "<ncx xmlns=\"http://www.daisy.org/z3986/2005/ncx/\" version=\"2005-1\">\n"
        "  <head>\n"
        f"    <meta name=\"dtb:uid\" content=\"{package_uid}\" />\n"
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


def _build_unique_identifier(cover_metadata: CoverMetadata) -> str:
    if cover_metadata.isbn:
        normalized_isbn = re.sub(r"[^0-9Xx]", "", cover_metadata.isbn)
        if normalized_isbn:
            return f"urn:isbn:{normalized_isbn}"
    return f"urn:uuid:{uuid4()}"


def _build_publication_date(cover_metadata: CoverMetadata) -> str:
    if cover_metadata.publication_year and cover_metadata.publication_year.isdigit():
        return f"{cover_metadata.publication_year}-01-01"
    return datetime.utcnow().date().isoformat()


def _build_description(cover_metadata: CoverMetadata) -> str:
    return cover_metadata.expression or "Descrição não informada"


def default_content_opf(
        title: str,
        content_files: list[str],
        cover_metadata: CoverMetadata,
        identifier: str,
) -> str:
    manifest_items = [
        "    <item id=\"index\" href=\"index.html\" media-type=\"application/xhtml+xml\" properties=\"nav\" />"
    ]
    spine_items = ["    <itemref idref=\"index\" />"]

    for file_name in content_files:
        item_id = Path(file_name).stem
        manifest_items.append(
            f"    <item id=\"{item_id}\" href=\"content/{file_name}\" media-type=\"application/xhtml+xml\" />"
        )
        spine_items.append(f"    <itemref idref=\"{item_id}\" />")

    manifest_items.append("    <item id=\"toc\" href=\"toc.ncx\" media-type=\"application/x-dtbncx+xml\" />")
    manifest_items.append("    <item id=\"cover\" href=\"cover\" media-type=\"image/jpeg\" />")

    manifest_block = "\n".join(manifest_items)
    spine_block = "\n".join(spine_items)

    creator = cover_metadata.authors_text()
    publisher = cover_metadata.editor or "Editor não informado"
    publication_date = _build_publication_date(cover_metadata)
    description = _build_description(cover_metadata)

    return (
        "<?xml version='1.0' encoding='UTF-8'?>\n"
        f"<package version=\"{OPF_VERSION}\" xmlns=\"http://www.idpf.org/2007/opf\" unique-identifier=\"BookId\">\n"
        "  <metadata xmlns:dc=\"http://purl.org/dc/elements/1.1/\" xmlns:opf=\"http://www.idpf.org/2007/opf\">\n"
        f"    <dc:title>{title}</dc:title>\n"
        f"    <dc:identifier id=\"BookId\">{identifier}</dc:identifier>\n"
        f"    <dc:language>pt-BR</dc:language>\n"
        f"    <dc:creator>{creator}</dc:creator>\n"
        f"    <dc:publisher>{publisher}</dc:publisher>\n"
        f"    <dc:date>{publication_date}</dc:date>\n"
        f"    <dc:description>{description}</dc:description>\n"
        "    <meta property=\"schema:accessibilityFeature\">structuralNavigation</meta>\n"
        "    <meta property=\"schema:accessibilityFeature\">tableOfContents</meta>\n"
        "    <meta property=\"schema:accessibilityAPI\">ARIA</meta>\n"
        "  </metadata>\n"
        "  <manifest>\n"
        f"{manifest_block}\n"
        "  </manifest>\n"
        "  <spine>\n"
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
