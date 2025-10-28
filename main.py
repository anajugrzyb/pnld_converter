import os
import shutil
import zipfile
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException
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
async def convert_pdf(file: UploadFile = File(...)):
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

    html_content = generate_html5(text, title=file.filename.replace(".pdf", ""))

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


def generate_html5(text: str, title: str = "PNLD Work") -> str:
    soup = BeautifulSoup("", "html.parser")
    doctype = "<!DOCTYPE html>"

    html = soup.new_tag("html", lang="pt-br")
    head = soup.new_tag("head")
    head.append(soup.new_tag("meta", charset="UTF-8"))
    head.append(soup.new_tag("meta", attrs={"name": "robots", "content": "noindex, nofollow"}))

    title_tag = soup.new_tag("title")
    title_tag.string = title
    head.append(title_tag)
    html.append(head)

    body = soup.new_tag("body")
    main = soup.new_tag("main")
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


def create_pnld_package(base_path: Path, output_zip: Path):
    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(base_path):
            for file in files:
                path = Path(root) / file
                zf.write(path, path.relative_to(base_path))
