# PNLD Converter API
API desenvolvida com FastAPI para converter arquivos PDF em pacotes no formato .pnld.

## Funcionalidades
- Upload de arquivos PDF
-  Extração de texto via pdfminer
-  Geração automática da estrutura de pastas PNLD
-  Criação de um index.html com o conteúdo extraído
-  Empacotamento final em um arquivo .pnld (ZIP)
-  Testes

## Tecnologias utilizadas
[FastAPI](https://fastapi.tiangolo.com/)
 — Framework principal da API
 
[pdfminer.six](https://github.com/pdfminer/pdfminer.six)
 — Extração de texto de PDFs
 
 [BeautifulSoup4](https://www.crummy.com/software/BeautifulSoup/)
 — Geração de HTML
 
 [pytest](https://docs.pytest.org/en/stable/)
 — Testes automatizados
 
 [Uvicorn](https://uvicorn.dev/)
 — Servidor ASGI para rodar a aplicação

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
