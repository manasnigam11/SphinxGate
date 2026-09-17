# SphinxGate Backend

FastAPI-based AI API gateway. Phase 1: real request routing through the Playground.

## Structure

```
backend/
├── app/
│   ├── main.py           — FastAPI app, CORS, routers
│   ├── config.py         — Settings via environment variables
│   ├── models.py         — Pydantic request/response models
│   ├── gateway/
│   │   └── router.py     — Core gateway routing logic
│   └── providers/
│       ├── base.py       — Abstract provider interface
│       └── openai.py     — OpenAI-compatible provider adapter
├── .env.example          — Required environment variables
├── pyproject.toml
└── README.md
```

## Setup

```bash
cd backend

# Create virtual environment
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate

# Install dependencies
pip install -e .

# Copy and fill in environment variables
cp .env.example .env
# Edit .env and add your provider API keys

# Run the dev server
uvicorn app.main:app --reload --port 8000
```

## Environment variables

See `.env.example` for all required variables.

## API

- `GET  /health`                     — Gateway health check
- `POST /api/v1/chat/completions`    — Chat completion (routed through gateway)
