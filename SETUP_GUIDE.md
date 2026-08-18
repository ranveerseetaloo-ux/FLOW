# PipeCore — Beginner Setup Guide

**Goal:** run the **backend** (the API + database) on a **server VM**, and do
**frontend** work (the dashboard) on **your laptop**, with the two talking to
each other.

This guide assumes you have never done this before. Every command is spelled
out. Read the short "What this does" notes so you understand *why*, not just
*what*. Follow the parts in order. There are **checkpoints** — don't move on
until a checkpoint passes.

---

## 0. The big picture (read this first)

You have two computers:

```
   YOUR LAPTOP                          YOUR SERVER VM
   (frontend dev)                       (backend host)
   ┌───────────────────┐   internet     ┌────────────────────────────┐
   │  Web browser       │  ───────────▶  │  PipeCore API (FastAPI)     │
   │  dashboard         │   HTTP :8000   │  runs on port 8000          │
   │  (ui/index.html)   │  ◀───────────  │  database (SQLite to start) │
   │  code editor       │                │  Python virtual environment │
   └───────────────────┘                └────────────────────────────┘
```

- The **backend** is the "brain": it stores customers/pipes, compiles shaping
  policy, and answers questions over the network on **port 8000**.
- The **frontend** is just an HTML page your browser runs. It makes requests to
  the backend's address.
- They connect over the network using the server's **IP address** and port 8000.

**Key idea for a newbie:** you don't need the fancy databases (PostgreSQL,
ClickHouse) to start. PipeCore falls back to a built-in file database (SQLite)
and sample report data. So we get it running the *easy* way first, then add the
real databases later (Part 4).

**What you need before starting:**

1. A **server VM** running **Ubuntu** (22.04 or 24.04). This can be from any
   cloud (AWS, DigitalOcean, Hetzner, Azure, a local VM in VirtualBox, etc.).
   You need its **public IP address** and a **username** (often `ubuntu` or
   `root`) and either a password or an SSH key.
2. **Your laptop** (Windows or Mac).
3. The **`pipecore.zip`** file I gave you.

Throughout this guide, wherever you see **`SERVER_IP`**, replace it with your
server's real IP address (for example `203.0.113.9`). Wherever you see
**`youruser`**, replace it with your real server username.

---

## Part 1 — Set up the backend on the server VM

### 1.1 Connect to your server with SSH

SSH is how you get a command line *on the server* from your laptop.

**On Mac:** open the **Terminal** app.
**On Windows:** open **PowerShell** (press Start, type "PowerShell", Enter).

Then type (replacing the placeholders):

```bash
ssh youruser@SERVER_IP
```

