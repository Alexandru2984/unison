# Distributed Idea Evolution Engine

A unique web application showcasing Unison's deterministic execution and content-addressed code.

## 🌟 Why Unison?

Unison is fundamentally different from traditional programming languages:
- **Content-Addressed Code:** Functions and data are identified by a cryptographic hash of their abstract syntax tree, not by a text-based file name. This means no dependency conflicts and trivial refactoring.
- **Deterministic Evolution:** Each idea mutation is a pure function. Given the same idea and the same function hash, the output is guaranteed to be identical every time. This enables reliable, exact replay of the idea evolution tree.
- **Distributed Ready:** Because code is immutable and content-addressed, functions can be serialized and sent across nodes over a network, making the system naturally distributed.

## 🏗 Architecture

- **Core Engine (Unison):** Handles pure, side-effect-free transformations of textual ideas. Compiles to `.uc` format.
- **Web Wrapper (Python / FastAPI):** Acts as an API Gateway, managing SQLite database persistence and orchestrating Unison code via the command line. It also provides WebSocket streaming for real-time live graph updates.
- **Frontend (React / Vite):** Visualizes the idea tree and the timeline of changes deterministically computed by Unison using `reactflow`.
- **Infrastructure:** Secured via `Certbot`/`LetsEncrypt`, proxied through `Nginx` and process-managed by `systemd`.

## 🚀 Key Features

* **Evolution Graph:** Visualize ideas as they branch and evolve into multiple paths.
* **Deterministic Computations:** All mutative actions triggered on the frontend compute an exact result through the backend via the pure Unison script.
* **Real-time Live Sync:** The frontend uses WebSockets to seamlessly sync and render graph changes instantly across multiple browsers.
* **Smart Port Management:** Deployment scripts automatically traverse and resolve to a free dynamic port, ensuring zero process conflicts on shared servers.

## 🛠 Local Development Setup

### 1. Requirements
* Node.js & npm
* Python 3
* `ucm` (Unison Codebase Manager)

### 2. Frontend
```bash
cd frontend
npm install
npm run dev
```

### 3. Backend
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt # (or manually install fastapi uvicorn websockets python-dotenv sqlite3-api pydantic)
uvicorn main:app --reload --port 8080
```

### 4. Unison Codebase
The Unison code logic resides in `unison/evolution.u`. Whenever you alter the mutations, you need to load and recompile using `ucm`:
```bash
ucm -C ./unison
> load evolution.u
> update
> compile main evolution.uc
```

## 🌐 Production Deployment

The project can be deployed easily on a Debian/Ubuntu machine using the automated script:
```bash
sudo ./deploy.sh
```

**What deploy.sh does:**
1. Searches dynamically for an unused backend port (e.g. 8088).
2. Rewrites Nginx config and startup scripts to utilize the fresh port.
3. Reloads systemd and restarts the backend process in background.
4. Secures the Nginx reverse proxy with a free SSL certificate from Let's Encrypt (Certbot).