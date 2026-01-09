# PNLD Converter API
API desenvolvida com FastAPI para converter arquivos PDF em pacotes no formato `.pnld`.

## Visão geral
Este serviço recebe PDFs, extrai o conteúdo e empacota tudo em um arquivo `.pnld` seguindo a estrutura exigida.

## Funcionalidades
- Upload de arquivos PDF.
- Extração de texto via `pdfminer.six`.
- Geração automática da estrutura de pastas PNLD.
- Criação de um `index.html` com o conteúdo extraído.
- Empacotamento final em um arquivo `.pnld` (ZIP).
- Cobertura de testes com `pytest`.

## Tecnologias utilizadas
[FastAPI](https://fastapi.tiangolo.com/) — framework principal da API.
- [pdfminer.six](https://github.com/pdfminer/pdfminer.six) — extração de texto de PDFs.
- [BeautifulSoup4](https://www.crummy.com/software/BeautifulSoup/) — geração de HTML.
- [pytest](https://docs.pytest.org/en/stable/) — testes automatizados.
- [Uvicorn](https://uvicorn.dev/) — servidor ASGI para rodar a aplicação.

## Instalação e execução
1. Clone o repositório

   git clone https://github.com/anajugrzyb/pnld_converter.git

   cd pnld_converter
3. Crie e ative um ambiente virtual
   python -m venv venv

   source venv/bin/activate  # Linux/Mac
   
   venv\Scripts\activate     # Windows
4. Instale as dependências

    pip install -r requirements.txt
6. Execute a API

    uvicorn main:app --reload
8. Acesse no navegador

    http://127.0.0.1:8000

   http://127.0.0.1:8000/docs
