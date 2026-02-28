#!/usr/bin/env python3
"""
Claude Code Proxy — makes OpenClaw talk to local Claude Code CLI
Speaks OpenAI API format, routes to ~/.local/bin/claude --print
Zero per-token cost (uses Claude Pro subscription)
"""

import json
import subprocess
import time
import uuid
import logging
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
from typing import Optional, Union

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("claude-proxy")

app = FastAPI()

CLAUDE_CLI = "/home/rob/.local/bin/claude"

class Message(BaseModel):
    model_config = ConfigDict(extra="ignore")
    role: str
    content: Union[str, list, None] = None

class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    model: Optional[str] = "claude-local"
    messages: list[Message]
    max_tokens: Optional[int] = 4096
    temperature: Optional[float] = 0.7
    stream: Optional[bool] = False

@app.get("/")
def root():
    return {"status": "Claude Code Proxy running"}

@app.get("/v1/models")
def list_models():
    return {
        "object": "list",
        "data": [{
            "id": "claude-local",
            "object": "model",
            "created": 1700000000,
            "owned_by": "local"
        }]
    }

def extract_text(content) -> str:
    """Extract plain text from message content (str, list of parts, or None)."""
    if content is None:
        return ""
    elif isinstance(content, list):
        return " ".join(
            part.get("text", "") for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        )
    return content

MAX_CONVERSATION_MESSAGES = 20  # only keep last N user/assistant messages

def build_prompt(messages: list[Message]) -> tuple[str, str]:
    """Split messages into (system_prompt, conversation_prompt).
    Returns system text separately so it can go via --system-prompt,
    and only keeps the last MAX_CONVERSATION_MESSAGES for context."""
    system_parts = []
    conversation = []
    for msg in messages:
        text = extract_text(msg.content)
        if not text:
            continue
        if msg.role == "system":
            system_parts.append(text)
        elif msg.role == "user":
            conversation.append(f"User: {text}")
        elif msg.role == "assistant":
            conversation.append(f"Assistant: {text}")

    system_prompt = "\n".join(system_parts)
    # Keep only recent conversation to avoid bloat
    trimmed = conversation[-MAX_CONVERSATION_MESSAGES:]
    return system_prompt, "\n".join(trimmed)

def call_claude(prompt: str, system_prompt: str = "") -> str:
    """Call Claude Code CLI and return the output."""
    try:
        cmd = [CLAUDE_CLI, "--print", "--permission-mode", "acceptEdits"]
        if system_prompt:
            cmd.extend(["--system-prompt", system_prompt])
        result = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            cwd="/home/rob/.openclaw/workspace",
            timeout=120
        )
        output = result.stdout.strip()
        if result.returncode != 0:
            logger.error(f"CLI failed (code {result.returncode}): {result.stderr[:300] if result.stderr else '(no stderr)'}")
        if not output and result.stderr:
            output = result.stderr.strip()
    except subprocess.TimeoutExpired:
        output = "Request timed out."
        logger.error("CLI timed out after 120s")
    except Exception as e:
        output = f"Error calling Claude Code: {str(e)}"
        logger.error(f"CLI exception: {e}")
    return output

@app.post("/v1/chat/completions")
def chat(req: ChatRequest):
    logger.info(f"Request: model={req.model}, messages={len(req.messages)}, max_tokens={req.max_tokens}, stream={req.stream}")

    # Extract and log the last user message (what came from Telegram)
    last_user_text = ""
    for msg in reversed(req.messages):
        if msg.role == "user":
            last_user_text = extract_text(msg.content)
            # Strip metadata prefix (Conversation info block) to get the real message
            if "```\n\n" in last_user_text:
                last_user_text = last_user_text.split("```\n\n", 1)[-1]
            break
    logger.info(f"TELEGRAM_IN: {last_user_text}")

    system_prompt, prompt = build_prompt(req.messages)
    prompt_tokens = max(1, (len(prompt) + len(system_prompt)) // 4)
    logger.info(f"PROMPT: ({prompt_tokens} tokens, system={len(system_prompt)} chars, conv={len(prompt)} chars)")

    output = call_claude(prompt, system_prompt)

    completion_tokens = max(1, len(output) // 4)
    output_oneline = output.replace('\n', ' ')[:500]
    logger.info(f"TELEGRAM_OUT: {output_oneline}")
    logger.info(f"TOKENS: prompt={prompt_tokens} completion={completion_tokens} total={prompt_tokens + completion_tokens}")

    chat_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"
    created = int(time.time())

    if req.stream:
        def generate_sse():
            # Single content chunk with the full response
            chunk = {
                "id": chat_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": "claude-local",
                "choices": [{
                    "index": 0,
                    "delta": {"role": "assistant", "content": output},
                    "finish_reason": None
                }]
            }
            yield f"data: {json.dumps(chunk)}\n\n"

            # Final chunk with finish_reason and usage
            done_chunk = {
                "id": chat_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": "claude-local",
                "choices": [{
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop"
                }],
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens
                }
            }
            yield f"data: {json.dumps(done_chunk)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(generate_sse(), media_type="text/event-stream")

    # Non-streaming response
    return {
        "id": chat_id,
        "object": "chat.completion",
        "created": created,
        "model": "claude-local",
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": output
            },
            "finish_reason": "stop"
        }],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=19000)
