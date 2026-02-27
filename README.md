# claude-cli-proxy

A lightweight FastAPI proxy that exposes an OpenAI-compatible `/v1/chat/completions` endpoint, but routes all requests to the local Claude CLI (`claude --print`) instead of a paid API. Lets any OpenAI-compatible client use Claude at zero marginal cost with a Claude Pro/Max subscription.

## Architecture

```
Client (OpenClaw, curl, etc.)
  → POST /v1/chat/completions  (OpenAI format)
  → claude-proxy.py            (FastAPI, port 19000, loopback only)
  → subprocess: claude --print
  → Claude CLI                 (Claude Pro/Max, $0 per token)
  → response wrapped in OpenAI JSON → back to client
```

## Requirements

- Python 3.11+
- [Claude Code CLI](https://claude.ai/code) installed and authenticated (`~/.local/bin/claude`)
- Claude Pro or Max subscription

## Installation (Ubuntu / Debian)

```bash
# Clone the repo
git clone https://github.com/schaef1/claude-cli-proxy.git ~/claude-cli-proxy
cd ~/claude-cli-proxy

# Create venv and install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Running

```bash
# One-off
python claude-proxy.py

# Or via systemd (see deploy section)
```

The proxy binds to `127.0.0.1:19000` only — never expose it publicly.

## Systemd Service

Copy and enable the service file:

```bash
mkdir -p ~/.config/systemd/user
cp claude-proxy.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now claude-proxy
```

Check status and logs:

```bash
systemctl --user status claude-proxy
journalctl --user -u claude-proxy -f
```

## Test It

```bash
curl -s http://127.0.0.1:19000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-local","messages":[{"role":"user","content":"say hi"}]}'
```

Or open `test.http` in VS Code with the [REST Client](https://marketplace.visualstudio.com/items?itemName=humao.rest-client) extension.

## OpenClaw Integration

```bash
# Copy the provider config
cp openclaw/models.json ~/.openclaw/agents/main/agent/models.json

# Set as default model
openclaw models set local/claude-local
```

## Deployment Workflow

```bash
# On dev machine — push changes
git add -A
git commit -m "your message"
git push origin main

# On server — pull and restart
cd ~/claude-cli-proxy
git pull origin main
systemctl --user restart claude-proxy
```
