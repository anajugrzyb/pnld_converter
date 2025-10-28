import io
import zipfile
from fastapi.testclient import TestClient
from main import app, TEMP_DIR, OUTPUT_NAME

client = TestClient(app)

def test_home_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    assert "PNLD Converter API" in response.json()["message"]


def test_invalid_file_upload():
    response = client.post("/convert", files={"file": ("fake.txt", b"not a pdf")})
    assert response.status_code == 400
    assert "valid PDF" in response.json()["detail"]


def test_pdf_conversion(monkeypatch):

    def mock_extract_text_from_pdf(_):
        return "Texto simulado do PDF."

    monkeypatch.setattr("main.extract_text_from_pdf", mock_extract_text_from_pdf)

    fake_pdf = io.BytesIO(b"%PDF-1.4 Fake content")
    response = client.post("/convert", files={"file": ("sample.pdf", fake_pdf, "application/pdf")})

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"

    output_path = TEMP_DIR / OUTPUT_NAME
    assert output_path.exists()

    with zipfile.ZipFile(output_path, "r") as z:
        files_inside = z.namelist()
        assert "index.html" in files_inside
        assert any("resources" in f for f in files_inside)


def test_generated_html_structure():
    from main import generate_html5

    html = generate_html5("Texto de teste", title="Obra Teste")
    assert "<!DOCTYPE html>" in html
    assert "<html" in html
    assert "<head>" in html
    assert "<body>" in html
    assert "Texto de teste" in html
    assert "Obra Teste" in html


def test_create_structure(tmp_path):
    from main import create_structure

    base_dir = tmp_path / "pnld_project"
    create_structure(base_dir)

    expected_dirs = [
        "content",
        "resources/images",
        "resources/styles",
        "resources/scripts",
        "resources/fonts",
    ]
    for folder in expected_dirs:
        assert (base_dir / folder).exists()


def test_create_pnld_package(tmp_path):
    from main import create_pnld_package

    base_dir = tmp_path / "pnld_project"
    base_dir.mkdir(parents=True, exist_ok=True)
    file_path = base_dir / "index.html"
    file_path.write_text("<html></html>", encoding="utf-8")

    output_zip = tmp_path / "output.pnld"
    create_pnld_package(base_dir, output_zip)

    assert output_zip.exists()
    with zipfile.ZipFile(output_zip, "r") as z:
        assert "index.html" in z.namelist()