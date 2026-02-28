# claude-cli-proxy

A lightweight FastAPI proxy that exposes an OpenAI-compatible `/v1/chat/completions` endpoint and routes all requests to the local Claude CLI instead of a paid API. Lets any OpenAI-compatible client (OpenClaw, LiteLLM, curl, etc.) use Claude at zero marginal cost with a Claude Pro or Max subscription.

## How It Works

```
Client (OpenClaw, curl, etc.)
  → POST /v1/chat/completions  (OpenAI format)
  → claude-proxy.py            (FastAPI, port 19000, loopback only)
  → subprocess: claude --print
  → Claude CLI                 (Claude Pro/Max, $0 per token)
  → response wrapped in OpenAI JSON → back to client
```

The proxy is stateless — the caller sends the full conversation history each request. It supports both streaming and non-streaming responses.

---

## Prerequisites

- **OS:** Ubuntu 20.04+ or Debian 11+ (any Linux with systemd)
- **Python:** 3.11 or newer (`python3 --version`)
- **Claude Code CLI:** installed and authenticated (see below)
- **Subscription:** Claude Pro or Max

### Install Claude Code CLI

Follow the [official Claude Code installation guide](https://docs.anthropic.com/en/docs/claude-code). After installing, authenticate:

```bash
claude auth login
```

Verify it works:

```bash
echo "say hello" | claude --print
```

You should get a response back. If this doesn't work, the proxy won't work either — fix this first.

Find the path to the binary (you'll need it in step 4):

```bash
which claude
# typically: /home/youruser/.local/bin/claude
```

---

## Installation

### Step 1 — Clone the repo

```bash
git clone https://github.com/schaef1/claude-cli-proxy.git ~/claude-cli-proxy
cd ~/claude-cli-proxy
```

### Step 2 — Create a virtual environment and install dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Step 3 — Create a workspace directory

The proxy runs the Claude CLI from a working directory. Create it:

```bash
mkdir -p ~/workspace
```

> You can use any directory. The default in `claude-proxy.py` is `~/workspace` — adjust if needed.

### Step 4 — Configure paths in claude-proxy.py

Open `claude-proxy.py` and update these two lines near the top to match your system:

```python
CLAUDE_CLI = "/home/youruser/.local/bin/claude"   # output of: which claude
```

And in `call_claude()`:

```python
cwd="/home/youruser/workspace",   # working directory for the CLI
```

Replace `youruser` with your actual Linux username (`whoami`).

### Step 5 — Test it manually

```bash
source venv/bin/activate
python claude-proxy.py
```

In a second terminal:

```bash
curl -s http://127.0.0.1:19000/
# → {"status":"Claude Code Proxy running"}

curl -s http://127.0.0.1:19000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-local","messages":[{"role":"user","content":"say hi"}]}'
```

You should get a valid OpenAI-format JSON response with Claude's reply. Stop the test server with `Ctrl+C` when done.

### Step 6 — Install as a systemd user service

```bash
mkdir -p ~/.config/systemd/user
cp claude-proxy.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now claude-proxy
```

Check it's running:

```bash
systemctl --user status claude-proxy
```

View live logs:

```bash
journalctl --user -u claude-proxy -f
```

### Step 7 — Verify end-to-end

```bash
curl -s http://127.0.0.1:19000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-local","messages":[{"role":"user","content":"what is 2+2?"}]}'
```

The `content` field in the response should contain Claude's answer.

---

## OpenClaw Integration

Copy the provider config:

```bash
cp openclaw/models.json ~/.openclaw/agents/main/agent/models.json
```

Set as the default model:

```bash
openclaw models set local/claude-local
```

The proxy registers as provider `local`, model `claude-local`, base URL `http://127.0.0.1:19000/v1`.

---

## Service Management

```bash
# Status
systemctl --user status claude-proxy

# Restart (required after any code change)
systemctl --user restart claude-proxy

# Stop / Start
systemctl --user stop claude-proxy
systemctl --user start claude-proxy

# Live logs
journalctl --user -u claude-proxy -f

# Logs since last boot
journalctl --user -u claude-proxy -b
```

---

## Deployment Workflow

The repo is the source of truth. Edit locally, push to GitHub, pull on the server.

**On your dev machine:**

```bash
git add -A
git commit -m "describe your change"
git push origin main
```

**On the server:**

```bash
cd ~/claude-cli-proxy
git pull origin main
systemctl --user restart claude-proxy
```

---

## Testing with REST Client (VS Code)

Install the [REST Client](https://marketplace.visualstudio.com/items?itemName=humao.rest-client) extension, then open `test.http`. Click **Send Request** above any block to run it against the proxy.

---

## Troubleshooting

**Proxy starts but Claude returns empty output**
- Run `echo "test" | claude --print` manually. If it fails, re-authenticate: `claude auth login`

**Service fails to start**
- Check logs: `journalctl --user -u claude-proxy -b`
- Confirm the venv exists: `ls ~/claude-cli-proxy/venv/bin/python3`
- Confirm paths in `claude-proxy.py` match your system

**Port 19000 already in use**
- Find and kill the old process: `lsof -i :19000` then `kill <PID>`

**Client gets `content: []` instead of a response**
- Check proxy logs for `TELEGRAM_OUT` to confirm the proxy is returning content
- The issue is likely in the client/gateway, not the proxy