The first time it asks "Are you sure you want to continue connecting?" — type
`yes` and Enter. Enter your password if prompted (the password is invisible as
you type — that's normal).

**What this does:** gives you a command prompt that is running *on the server*.
From now on in Part 1, you are typing commands on the server, not your laptop.
You'll know you're connected because the prompt changes to something like
`youruser@myserver:~$`.

> If `ssh` on Windows says "command not found", install the free tool **PuTTY**,
> or enable OpenSSH (Settings → Apps → Optional features → Add → OpenSSH Client).

### 1.2 Install the basic tools

Copy-paste this whole block and press Enter:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip unzip
```

**What this does:** `apt` is Ubuntu's app installer. This installs Python (the
language the backend is written in), the "venv" tool (explained next), pip
(Python's package installer), and `unzip`. `sudo` means "run as administrator";
it may ask for your password.

### 1.3 Get the PipeCore code onto the server

You have `pipecore.zip` on your laptop. We need to copy it to the server.

**Open a SECOND terminal window on your laptop** (leave the SSH one open). In
this new one you are on your *laptop*. Navigate to wherever the zip is (e.g. your
Downloads folder) and send it to the server:

```bash
cd Downloads
scp pipecore.zip youruser@SERVER_IP:~
```

**What this does:** `scp` = "secure copy". It copies `pipecore.zip` to the
server's home folder (`~` means home). Enter your password if asked.

Now go **back to your SSH terminal** (the one on the server) and unzip it:

```bash
cd ~
unzip pipecore.zip
cd pipecore
ls
```

**What this does:** unzips the project and enters its folder. `ls` lists the
contents — you should see `control-plane`, `data-plane`, `ui`, `README.md`, etc.

> **Alternative (if you use GitHub):** instead of scp, you could
> `git clone <your-repo-url>`. For now, scp is simplest.

### 1.4 Create a Python virtual environment

```bash
cd ~/pipecore
python3 -m venv .venv
source .venv/bin/activate
```

**What this does:** a "virtual environment" is a private, clean box for this
project's Python packages, so they never clash with the rest of the system.
`source .venv/bin/activate` switches into that box — your prompt now starts with
`(.venv)`. **Whenever you come back later to run the backend, you must run
`source .venv/bin/activate` again first.**

### 1.5 Install the backend's packages

```bash
pip install -r control-plane/requirements.txt
```

**What this does:** downloads and installs everything the backend needs
(FastAPI, the web server, etc.). This takes a minute or two. It's normal to see
lots of "Collecting..." and "Installing..." lines.

> If it fails with an error mentioning a compiler, run
> `sudo apt install -y build-essential libffi-dev python3-dev` and then repeat
> the `pip install` command.

### 1.6 Start the backend (first run)

```bash
cd ~/pipecore/control-plane
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**What this does:** starts the API. You should see lines ending in
`Application startup complete.` and
`Uvicorn running on http://0.0.0.0:8000`.

- `--host 0.0.0.0` is **important**: it means "accept connections from other
  computers" (i.e. your laptop). Without it, only the server itself could reach
  it.
- On first start it automatically creates a SQLite database file and fills it
  with demo data (a few customers and pipes).

**Leave this running.** It occupies the terminal. To stop it later you press
`Ctrl + C`. (In Part 3 we make it run permanently in the background.)

### 1.7 Open the firewall / cloud security group

Two firewalls may block port 8000. Open both.

**A) Ubuntu's own firewall** — open a *new* SSH terminal to the server (or press
Ctrl+C to stop the server briefly, run these, then start it again):

```bash
sudo ufw allow 22
sudo ufw allow 8000
sudo ufw --force enable
```

**What this does:** allows SSH (port 22, so you don't lock yourself out) and the
API (port 8000).

**B) Your cloud provider's firewall ("Security Group" / "Firewall rules").**
This is on the cloud's website, not the server. In your provider's dashboard,
find your VM's firewall/security-group settings and **add an inbound rule
allowing TCP port 8000** from your IP (or from anywhere, `0.0.0.0/0`, for
testing). AWS calls this a Security Group; DigitalOcean/Hetzner call it a
Firewall; Azure calls it a Network Security Group.

> If you skip step B on a cloud VM, your laptop will "hang" trying to connect.
> This is the #1 beginner gotcha.

### ✅ Checkpoint 1 — is the backend reachable?

Make sure the backend is running (step 1.6). Then **on your laptop**, open a web
browser and go to:

```
http://SERVER_IP:8000/docs
```

You should see an interactive **API documentation** page (Swagger UI) listing
endpoints like `/api/auth/token`, `/api/pipes`, `/api/customers`. 🎉

Also try `http://SERVER_IP:8000/` — you should see the **PipeCore dashboard**
served directly by the server (login with `admin` / `admin`). This proves the
whole backend works end-to-end before you even touch laptop frontend dev.

**If the page doesn't load:** re-check 1.6 (is it running with `--host
0.0.0.0`?), 1.7A (ufw), and especially 1.7B (cloud security group). See the
Troubleshooting section at the end.

---

## Part 2 — Set up the frontend on your laptop

The dashboard is a single file, `ui/index.html`. For real development you'll
edit it on your laptop and run it locally, pointed at your server's API.

### 2.1 Install a code editor

Install **Visual Studio Code** (free): https://code.visualstudio.com/ — download,
install, open it.

### 2.2 Get the project onto your laptop

Unzip `pipecore.zip` on your laptop too (double-click it). In VS Code choose
**File → Open Folder** and open the unzipped `pipecore` folder.

### 2.3 Point the frontend at your server (one small edit)

Open `ui/index.html` in VS Code. Near the top of the `<script>` section (around
line 106 — use Ctrl+F / Cmd+F and search for `API_BASE`) you'll find this config
block:

```javascript
const API_BASE = "";
```

Change it to your server's address:

```javascript
const API_BASE = "http://SERVER_IP:8000";
```

(Use your real IP, e.g. `"http://203.0.113.9:8000"`.) Save the file (Ctrl+S /
Cmd+S).

**What this does:** tells the dashboard running on your laptop where to send its
requests — to your server, instead of to itself.

> Remember: when you're *finished* and want the server to serve the page itself
> again, set it back to `""`. Blank means "same computer that served this page".

### 2.4 Run the frontend locally

You can't just double-click the HTML (browsers block some requests from
`file://` pages). Serve it with a tiny local web server. Two easy options:

