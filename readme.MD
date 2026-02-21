# Topology JSON Builder

A browser-based visual editor for designing infrastructure topologies and exporting them as nested JSON. Built for teams who use infrastructure-as-code tools like Ansible, Terraform, or custom provisioning scripts.

---

## What is this?

You drag nodes onto a canvas, connect them, fill in their properties, and export a structured JSON file that mirrors how your infrastructure is actually nested — networks containing VMs, VMs containing databases, and so on.

The output JSON is designed to be consumed directly by Ansible playbooks, Terraform modules, or any other tooling that expects a structured description of your infrastructure.

```json
{
  "Production Network": {
    "type": "network",
    "cidr": "10.0.1.0/24",
    "zone": "private",
    "Web VM 1": {
      "type": "vm",
      "os": "Ubuntu 22.04",
      "cpu": "4 vCPU",
      "roles": ["nginx", "certbot", "fail2ban"],
      "App DB": {
        "type": "database",
        "engine": "PostgreSQL",
        "version": "15"
      }
    }
  }
}
```

---

## How it works

```
┌─────────────────────────────────────────────────────────────────┐
│                         Browser                                 │
│                                                                 │
│   ┌──────────┐   ┌──────────────────────┐   ┌───────────────┐  │
│   │ Palette  │   │   Canvas (HTML/JS)   │   │  JSON Output  │  │
│   │          │   │  nodes · edges · pan │   │  Property Ed. │  │
│   └──────────┘   └──────────────────────┘   └───────────────┘  │
│                             │                                   │
│                     fetch('/api/...')                           │
└─────────────────────────────┼───────────────────────────────────┘
                              │
┌─────────────────────────────┼───────────────────────────────────┐
│                     app.py (FastAPI)                            │
│                             │                                   │
│   ┌─────────────────────────▼──────────────────────────────┐   │
│   │  AppState                                              │   │
│   │  nodes · edges · node_types · rules · selected_id      │   │
│   └────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

The architecture is intentionally split into two completely independent layers:

- **`app.py`** owns all state and business logic. It is plain Python with no UI code whatsoever.
- **`static/index.html`** owns all rendering and interaction. It is a single HTML file with no build step and no npm dependencies.
- They communicate exclusively through a REST API (`/api/*`). Neither side knows anything about the other's internals.

This means you can modify the UI without touching Python, and add new backend logic without touching the frontend.

---

## Project structure

```
topology-builder/
├── app.py                 ← Python backend — edit DEFAULT_CONFIG here
├── requirements.txt       ← pip dependencies (fastapi, uvicorn)
├── Dockerfile
├── docker-compose.yml
├── static/
│   └── index.html         ← Complete frontend (single file, no build step)
└── nginx/
    ├── nginx.conf         ← Reverse proxy + TLS termination config
    ├── CERTS_README.md    ← Certificate setup instructions
    └── certs/             ← Place your cert.pem and key.pem here
```

---

## Running the app

### Without Docker

**Requirements:** Python 3.10 or newer.

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start the server
python app.py

# 3. Open in your browser
# http://localhost:8080
```

The server binds to `0.0.0.0:8080`, so it is also reachable from other devices on your local network via your machine's IP address.

To change the port, edit the last line of `app.py`:

```python
uvicorn.run(api, host="0.0.0.0", port=9000)
```

### With Docker

**Requirements:** Docker and Docker Compose.

**Step 1 — Add your TLS certificates** (see [Certificate setup](#certificate-setup) below)

**Step 2 — Build and start**

```bash
docker compose up -d
```

The app will be available at `https://your-server-ip` or `https://yourdomain.com`.

**Useful commands:**

```bash
# View live logs
docker compose logs -f

# Stop everything
docker compose down

# Rebuild after editing app.py or index.html
docker compose up -d --build

# Restart just the app without rebuilding
docker compose restart app

# Restart nginx (e.g. after renewing certificates)
docker compose restart nginx
```

---

## Certificate setup

Certificates live in `nginx/certs/`. Two files are required:

| File | Contents |
|---|---|
| `nginx/certs/cert.pem` | Your TLS certificate (or full chain) |
| `nginx/certs/key.pem`  | Your private key — keep this secret, never commit it |

### Option A — Let's Encrypt (internet-facing server, recommended)

```bash
# Install certbot on the host
apt install certbot

# Obtain a certificate (temporarily stop nginx if port 80 is in use)
certbot certonly --standalone -d yourdomain.com

# Symlink the files into the project
ln -s /etc/letsencrypt/live/yourdomain.com/fullchain.pem nginx/certs/cert.pem
ln -s /etc/letsencrypt/live/yourdomain.com/privkey.pem   nginx/certs/key.pem
```

Certbot installs a systemd timer that auto-renews certificates before they expire. After each renewal, nginx needs to reload to pick up the new cert. Add a post-renewal hook to do this automatically:

```bash
# Create /etc/letsencrypt/renewal-hooks/post/restart-nginx.sh
#!/bin/bash
cd /path/to/topology-builder && docker compose restart nginx
chmod +x /etc/letsencrypt/renewal-hooks/post/restart-nginx.sh
```

### Option B — Self-signed (internal / LAN use)

```bash
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout nginx/certs/key.pem \
  -out    nginx/certs/cert.pem \
  -subj   "/CN=topology-builder"
```

Browsers will show a certificate warning for self-signed certs. You can silence this by adding `cert.pem` to your OS trusted certificate store, or by using your organisation's internal CA.

### Secure the key file

```bash
chmod 600 nginx/certs/key.pem
```

---

## Configuring node types and rules

All default settings live in the `DEFAULT_CONFIG` block near the top of `app.py`. You do not need to understand the rest of the file to customise it.

### Adding or editing a node type

```python
"vm": {
    "label": "VM",
    "color": "#4ade80",   # any hex colour
    "icon":  "▣",         # any single unicode character
    "props": {
        "os": {
            "type":    "select",
            "label":   "Operating System",
            "default": "Ubuntu 22.04",
            "options": ["Ubuntu 22.04", "Debian 12", "Rocky Linux 9"]
        },
        "roles": {
            "type":    "multiselect",
            "label":   "Ansible Roles",
            "default": [],            # must be [] for multiselect
            "options": ["nginx", "docker", "postgresql", "certbot"]
        },
        "ip": {
            "type":    "text",
            "label":   "IP Address",
            "default": ""
        }
    }
}
```

### Field types

| Type | Renders as | JSON output |
|---|---|---|
| `text` | Text input | `"10.0.0.1"` |
| `number` | Number input | `"5432"` |
| `select` | Dropdown | `"PostgreSQL"` |
| `multiselect` | Toggle buttons | `["nginx", "docker"]` |

### Connection rules

Rules define which node types can be nested as children of which parent types.

```python
"rules": {
    "network":  ["vm", "container", "firewall"],  # VMs can go inside networks
    "vm":       ["database", "storage"],           # databases can go inside VMs
    "database": ["storage"],
    "storage":  []                                 # storage has no children
}
```

### Live editing vs. permanent config

You can edit node types and rules at runtime inside the app via **⚙ Settings**, without restarting anything. To make those changes permanent:

1. In Settings, click **↓ Export Config**
2. Open the downloaded `topology-settings.json`
3. Paste its contents into `DEFAULT_CONFIG` in `app.py`
4. Restart the app — all new sessions will start with your updated defaults

---

## Maintaining the app

### Canvas state is not persisted

Nodes and edges live in memory in the running Python process. Restarting the app or the Docker container clears the canvas. **Export your JSON before restarting.**

This is intentional — the app is a build tool for producing JSON files, not a persistent datastore.

### Updating Python dependencies

```bash
pip install --upgrade fastapi uvicorn
```

With Docker, just rebuild:

```bash
docker compose up -d --build
```

### Modifying the frontend

All frontend code is in `static/index.html`. It is vanilla HTML/CSS/JavaScript with no build step and no npm. Open it in any editor, save, and refresh your browser.

The file is organised in labelled sections you can search for:

| Section | What it contains |
|---|---|
| `<style>` | All CSS — layout, node cards, modals, animations |
| `API helpers` | `get`, `post`, `put`, `patch`, `del` wrappers around `fetch` |
| `GEOMETRY` | Node height calculation, port positions, bezier curve formula |
| `TRANSFORM` | Zoom and pan logic |
| `RENDER — NODES` | Builds node `div` elements and ports |
| `RENDER — EDGES` | Draws SVG bezier curves between nodes |
| `POLL` | Polls `/api/state` every 280ms and re-renders on version change |
| `JSON PANEL` | Right-panel JSON output with syntax highlighting |
| `PROPERTY EDITOR` | Right-panel property form for the selected node |
| `CANVAS EVENTS` | `mousedown`, `mousemove`, `mouseup`, `wheel`, keyboard |
| `PALETTE` | Left-sidebar node type buttons |
| `SETTINGS` | Settings modal: type list, schema editor, rules matrix |

### Adding a new API endpoint

All API routes live in `app.py` below the `# ── API ──` comment. Add new endpoints following the existing pattern:

```python
@api.get("/api/my-endpoint")
def my_endpoint():
    return {"data": state.nodes}
```

The frontend can then call it with:

```javascript
const data = await get('/api/my-endpoint');
```

---

## Canvas controls reference

| Action | How |
|---|---|
| Add node | Click a type button in the left palette |
| Move node | Click and drag the node card |
| Select node | Click the node |
| Deselect | Click the canvas background |
| Delete selected node | `Delete` or `Backspace` key, or **✕ DELETE NODE** toolbar button |
| Connect nodes | Drag from the **●** right port to the **○** left port of another node |
| Delete a connection | Hover the line → click the **✕** at its midpoint |
| Pan canvas | Click-and-drag the background, or middle-mouse drag |
| Zoom | Scroll wheel, or the `+` / `−` buttons (bottom right) |
| Reset zoom & position | Click the `%` percentage display |

---

## Tech stack

| Layer | Technology | Reason |
|---|---|---|
| Backend | Python + FastAPI | Readable, easy to extend, no magic |
| Frontend | Vanilla HTML/CSS/JS | No build step, no framework to fight |
| Reverse proxy | nginx | TLS termination, production-standard |
| Containers | Docker + Compose | One-command deployment on any Linux server |
| Fonts | IBM Plex Mono, Orbitron | Monospace for data; Orbitron for headings |

---

