# DocuMind — Tutor acadêmico com RAG (Gemini)

## Executar
```bash
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                 # edite e coloque sua GEMINI_API_KEY
python -m uvicorn app.main:app --reload --port 8000
```
Abra http://localhost:8000 (chave gratuita em https://aistudio.google.com/apikey).
Requer Python 3.10+.