**Option A — VS Code "Live Server" (recommended):**
1. In VS Code, click the Extensions icon (left sidebar), search **"Live Server"**
   (by Ritwick Dey), click **Install**.
2. Open `ui/index.html`, then click **"Go Live"** in the bottom-right status bar.
3. Your browser opens something like `http://127.0.0.1:5500/ui/index.html`.
   Editing the file and saving now auto-refreshes the browser.

**Option B — Python (if you have Python on your laptop):**
```bash
cd pipecore/ui
python -m http.server 5500
```
Then open `http://localhost:5500` in your browser.

### 2.5 Log in and confirm it works

In the dashboard that opened, log in with **admin / admin**. You should see the
pipes, IP groups, the "Compile → tc" button producing shaping commands, and the
traffic report. This data is coming **from your server** — you're now doing
laptop frontend dev against the remote backend.

### ✅ Checkpoint 2 — full split setup working

- Backend running on the server (Part 1).
- Dashboard running on your laptop via Live Server, `API_BASE` set to your
  server, logged in, data visible.

If login fails or data is empty, open the browser's **Developer Tools** (press
F12) → **Console** tab, and look for red errors. A "CORS" or "Failed to fetch"
error almost always means `API_BASE` is wrong or the server firewall (1.7) is
still blocking. See Troubleshooting.

---

## Part 3 — Keep the backend running 24/7

Right now the backend stops when you close the SSH window. Let's make it a proper
background **service** that starts on boot and restarts if it crashes.

On the server (SSH), create a service file:

```bash
sudo nano /etc/systemd/system/pipecore.service
```

`nano` is a simple text editor. Paste this (change `youruser` in **all three**
places to your real username):

```ini
[Unit]
Description=PipeCore control plane
After=network.target

[Service]
User=youruser
WorkingDirectory=/home/youruser/pipecore/control-plane
Environment="PIPECORE_JWT_SECRET=please-change-this-to-a-long-random-string"
ExecStart=/home/youruser/pipecore/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Save and exit nano: press **Ctrl+O**, then **Enter**, then **Ctrl+X**.

Now enable and start it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable pipecore
sudo systemctl start pipecore
sudo systemctl status pipecore
```

**What this does:** `enable` makes it start automatically when the server boots;
`start` runs it now; `status` shows if it's healthy (look for a green
**active (running)**). Press `q` to exit the status view.

Useful later:
- See live logs: `journalctl -u pipecore -f` (Ctrl+C to stop watching)
- Restart after you change backend code: `sudo systemctl restart pipecore`
- Stop it: `sudo systemctl stop pipecore`

You can now close your SSH window and the backend keeps running.

---

## Part 4 — (Later) Add the real databases with Docker

SQLite and sample reports are perfect for learning. When you want real
PostgreSQL (config storage) and ClickHouse (traffic reporting), use Docker.

On the server:

```bash
# install Docker (one time)
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
# log out and back in (close SSH, reconnect) so the group change applies
```

Then start just the two databases:

```bash
cd ~/pipecore
docker compose up -d postgres clickhouse
```

**What this does:** `-d` runs them in the background. `docker compose` reads
`docker-compose.yml` and launches PostgreSQL and ClickHouse with the right
settings; ClickHouse auto-loads the reporting schema.

Now tell the backend to use them. Edit the service file
(`sudo nano /etc/systemd/system/pipecore.service`) and add two more
`Environment=` lines under the existing one:

