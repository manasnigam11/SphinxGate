<div align="center">
  <h1>🛡️ SphinxGate</h1>
  <p><strong>Enterprise AI & API Reliability Gateway</strong></p>
  <p>
    <a href="#features">Features</a> • 
    <a href="#architecture">Architecture</a> • 
    <a href="#quick-start">Quick Start</a> • 
    <a href="#tech-stack">Tech Stack</a>
  </p>
</div>

---

## ⚡ What is SphinxGate?

Modern applications rely heavily on external Generative AI models (OpenAI, Gemini, Groq) and public APIs. However, these external dependencies frequently suffer from **latency spikes, strict rate limits (429s), and hard outages**. If they fail, your application crashes.

**SphinxGate** acts as a fault-aware intermediary shield. When an upstream provider becomes slow or unavailable, SphinxGate detects the failure, protects the provider from "retry storms" via a **Circuit Breaker**, and transparently routes your request to a **Fallback Provider** (including local offline LLMs). 

*Principle: "Failure is inevitable and acceptable. Silent failure and cascading failures are not."*

---

## ✨ Key Features

- **Multi-Cloud LLM Fallback:** Seamlessly cascade traffic between OpenAI, Google Gemini, and Groq based on dynamic policy chains.
- **Local LLM Rescue:** If the internet entirely drops, SphinxGate can route traffic to an offline, local model (via Ollama) as the ultimate safety net.
- **Resilience Engine:** Implements battle-tested distributed systems patterns:
  - **Exponential Backoff & Retries** for Server Errors (503, 504).
  - **Circuit Breaking** to fast-fail and prevent retry storms.
  - **Active Health Probing** to safely recover circuits in the background.
- **Incident Intelligence (AI Copilot):** Automatically detects outages via asynchronous telemetry and uses a Gemini-powered Copilot to generate instant Root Cause Analysis (RCA) reports based on telemetry metadata.
- **Fault Injection (Chaos Engineering):** Simulate 503s, 504s, and 429s instantly via the dashboard to prove your resilience strategy works without turning off your Wi-Fi.

---

## 🏗️ Architecture & Philosophy

SphinxGate uses a strict, unidirectional data pipeline:

1. **Client Request:** A client sends a standard OpenAI-formatted request to the Gateway (`/api/v1/chat/completions`).
2. **Resilience Engine:** Evaluates the health of the requested provider.
3. **Provider Adapter:** The engine delegates the network call to stateless adapters (e.g., `GeminiProvider`), converting the unified OpenAI payload into the specific provider's required schema.
4. **Recovery / Telemetry:** If an error occurs, the engine classifies it, retries it, or routes to a fallback. Telemetry is emitted asynchronously to local storage to avoid blocking the client.

<div align="center">
  <img src="https://via.placeholder.com/800x400/111827/ffffff?text=Client+->+Resilience+Engine+->+Circuit+Breaker+->+Provider+Adapters" alt="Architecture Flow" />
</div>

---

## 🚀 Quick Start

### 1. Prerequisites
- [Docker](https://www.docker.com/) (Recommended) OR Python 3.11 & Node.js 20
- (Optional) [Ollama](https://ollama.com/) if you want to test the Local LLM fallback.

### 2. Setup Environment Variables
Clone the repository and set up your `.env` file in the `backend/` directory:

```bash
cd backend
cp .env.example .env
```
Edit `.env` and add your API keys:
```env
OPENAI_API_KEY="sk-proj-..."
GEMINI_API_KEY="AIzaSy..."
GROQ_API_KEY="gsk_..."

# To enable Local Offline LLM Fallback:
LOCAL_LLM_ENABLED=true
LOCAL_LLM_MODEL="llama3.2"
```

### 3. Run the Application
You can run the backend and frontend separately for development:

**Backend (Terminal 1):**
```bash
cd backend
pip install uv
uv pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
```

**Frontend (Terminal 2):**
```bash
cd frontend
npm install
npm run dev
```

The Dashboard will be available at: `http://localhost:5173`

---

## 🛠️ Tech Stack

- **Backend:** Python 3.11, FastAPI, `httpx` (Async HTTP), Pydantic
- **Frontend:** React 18, Vite, Tailwind CSS, TypeScript, Framer Motion
- **Testing & CI:** Pytest, GitHub Actions, Gitleaks (Secret Scanning)
- **Runtime:** Uvicorn, Docker (Multi-stage `uv`-optimized builds)

---

## 🔒 Security Notice

**DO NOT COMMIT API KEYS.** 
SphinxGate's CI/CD pipeline utilizes `Gitleaks`. If you accidentally push a commit containing an OpenAI or Google API key, the build will automatically fail. 

The React Frontend never touches API keys. All keys are securely stored on the backend, ensuring users cannot extract them via browser developer tools.

---

## 🧪 Testing

The backend contains a heavy suite of mocked resilience tests to prove the fallback engine works securely.
```bash
cd backend
pytest
```

---

<div align="center">
  <i>Built to ensure that when APIs go down, your application stays up.</i>
</div>