```ini
Environment="PIPECORE_DB=postgresql+psycopg2://pipecore:pipecore@localhost:5432/pipecore"
Environment="PIPECORE_CLICKHOUSE=clickhouse://localhost:9000/pipecore"
```

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl restart pipecore
```

The backend now stores data in PostgreSQL and reads live traffic stats from
ClickHouse. (Until real flow data is ingested, reports still show sample data —
that's expected.)

> You do **not** need to run the backend itself inside Docker. Running it with
> systemd (Part 3) while only the databases are in Docker is simpler to learn and
> debug.

---

## Part 5 — Your day-to-day workflow

**Frontend change (on your laptop):**
1. Edit `ui/index.html` in VS Code.
2. Save. With Live Server, the browser auto-refreshes. Done — no server restart
   needed, because the frontend runs on your laptop.

**Backend change (Python files under `control-plane/` or `data-plane/`):**
1. Edit on your laptop, then copy the changed files to the server (scp again),
   **or** edit directly on the server with `nano`, **or** (best, later) use
   **git** to push/pull.
2. Restart the backend so it picks up changes:
   `sudo systemctl restart pipecore`.

**Tip for active backend development:** instead of the systemd service, you can
run it manually with auto-reload so it restarts itself on every save:
```bash
cd ~/pipecore/control-plane
source ~/pipecore/.venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
Use `--reload` only during development, never for the permanent service.

**Recommended next step — use Git** so you stop copying zip files around:
create a free private repo on GitHub, `git init` in the `pipecore` folder on your
laptop, push it, then `git clone` it on the server. After that, your workflow is
`git push` (laptop) → `git pull` (server) → `sudo systemctl restart pipecore`.

---

## Part 6 — Security must-dos (before real traffic ever touches this)

This setup is for **learning/development**. Before it goes anywhere near a real
network:

1. **Change the admin password.** The seeded `admin/admin` is public knowledge.
2. **Set a strong `PIPECORE_JWT_SECRET`** (a long random string) — done in the
   service file in Part 3. This signs login tokens.
3. **Don't expose port 8000 to the whole internet.** In your cloud firewall,
   restrict inbound 8000 to *your* IP only, or keep the API on a private network
   and reach it over a VPN.
4. **Add HTTPS** eventually (put nginx + a free Let's Encrypt certificate in
   front). Plain HTTP sends passwords unencrypted.
5. **Keep `PIPECORE_DRY_RUN=true`** until you have fail-to-wire bypass and HA
   (from the feasibility plan). Dry-run means it *computes* shaping but never
   pushes it to a live link — so it can't accidentally take a network down.

---

## Troubleshooting cheat sheet

| Symptom | Most likely cause | Fix |
|---|---|---|
| Browser hangs / can't reach `SERVER_IP:8000/docs` | Cloud firewall blocks 8000 | Add inbound TCP 8000 rule in your cloud dashboard (1.7B) |
| `docs` works on the server itself but not from laptop | Started without `--host 0.0.0.0`, or ufw | Use `--host 0.0.0.0` (1.6); `sudo ufw allow 8000` (1.7A) |
| Dashboard on laptop shows blank / login fails | `API_BASE` wrong or has a typo/trailing slash | Set `API_BASE="http://SERVER_IP:8000"` exactly, save, refresh (2.3) |
| Browser console shows **CORS** error | Wrong API address, or hitting `https` instead of `http` | Use `http://` and the exact IP:port; the backend already allows cross-origin |
| `pip install` fails mentioning a compiler | Missing build tools | `sudo apt install -y build-essential libffi-dev python3-dev`, retry |
| `uvicorn: command not found` | venv not activated | `source ~/pipecore/.venv/bin/activate` first |
| Service won't start (`systemctl status` red) | Wrong path/username in service file | Check the three `youruser` spots and the venv path; `journalctl -u pipecore -e` for the error |
| Backend "forgets" everything on restart | Using SQLite (a file) — that's fine for dev | It persists in `control-plane/pipecore.db`; move to PostgreSQL (Part 4) for production |

---

## One-page quick reference

**Server (SSH in first: `ssh youruser@SERVER_IP`):**
```bash
# start backend manually (dev)
cd ~/pipecore/control-plane && source ~/pipecore/.venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# as a permanent service
sudo systemctl start|stop|restart|status pipecore
journalctl -u pipecore -f          # live logs
```

**Laptop:**
```bash
# edit ui/index.html  -> set API_BASE="http://SERVER_IP:8000"
# then in VS Code click "Go Live", or:
cd pipecore/ui && python -m http.server 5500   # open http://localhost:5500
```

**URLs:**
- API docs: `http://SERVER_IP:8000/docs`
- Health check: `http://SERVER_IP:8000/api/health`
- Server-hosted dashboard: `http://SERVER_IP:8000/`
- Laptop dev dashboard: `http://localhost:5500`

Demo login: **admin / admin** (change it — Part 6).
