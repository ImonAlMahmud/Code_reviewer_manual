#!/usr/bin/env python3
"""
AI Code Reviewer - Interactive Multi-Provider + Local AI

Usage:
    py ai_code_reviewer_interactive.py "C:\\Users\\Imon\\Downloads\\Data Insight"

Workflow:
    1. Configure / verify API keys before scanning.
    2. Scan/tokenize the selected folder OR specific file.
    3. Save tokenizer HTML report.
    4. Ask Y/N for AI review.
    5. Select provider from a numbered dropdown-style menu.
    6. Select an active model.
    7. Review the codebase in context-sized chunks.
    8. Save one consolidated HTML review report.

Supported:
    OpenRouter, OpenAI, Anthropic, xAI, DeepSeek, Gemini, Mistral,
    Groq, Together AI, Ollama, LM Studio, vLLM, custom OpenAI-compatible.

Optional:
    pip install tiktoken
"""
# AI_CODE_REVIEWER_VERSION = 4.0.0 | SMART CHUNKING + RETRY + RESUME + RATE LIMIT HANDLING\n

from __future__ import annotations

AI_CODE_REVIEWER_V6 = "8.6 - single consolidated HTML report + strict Groq JSON output + file/folder review"

import argparse
import getpass
import hashlib
import html
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
import unicodedata
try:
    import requests  # type: ignore
except Exception:
    requests = None
try:
    from groq import Groq  # type: ignore
except Exception:
    Groq = None
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


# ============================================================
# CONFIG
# ============================================================

IGNORE_DIRS = {
    ".git", ".svn", ".hg",
    "node_modules", "vendor",
    "target", "build", "dist",
    ".idea", ".gradle",
    "__pycache__", ".pytest_cache",
    ".venv", "venv",
    "coverage", ".next", ".nuxt",
}

IGNORE_FILES = {"Thumbs.db", ".DS_Store"}

TEXT_EXTENSIONS = {
    ".java", ".groovy", ".gradle", ".kt", ".kts",
    ".py", ".js", ".jsx", ".ts", ".tsx",
    ".php", ".c", ".h", ".cpp", ".cc", ".cxx", ".hpp",
    ".cs", ".go", ".rs", ".rb", ".swift",
    ".sql", ".sh", ".bash", ".zsh", ".ps1",
    ".html", ".htm", ".css", ".scss", ".sass", ".less",
    ".xml", ".json", ".yaml", ".yml", ".toml", ".ini",
    ".properties", ".conf", ".cfg",
    ".md", ".txt",
}

PROVIDERS = [
    ("OpenRouter", "openrouter", "Cloud aggregator / free models"),
    ("OpenAI", "openai", "OpenAI API"),
    ("Anthropic", "anthropic", "Claude API"),
    ("xAI", "xai", "Grok API"),
    ("DeepSeek", "deepseek", "DeepSeek API"),
    ("Google Gemini", "gemini", "Gemini API"),
    ("Mistral", "mistral", "Mistral API"),
    ("Groq", "groq", "OpenAI-compatible API"),
    ("Together AI", "together", "OpenAI-compatible API"),
    ("Ollama (Local)", "ollama", "Local AI - no API key"),
    ("LM Studio (Local)", "lmstudio", "Local AI - OpenAI compatible"),
    ("vLLM (Local)", "vllm", "Local AI - OpenAI compatible"),
    ("Custom OpenAI-Compatible", "custom", "Custom endpoint"),
]

ENV_KEYS = {
    "openrouter": "OPENROUTER_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "xai": "XAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "groq": "GROQ_API_KEY",
    "together": "TOGETHER_API_KEY",
}

API_KEY_STORE_FILENAME = "api_keys.env"

DEFAULT_ENDPOINTS = {
    "ollama": "http://127.0.0.1:11434",
    "lmstudio": "http://127.0.0.1:1234/v1",
    "vllm": "http://127.0.0.1:8000/v1",
}

MODEL_CONTEXTS = {
    "openrouter/free": 200_000,
    "qwen/qwen3-coder:free": 32_000,
    "deepseek/deepseek-r1:free": 32_000,
    "openai/gpt-oss-120b:free": 131_072,
    "openai/gpt-oss-20b:free": 131_072,

    # Context values are only used for chunking. Verify current provider
    # documentation before relying on exact context limits.
    "gpt-5.5": 400_000,
    "gpt-5": 400_000,
    "claude-opus-4.8": 1_000_000,
    "grok-4.5": 200_000,
    "deepseek-v4-pro": 1_000_000,

    "qwen3-coder": 256_000,
    "qwen3-coder:latest": 256_000,
    "deepseek-coder": 128_000,

    # Groq legacy / explicitly sized models.
    "llama3-8b-8192": 8_192,
    "llama-3.1-8b-instant": 131_072,
    "llama-3.3-70b-versatile": 131_072,
    "llama-4-scout": 131_072,
}

# Conservative fallback for an unknown model. The user can still override
# the context window interactively before review.
DEFAULT_CONTEXT = 8_192

SYSTEM_PROMPT = """
You are a senior software engineer performing a production-grade code review.

Review ONLY the supplied source code. Do not invent files, line numbers,
functions, APIs, behavior, or vulnerabilities.

Find:
- Bugs and correctness problems
- Security issues
- Null/error/exception handling problems
- Concurrency/thread-safety issues
- Resource leaks
- Performance problems
- Maintainability/code smells
- Architecture/design issues
- Java/Groovy best practices
- Build/dependency problems
- Testing gaps
- Reliability/observability improvements

For every real finding provide:
- category
- severity: Critical, High, Medium, Low, Info
- file path
- line/LOC if reasonably identifiable
- title
- evidence
- why it matters
- concrete fix suggestion
- confidence

Do not report speculative problems as definite problems.

Return ONLY valid JSON:
{
  "summary": "short summary",
  "overall_status": "positive|needs_attention|critical",
  "findings": [
    {
      "category": "...",
      "severity": "Critical|High|Medium|Low|Info",
      "file": "relative/path",
      "line": 123,
      "line_end": 130,
      "title": "...",
      "evidence": "...",
      "why": "...",
      "fix": "...",
      "confidence": "High|Medium|Low"
    }
  ],
  "positive_points": ["..."],
  "recommendations": ["..."]
}
""".strip()


@dataclass
class FileInfo:
    path: Path
    relative: str
    size: int
    lines: int
    text: str
    tokens: int


# ============================================================
# UTILITIES
# ============================================================

def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def safe_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value)
    return value.strip("_") or "project"


def format_bytes(value: int) -> str:
    n = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.2f} {unit}"
        n /= 1024
    return f"{value} B"


def estimate_tokens(text: str) -> int:
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return max(1, len(enc.encode(text)))
    except Exception:
        return max(1, round(len(text) / 3.5))


def read_text(path: Path) -> str | None:
    try:
        raw = path.read_bytes()
    except Exception:
        return None

    if b"\x00" in raw[:8192]:
        return None

    for enc in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass

    return None


def scan_target(target: Path) -> tuple[Path, list[FileInfo], str]:
    """
    Scan either:
      - a directory recursively, or
      - one specific source/text file.

    Returns:
      (project_root, files, target_type)

    For a single file, project_root is the file's parent directory and
    the report will contain only that file.
    """
    result: list[FileInfo] = []

    if target.is_file():
        name = target.name
        suffix = target.suffix.lower()

        if suffix not in TEXT_EXTENSIONS and name not in {
            "Dockerfile", "Makefile", "Jenkinsfile", "gradlew"
        }:
            raise RuntimeError(
                f"Unsupported file type: {target}\n"
                f"Extension '{suffix or '[none]'}' is not in TEXT_EXTENSIONS."
            )

        try:
            size = target.stat().st_size
        except OSError as exc:
            raise RuntimeError(f"Could not stat file: {target}") from exc

        content = read_text(target)
        if content is None:
            raise RuntimeError(
                f"Could not read file as supported text/source: {target}"
            )

        root = target.parent
        relative = target.name
        lines = content.count("\n") + (1 if content else 0)

        result.append(
            FileInfo(
                path=target,
                relative=relative,
                size=size,
                lines=lines,
                text=content,
                tokens=estimate_tokens(content),
            )
        )

        return root, result, "file"

    if not target.is_dir():
        raise RuntimeError(
            f"Target does not exist or is not a file/folder:\n{target}"
        )

    root = target

    for current, dirs, filenames in os.walk(root):
        dirs[:] = [
            d for d in dirs
            if d not in IGNORE_DIRS and not d.startswith(".")
        ]

        for name in filenames:
            if name in IGNORE_FILES:
                continue

            path = Path(current) / name
            suffix = path.suffix.lower()

            if suffix not in TEXT_EXTENSIONS and name not in {
                "Dockerfile", "Makefile", "Jenkinsfile", "gradlew"
            }:
                continue

            try:
                size = path.stat().st_size
            except OSError:
                continue

            content = read_text(path)
            if content is None:
                continue

            relative = path.relative_to(root).as_posix()
            lines = content.count("\n") + (1 if content else 0)

            result.append(
                FileInfo(
                    path=path,
                    relative=relative,
                    size=size,
                    lines=lines,
                    text=content,
                    tokens=estimate_tokens(content),
                )
            )

    return root, sorted(result, key=lambda f: f.relative.lower()), "folder"


# ============================================================
# TOKENIZER REPORT
# ============================================================

def save_tokenizer_report(root: Path, files: list[FileInfo]) -> Path:
    out_dir = root / "ai_code_review_reports"
    out_dir.mkdir(exist_ok=True)

    total_size = sum(f.size for f in files)
    total_lines = sum(f.lines for f in files)
    total_tokens = sum(f.tokens for f in files)

    rows = []

    for f in files:
        rows.append(
            "<tr>"
            f"<td>{html.escape(f.relative)}</td>"
            f"<td>{f.lines:,}</td>"
            f"<td>{f.tokens:,}</td>"
            f"<td>{html.escape(format_bytes(f.size))}</td>"
            f"<td>{html.escape(f.path.suffix or '[no extension]')}</td>"
            "</tr>"
        )

    report = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Tokenizer Report - {html.escape(root.name)}</title>
<style>
body{{font-family:Arial,sans-serif;margin:32px;color:#222}}
.cards{{display:flex;gap:14px;flex-wrap:wrap;margin:20px 0}}
.card{{border:1px solid #ddd;border-radius:10px;padding:16px;min-width:170px}}
.value{{font-size:24px;font-weight:700}}
table{{border-collapse:collapse;width:100%}}
th,td{{border:1px solid #ddd;padding:8px;text-align:left}}
th{{background:#f5f5f5}}
small{{color:#666}}
</style>
</head>
<body>
<h1>Tokenizer Report</h1>
<p>
<b>Project:</b> {html.escape(root.name)}<br>
<b>Path:</b> {html.escape(str(root))}<br>
<b>Generated:</b> {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
</p>

<div class="cards">
<div class="card"><div>Files</div><div class="value">{len(files):,}</div></div>
<div class="card"><div>LOC</div><div class="value">{total_lines:,}</div></div>
<div class="card"><div>Estimated Tokens</div><div class="value">{total_tokens:,}</div></div>
<div class="card"><div>Source Size</div><div class="value">{html.escape(format_bytes(total_size))}</div></div>
</div>

<p><small>
If tiktoken is installed, cl100k_base is used as a common programming-token
approximation. Otherwise a character-based estimate is used. Exact token
counts vary by model tokenizer.
</small></p>

<table>
<thead>
<tr><th>File</th><th>LOC</th><th>Tokens</th><th>Size</th><th>Type</th></tr>
</thead>
<tbody>
{''.join(rows)}
</tbody>
</table>
</body>
</html>
"""

    report_subject = (
        safe_name(files[0].path.stem)
        if len(files) == 1
        else safe_name(root.name)
    )
    path = out_dir / f"{report_subject}-tokenizer-{timestamp()}.html"
    path.write_text(report, encoding="utf-8")
    return path


# ============================================================
# INTERACTIVE PROVIDER / MODEL SELECTORS
# ============================================================

def select_provider() -> str:
    print("\n" + "=" * 76)
    print("                 AI PROVIDER SELECTOR v2")
    print("=" * 76)
    print("  1. OpenRouter")
    print("  2. OpenAI")
    print("  3. Anthropic")
    print("  4. xAI")
    print("  5. DeepSeek")
    print("  6. Google Gemini")
    print("  7. Mistral")
    print("  8. Groq")
    print("  9. Together AI")
    print(" 10. Ollama (Local)")
    print(" 11. LM Studio (Local)")
    print(" 12. vLLM (Local)")
    print(" 13. Custom OpenAI-Compatible")
    print("=" * 76)

    while True:
        raw = input("\nSelect provider [1-13]: ").strip()

        try:
            index = int(raw)
            if 1 <= index <= 13:
                name, key, desc = PROVIDERS[index - 1]
                print(f"Selected: {name}")
                return key
        except ValueError:
            pass

        print("Invalid selection. Please enter a number from 1 to 13.")

def get_json(url: str, timeout: int = 3) -> dict[str, Any]:
    request = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def discover_ollama_models(endpoint: str) -> list[str]:
    try:
        data = get_json(endpoint.rstrip("/") + "/api/tags")
        return [
            x.get("name")
            for x in data.get("models", [])
            if x.get("name")
        ]
    except Exception:
        return []


def discover_openai_models(endpoint: str) -> list[str]:
    try:
        data = get_json(endpoint.rstrip("/") + "/models")
        return [
            x.get("id")
            for x in data.get("data", [])
            if x.get("id")
        ]
    except Exception:
        return []


def check_local_runtime(provider: str, endpoint: str) -> bool:
    if provider == "ollama":
        url = endpoint.rstrip("/") + "/api/tags"
    else:
        url = endpoint.rstrip("/") + "/models"

    try:
        get_json(url, timeout=2)
        return True
    except Exception:
        return False


def select_local_model(
    provider: str,
    endpoint: str,
) -> tuple[str, str]:
    if provider == "ollama":
        models = discover_ollama_models(endpoint)
    else:
        models = discover_openai_models(endpoint)

    if models:
        print("\nDetected local models:")
        for i, model in enumerate(models, 1):
            print(f"  {i}. {model}")
        print(f"  {len(models) + 1}. Enter model manually")

        while True:
            raw = input(
                f"Select model [1-{len(models) + 1}]: "
            ).strip()

            try:
                index = int(raw)

                if 1 <= index <= len(models):
                    return models[index - 1], endpoint

                if index == len(models) + 1:
                    break
            except ValueError:
                pass

            print("Invalid selection.")

    model = input(
        "Model name "
        "(example: qwen3-coder): "
    ).strip()

    return model, endpoint


def select_model(
    provider: str,
) -> tuple[str, str | None]:
    if provider in {"ollama", "lmstudio", "vllm"}:
        default = DEFAULT_ENDPOINTS[provider]

        endpoint = input(
            f"\n{provider.upper()} endpoint "
            f"[Enter = {default}]: "
        ).strip() or default

        if check_local_runtime(provider, endpoint):
            print("✓ Local AI runtime detected.")
        else:
            print(
                "⚠ Local runtime was not detected at that endpoint."
                "\n  You may still enter the model manually."
            )

        return select_local_model(provider, endpoint)

    if provider == "openrouter":
        choices = [
            ("openrouter/free", "Free router"),
            ("qwen/qwen3-coder:free", "Free coding model if available"),
            ("deepseek/deepseek-r1:free", "Free reasoning model if available"),
            ("openai/gpt-oss-120b:free", "Free large model if available"),
            ("custom", "Enter OpenRouter model ID"),
        ]

        print("\nOpenRouter model selector:")
        for i, (model, description) in enumerate(choices, 1):
            print(f"  {i}. {model:<38} - {description}")

        while True:
            raw = input("Select model [1-5]: ").strip()

            try:
                index = int(raw)
                if 1 <= index <= len(choices):
                    model = choices[index - 1][0]

                    if model == "custom":
                        model = input(
                            "OpenRouter model ID: "
                        ).strip()

                    return model, None
            except ValueError:
                pass

            print("Invalid selection.")

    presets = {
        "openai": ["gpt-5.5", "gpt-5"],
        "anthropic": ["claude-opus-4.8"],
        "xai": ["grok-4.5"],
        "deepseek": ["deepseek-v4-pro"],
        "gemini": ["gemini-2.5-pro"],
        "mistral": ["mistral-large-latest"],
        "groq": ["llama-4-scout"],
        "together": ["openai/gpt-oss-120b"],
    }

    choices = presets.get(provider, [])

    if choices:
        print(f"\n{provider.upper()} model selector:")

        for i, model in enumerate(choices, 1):
            print(f"  {i}. {model}")

        print(f"  {len(choices) + 1}. Enter model manually")

        while True:
            raw = input(
                f"Select model [1-{len(choices) + 1}]: "
            ).strip()

            try:
                index = int(raw)

                if 1 <= index <= len(choices):
                    return choices[index - 1], None

                if index == len(choices) + 1:
                    break
            except ValueError:
                pass

            print("Invalid selection.")

    model = input("Model name / model ID: ").strip()
    return model, None


# ============================================================
# API
# ============================================================

class ProviderHTTPError(RuntimeError):
    def __init__(self, status: int, detail: str, headers: Any = None):
        self.status = status
        self.detail = detail or ""
        self.headers = headers or {}

        clean = self.detail.strip()
        if not clean:
            clean = "(provider returned an empty error body)"

        super().__init__(f"HTTP {status} from provider: {clean[:4000]}")


def post_json(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout: int = 180,
) -> dict[str, Any]:
    """Robust JSON POST: requests first, urllib fallback."""
    clean_headers = dict(headers)

    auth = clean_headers.get("Authorization", "")
    if auth.lower().startswith("bearer bearer "):
        clean_headers["Authorization"] = "Bearer " + auth[14:].strip()

    if requests is not None:
        try:
            response = requests.post(
                url,
                json=payload,
                headers=clean_headers,
                timeout=timeout,
            )
            request_id = (
                response.headers.get("x-request-id")
                or response.headers.get("request-id")
                or response.headers.get("cf-ray")
                or ""
            )
            if response.status_code >= 400:
                body = (response.text or "").strip()
                raise RuntimeError(
                    f"HTTP {response.status_code} from provider. "
                    f"Body: {body[:5000] if body else '<empty>'}"
                    + (f" | Request ID: {request_id}" if request_id else "")
                )
            if not response.text.strip():
                raise RuntimeError("Provider returned an empty success response.")
            try:
                return response.json()
            except Exception as exc:
                raise RuntimeError(
                    f"Provider returned non-JSON data: {response.text[:3000]}"
                ) from exc
        except requests.RequestException as exc:
            raise RuntimeError(f"Provider connection failed: {exc}") from exc

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers=clean_headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            if not raw.strip():
                raise RuntimeError("Provider returned an empty success response.")
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            f"HTTP {exc.code} from provider. "
            f"Body: {body[:5000] if body else '<empty>'}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Provider connection failed: {exc}") from exc

def call_openai_compatible(
    provider: str,
    model: str,
    api_key: str | None,
    prompt: str,
    endpoint: str | None,
) -> tuple[str, dict[str, Any]]:
    cloud_urls = {
        "openrouter":
            "https://openrouter.ai/api/v1/chat/completions",
        "openai":
            "https://api.openai.com/v1/chat/completions",
        "xai":
            "https://api.x.ai/v1/chat/completions",
        "deepseek":
            "https://api.deepseek.com/chat/completions",
        "gemini":
            "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "mistral":
            "https://api.mistral.ai/v1/chat/completions",
        "groq":
            "https://api.groq.com/openai/v1/chat/completions",
        "together":
            "https://api.together.xyz/v1/chat/completions",
    }

    if provider == "ollama":
        base = (endpoint or DEFAULT_ENDPOINTS["ollama"]).rstrip("/")
        url = base + "/v1/chat/completions"
        key = api_key or "ollama"

    elif provider in {"lmstudio", "vllm"}:
        base = (
            endpoint or DEFAULT_ENDPOINTS[provider]
        ).rstrip("/")
        url = base + "/chat/completions"
        key = api_key or "local"

    elif provider == "custom":
        if endpoint:
            base = endpoint.rstrip("/")
        else:
            base = input(
                "Custom OpenAI-compatible base URL "
                "(example: https://host/v1): "
            ).strip().rstrip("/")

        url = base + "/chat/completions"
        key = api_key or ""

    else:
        url = cloud_urls[provider]
        key = api_key or ""

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
    }

    if provider == "openrouter":
        headers["HTTP-Referer"] = "http://localhost"
        headers["X-Title"] = "AI Code Reviewer"

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        "temperature": 0.1,
    }

    response = post_json(
        url,
        payload,
        headers,
    )

    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise RuntimeError(
            "Unexpected provider response:\n"
            + json.dumps(
                response,
                indent=2,
            )[:5000]
        )

    return content, response.get("usage", {})


def call_anthropic(
    model: str,
    api_key: str,
    prompt: str,
) -> tuple[str, dict[str, Any]]:
    url = "https://api.anthropic.com/v1/messages"

    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }

    payload = {
        "model": model,
        "max_tokens": 4096,
        "system": SYSTEM_PROMPT,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
    }

    response = post_json(
        url,
        payload,
        headers,
    )

    text = "".join(
        block.get("text", "")
        for block in response.get("content", [])
        if block.get("type") == "text"
    )

    if not text:
        raise RuntimeError(
            "Anthropic returned an empty/invalid response."
        )

    return text, response.get("usage", {})



def sanitize_api_key(value: str | None) -> str:
    """
    Normalize API-key input without ever printing the secret.

    Handles:
    - leading/trailing whitespace
    - accidental surrounding quotes
    - accidental 'Bearer ' prefix
    - zero-width/BOM/control-format characters
    - pasted CR/LF/tab/space characters
    """
    if not value:
        return ""

    key = unicodedata.normalize("NFKC", str(value))

    # Remove Unicode format/control characters such as BOM/zero-width spaces.
    key = "".join(
        ch for ch in key
        if unicodedata.category(ch) not in {"Cf", "Cc"}
        or ch not in {"\n", "\r", "\t"}
    )

    key = key.strip().strip('"').strip("'").strip()

    if key.lower().startswith("bearer "):
        key = key[7:].strip()

    # API keys never intentionally contain whitespace.
    key = "".join(ch for ch in key if not ch.isspace())

    return key


def safe_key_diagnostics(provider: str, api_key: str | None) -> None:
    """
    Show only non-secret diagnostics. Never prints the actual API key.
    """
    key = sanitize_api_key(api_key)

    import hashlib
    fingerprint = hashlib.sha256(key.encode("utf-8")).hexdigest()[:10] if key else "empty"

    expected = {
        "groq": "gsk_",
        "openrouter": "sk-or-",
    }.get(provider)

    print("\nAPI-key diagnostics (secret is NOT displayed):")
    print(f"  Length      : {len(key)}")
    print(f"  Fingerprint : {fingerprint}")
    if expected:
        print(f"  Prefix {expected:<6}: {'YES' if key.startswith(expected) else 'NO'}")


def groq_transport_diagnostics(api_key: str | None) -> None:
    """
    Test Groq authentication/connectivity without sending any source code.

    It performs:
      A. Official SDK models.list()
      B. Direct HTTPS GET /models using requests (if installed)

    If both fail with the same status, the problem is outside code chunking.
    """
    key = sanitize_api_key(api_key)

    print("\nGroq connection diagnostics (NO source code is sent):")

    # A) Official Groq SDK
    try:
        if Groq is None:
            print("  SDK models.list : SKIPPED (groq package not installed)")
        else:
            client = Groq(api_key=key)
            page = client.models.list()
            count = len(getattr(page, "data", []) or [])
            print(f"  SDK models.list : OK ({count} models)")
    except Exception as exc:
        status = getattr(exc, "status_code", None)
        body = getattr(exc, "body", None)
        request_id = getattr(exc, "request_id", None)
        print(f"  SDK models.list : FAILED ({type(exc).__name__})")
        if status is not None:
            print(f"    HTTP status : {status}")
        if request_id:
            print(f"    Request ID  : {request_id}")
        if body:
            safe_body = str(body)
            print(f"    Body        : {safe_body[:1000]}")
        else:
            print(f"    Detail      : {str(exc)[:1000]}")

    # B) requests
    try:
        if requests is None:
            print("  HTTPS /models   : SKIPPED (requests package not installed)")
        else:
            response = requests.get(
                "https://api.groq.com/openai/v1/models",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                timeout=20,
            )
            rid = (
                response.headers.get("x-request-id")
                or response.headers.get("request-id")
                or response.headers.get("cf-ray")
            )
            print(f"  HTTPS /models   : HTTP {response.status_code}")
            if rid:
                print(f"    Request ID  : {rid}")
            body = (response.text or "").strip()
            if body and response.status_code >= 400:
                print(f"    Body        : {body[:1000]}")
    except Exception as exc:
        print(f"  HTTPS /models   : FAILED ({type(exc).__name__}): {str(exc)[:1000]}")



# ============================================================
# API KEY SETUP / PERSISTENCE
# ============================================================

def api_key_store_path() -> Path:
    """Store API keys beside this script when the user explicitly chooses Save."""
    return Path(__file__).resolve().parent / API_KEY_STORE_FILENAME


def load_api_key_store(path: Path | None = None) -> dict[str, str]:
    """
    Load a simple KEY=VALUE file and also copy values into os.environ for
    this process. The file is optional.
    """
    path = path or api_key_store_path()
    values: dict[str, str] = {}

    if not path.exists():
        return values

    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            name, value = line.split("=", 1)
            name = name.strip()
            value = sanitize_api_key(value.strip().strip('"').strip("'"))

            if name and value:
                values[name] = value
                os.environ[name] = value

    except Exception as exc:
        print(f"WARNING: Could not read {path.name}: {exc}")

    return values


def save_api_key_store(values: dict[str, str], path: Path | None = None) -> None:
    """
    Save API keys to a local env-style file.

    IMPORTANT: this is plain-text secret storage. The UI makes this explicit
    before saving. On Unix we chmod 600 when possible.
    """
    path = path or api_key_store_path()

    lines = [
        "# AI Code Reviewer API Keys",
        "# DO NOT COMMIT THIS FILE TO GIT.",
        "# Keep it private. On Linux/macOS use chmod 600 api_keys.env.",
        "",
    ]

    for provider, env_name in ENV_KEYS.items():
        value = sanitize_api_key(values.get(env_name, ""))
        lines.append(f"{env_name}={value}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    try:
        if os.name != "nt":
            os.chmod(path, 0o600)
    except Exception:
        pass


def mask_key(value: str | None) -> str:
    key = sanitize_api_key(value)
    if not key:
        return "NOT SET"
    if len(key) <= 8:
        return f"SET ({len(key)} chars)"
    return f"{key[:4]}...{key[-4:]} ({len(key)} chars)"


def validate_api_key_format(provider: str, value: str | None) -> tuple[bool, list[str]]:
    """
    Provider-aware local validation.

    Hard failures are intentionally conservative:
    - empty key
    - obviously too short
    - whitespace/control-character corruption after sanitization

    Prefix checks are advisory because providers may introduce new key formats.
    A successful live connection test is the authoritative validation before
    a key is allowed to be persisted.
    """
    key = sanitize_api_key(value)
    messages: list[str] = []

    if not key:
        return False, ["API key is empty."]

    if len(key) < 20:
        return False, [
            f"API key is too short ({len(key)} characters). "
            "The key was probably pasted incorrectly."
        ]

    expected_prefixes = {
        "groq": ("gsk_",),
        "openrouter": ("sk-or-",),
        "openai": ("sk-",),
        "anthropic": ("sk-ant-",),
        "xai": ("xai-",),
        "deepseek": ("sk-",),
        "gemini": ("AIza",),
    }

    prefixes = expected_prefixes.get(provider)
    if prefixes and not key.startswith(prefixes):
        messages.append(
            "Prefix does not match the provider's common key format "
            f"({', '.join(prefixes)}). A live connection test will decide."
        )

    messages.append(f"Length check passed: {len(key)} characters.")
    return True, messages


def show_api_key_status() -> None:
    print("\n" + "=" * 76)
    print("                         API KEY STATUS")
    print("=" * 76)

    for name, provider, _ in PROVIDERS:
        if provider in {"ollama", "lmstudio", "vllm", "custom"}:
            continue

        env_name = ENV_KEYS.get(provider)
        if not env_name:
            continue

        value = os.getenv(env_name, "")
        print(f"{name:<22} {env_name:<24} {mask_key(value)}")

    print("=" * 76)


def choose_cloud_provider_for_key() -> str | None:
    cloud = [
        item for item in PROVIDERS
        if item[1] not in {"ollama", "lmstudio", "vllm", "custom"}
    ]

    print("\nSelect provider API key:")
    for i, (name, provider, _desc) in enumerate(cloud, 1):
        env_name = ENV_KEYS.get(provider, "")
        state = "SET" if sanitize_api_key(os.getenv(env_name, "")) else "NOT SET"
        print(f"  {i:>2}. {name:<20} [{state}]")

    print(f"  {len(cloud) + 1:>2}. Back")

    while True:
        raw = input(f"\nSelect [1-{len(cloud) + 1}]: ").strip()

        try:
            n = int(raw)
            if 1 <= n <= len(cloud):
                return cloud[n - 1][1]
            if n == len(cloud) + 1:
                return None
        except ValueError:
            pass

        print("Invalid selection.")


def visible_api_key_input(provider: str, env_name: str) -> str:
    """
    Windows-friendly paste mode.

    getpass() can capture only a control character in some Windows CMD setups.
    Here the key is visible while pasting, then immediately masked in all later
    output. The user is warned before input.
    """
    print("\n" + "-" * 76)
    print("VISIBLE API KEY PASTE MODE")
    print("-" * 76)
    print(
        "The API key WILL be visible on screen while you paste it.\n"
        "Use this only in a private terminal. It will not be echoed again after\n"
        "this step, and the script never writes it to reports."
    )
    print(f"Provider : {provider}")
    print(f"Variable : {env_name}")
    print("-" * 76)

    return sanitize_api_key(input("Paste API key: "))


def test_api_key_connection(provider: str, api_key: str) -> tuple[bool, str]:
    """
    Validate the key with a small provider-native model-list request.
    No source code is sent.

    This relies on the existing all-provider live-model discovery layer.
    """
    try:
        models = fetch_live_models(provider, api_key, None)
        if models:
            return True, f"Connection successful. {len(models)} active/usable model(s) returned."
        return False, "Provider authenticated but returned no usable models."
    except Exception as exc:
        return False, str(exc)


def set_api_key_interactive() -> None:
    provider = choose_cloud_provider_for_key()
    if not provider:
        return

    env_name = ENV_KEYS[provider]
    current = sanitize_api_key(os.getenv(env_name, ""))

    if current:
        print(f"\n{env_name} is already set: {mask_key(current)}")
        replace = input("Replace it? [Y/N]: ").strip().lower()
        if replace not in {"y", "yes"}:
            return

    # Retry loop so a bad paste never reaches persistence.
    while True:
        value = visible_api_key_input(provider, env_name)
        ok, messages = validate_api_key_format(provider, value)

        print("\nLocal validation:")
        for message in messages:
            print(f"  - {message}")

        if not ok:
            print("\nERROR: API key failed local validation.")
            print("The key was NOT set and was NOT saved.")
            action = input("[R]etry / [B]ack: ").strip().lower()
            if action == "r":
                continue
            return

        print("\nTesting provider connection (NO source code is sent)...")
        connected, detail = test_api_key_connection(provider, value)

        if not connected:
            print(f"✗ Connection test failed: {detail}")
            print("The key was NOT set and was NOT saved.")
            action = input("[R]etry / [B]ack: ").strip().lower()
            if action == "r":
                continue
            return

        print(f"✓ {detail}")
        os.environ[env_name] = value
        print(f"✓ {env_name} set for this run.")
        print(f"  Stored value check: {mask_key(value)}")
        break

    save = input(
        f"\nSave this verified key to {API_KEY_STORE_FILENAME} for future runs? "
        "[Y/N]: "
    ).strip().lower()

    if save not in {"y", "yes"}:
        return

    print(
        "\nSECURITY WARNING:\n"
        f"  {API_KEY_STORE_FILENAME} is a local PLAIN-TEXT secret file.\n"
        "  Never commit/upload it to GitHub."
    )
    confirm = input("Save the verified key anyway? [Y/N]: ").strip().lower()

    if confirm not in {"y", "yes"}:
        return

    values = {
        env_name_: os.getenv(env_name_, "")
        for env_name_ in ENV_KEYS.values()
    }
    save_api_key_store(values)
    print(f"✓ Verified API key saved to: {api_key_store_path()}")
    print(f"  Add '{API_KEY_STORE_FILENAME}' to .gitignore.")


def remove_saved_api_key_interactive() -> None:
    provider = choose_cloud_provider_for_key()
    if not provider:
        return

    env_name = ENV_KEYS[provider]

    if not sanitize_api_key(os.getenv(env_name, "")):
        print(f"{env_name} is not set.")
        return

    confirm = input(f"Remove {env_name}? [Y/N]: ").strip().lower()
    if confirm not in {"y", "yes"}:
        return

    os.environ.pop(env_name, None)

    values = load_api_key_store()
    values.pop(env_name, None)

    if api_key_store_path().exists():
        save_api_key_store(values)

    print(f"✓ {env_name} removed from this process and local key store.")


def api_setup_menu() -> None:
    """
    Runs before tokenization/review.

    Existing OS environment variables are loaded first. If api_keys.env exists,
    it is also loaded. Keys entered through this menu are validated with a live
    provider request before they can be saved.
    """
    load_api_key_store()

    while True:
        print("\n" + "=" * 76)
        print("                      API / PROVIDER SETUP")
        print("=" * 76)
        print("  1. Continue to Codebase Scan")
        print("  2. Set / Update API Key")
        print("  3. View API Key Status")
        print("  4. Remove Saved API Key")
        print("  5. Continue with Local AI (no API key)")
        print("=" * 76)

        raw = input("\nSelect [1-5]: ").strip()

        if raw == "1":
            return
        if raw == "2":
            set_api_key_interactive()
            continue
        if raw == "3":
            show_api_key_status()
            continue
        if raw == "4":
            remove_saved_api_key_interactive()
            continue
        if raw == "5":
            print("Local AI selected as intent; provider can be chosen after scanning.")
            return

        print("Invalid selection.")

def get_api_key(provider: str) -> str | None:
    # Local runtimes don't require an API key.
    if provider in {"ollama", "lmstudio", "vllm"}:
        return None

    env_name = ENV_KEYS.get(provider)

    if env_name:
        existing = sanitize_api_key(os.getenv(env_name))
        if existing:
            print(f"Using API key from environment/key store {env_name}.")
            return existing

    if provider == "custom":
        print(
            "\nCustom endpoint API key is optional. "
            "Input is visible for Windows paste compatibility."
        )
        value = sanitize_api_key(input("API key [Enter = none]: "))
        return value or None

    # If the user skipped setup, safely invoke the same validated setup flow.
    print(
        f"\nNo verified {env_name or provider.upper() + '_API_KEY'} is configured."
    )
    print("Opening API key setup...")
    set_api_key_interactive()

    existing = sanitize_api_key(os.getenv(env_name or ""))
    if existing:
        return existing

    raise RuntimeError(
        f"No verified API key is available for provider '{provider}'."
    )

def call_ai(
    provider: str,
    model: str,
    api_key: str | None,
    prompt: str,
    endpoint: str | None,
) -> tuple[str, dict[str, Any]]:
    if provider == "anthropic":
        return call_anthropic(
            model,
            api_key or "",
            prompt,
        )

    if provider == "groq":
        return groq_native_review(model, api_key, prompt)

    return call_openai_compatible(
        provider,
        model,
        api_key,
        prompt,
        endpoint,
    )


# ============================================================
# CHUNKING / REVIEW
# ============================================================

def context_for_model(model: str) -> int:
    key = model.strip()
    if key in MODEL_CONTEXTS:
        return MODEL_CONTEXTS[key]

    # Case-insensitive exact lookup.
    lowered = key.lower()
    for known, value in MODEL_CONTEXTS.items():
        if known.lower() == lowered:
            return value

    return DEFAULT_CONTEXT


def _token_encode(text: str):
    """Return a tiktoken encoding when available; otherwise None."""
    try:
        import tiktoken
        try:
            return tiktoken.get_encoding("cl100k_base")
        except Exception:
            return tiktoken.get_encoding("o200k_base")
    except Exception:
        return None


def split_text_to_budget(text: str, budget: int) -> list[tuple[str, int]]:
    """
    Hard-split arbitrary text into <= budget-token parts.

    This is intentionally token-aware so a single minified/very-long line
    cannot create a 100K+ token 'part' and bypass the chunk budget.
    """
    if not text:
        return []

    enc = _token_encode(text)
    if enc is not None:
        tokens = enc.encode(text)
        parts: list[tuple[str, int]] = []
        for i in range(0, len(tokens), budget):
            piece_tokens = tokens[i:i + budget]
            piece = enc.decode(piece_tokens)
            parts.append((piece, len(piece_tokens)))
        return parts

    # Fallback approximation: ~4 characters/token for source text.
    # Use a little extra safety so the fallback never intentionally fills
    # the whole budget.
    chars_per_part = max(1000, budget * 3)
    parts = []
    for i in range(0, len(text), chars_per_part):
        piece = text[i:i + chars_per_part]
        parts.append((piece, max(1, estimate_tokens(piece))))
    return parts


def build_chunks(
    files: list[FileInfo],
    context: int,
    input_budget: int | None = None,
) -> list[list[FileInfo]]:
    # Leave room for system prompt, file metadata and model output.
    budget = int(input_budget or max(1_500, min(100_000, int(context * 0.50))))

    chunks: list[list[FileInfo]] = []
    current: list[FileInfo] = []
    current_tokens = 0

    def flush_current() -> None:
        nonlocal current, current_tokens
        if current:
            chunks.append(current)
            current = []
            current_tokens = 0

    for file in files:
        # Normal file: it can fit inside the token budget.
        if file.tokens <= budget:
            if current and current_tokens + file.tokens > budget:
                flush_current()
            current.append(file)
            current_tokens += file.tokens
            continue

        # Large file: ALWAYS hard-split, including minified files with
        # extremely long single lines.
        flush_current()

        parts = split_text_to_budget(file.text, budget)
        for part_no, (part_text, part_tokens) in enumerate(parts, 1):
            virtual = FileInfo(
                path=file.path,
                relative=f"{file.relative} [part {part_no}/{len(parts)}]",
                size=len(part_text.encode("utf-8")),
                lines=len(part_text.splitlines()) or 1,
                text=part_text,
                tokens=part_tokens,
            )
            chunks.append([virtual])

    flush_current()
    return chunks


def review_prompt(
    root: Path,
    chunk: list[FileInfo],
    index: int,
    total: int,
) -> str:
    parts = [
        f"Project: {root.name}",
        f"Review chunk: {index}/{total}",
        "",
        "Paths are relative to the project root.",
        "Review the following source files:",
    ]

    for file in chunk:
        parts.append(
            f"\n===== FILE: {file.relative} | "
            f"LOC: {file.lines} =====\n"
            f"{file.text}\n"
            "===== END FILE ====="
        )

    return "\n".join(parts)


def parse_model_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()

    if not text:
        raise RuntimeError("AI provider returned an empty review response.")

    # Remove Markdown fences.
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)

    # First try the whole response.
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass

    # Then extract the outermost JSON object from incidental prose.
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidate = text[start:end + 1]
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass

    # Invalid model output should not be reported as a source-code defect.
    raise RuntimeError(
        "The AI response was not valid JSON. "
        f"Response preview: {text[:800]!r}"
    )



def chunk_signature(chunk: list[FileInfo]) -> str:
    payload = "|".join(
        f"{f.relative}:{f.lines}:{f.tokens}:{len(f.text)}"
        for f in chunk
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def codebase_signature(files: list[FileInfo]) -> str:
    payload = "|".join(
        f"{f.relative}:{f.size}:{f.lines}:{f.tokens}"
        for f in files
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def split_chunk_for_retry(
    chunk: list[FileInfo],
    target_tokens: int | None = None,
) -> list[list[FileInfo]]:
    """Split a chunk into genuinely smaller token-bounded chunks."""
    total = sum(f.tokens for f in chunk)
    if total <= 1_500:
        return []

    if len(chunk) > 1:
        # Greedy split by file weight.
        target = target_tokens or max(1_000, total // 2)
        parts: list[list[FileInfo]] = []
        current: list[FileInfo] = []
        current_tokens = 0

        for file in chunk:
            if current and current_tokens + file.tokens > target:
                parts.append(current)
                current = []
                current_tokens = 0
            current.append(file)
            current_tokens += file.tokens

        if current:
            parts.append(current)

        if len(parts) > 1:
            return parts

    # One oversized file/part: hard-split its text.
    file = chunk[0]
    target = target_tokens or max(1_000, file.tokens // 2)
    pieces = split_text_to_budget(file.text, target)

    result: list[list[FileInfo]] = []
    for i, (piece, tok) in enumerate(pieces, 1):
        result.append([FileInfo(
            path=file.path,
            relative=f"{file.relative} [retry-part {i}/{len(pieces)}]",
            size=len(piece.encode("utf-8")),
            lines=len(piece.splitlines()) or 1,
            text=piece,
            tokens=tok,
        )])
    return result if len(result) > 1 else []


def is_context_error(exc: Exception) -> bool:
    if isinstance(exc, ProviderHTTPError):
        if exc.status in {400, 413}:
            detail = exc.detail.lower()
            markers = (
                "context", "context_length", "context window",
                "maximum context", "max context", "too many tokens",
                "token limit", "prompt is too long", "input is too long",
                "request too large", "payload too large",
            )
            return any(m in detail for m in markers)
    return False


def retry_after_seconds(exc: Exception, attempt: int) -> float:
    if isinstance(exc, ProviderHTTPError):
        value = exc.headers.get("Retry-After") if exc.headers else None
        if value:
            try:
                return max(0.5, min(120.0, float(value)))
            except (TypeError, ValueError):
                pass

    # Exponential backoff + small jitter.
    return min(120.0, (2 ** (attempt - 1)) + random.uniform(0.0, 0.75))


def is_retryable_error(exc: Exception) -> bool:
    if isinstance(exc, ProviderHTTPError):
        return exc.status in {408, 409, 429, 500, 502, 503, 504}
    message = str(exc).lower()
    return any(x in message for x in (
        "timed out", "timeout", "temporarily", "connection reset",
        "connection aborted", "could not connect",
    ))


def checkpoint_path(root: Path, provider: str, model: str) -> Path:
    out_dir = root / "ai_code_review_reports"
    out_dir.mkdir(exist_ok=True)
    return out_dir / (
        f"{safe_name(root.name)}-"
        f"{safe_name(provider)}-"
        f"{safe_name(model)}-checkpoint.json"
    )


def load_checkpoint(
    path: Path,
    root: Path,
    files: list[FileInfo],
    provider: str,
    model: str,
) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

    if (
        data.get("project_path") != str(root)
        or data.get("provider") != provider
        or data.get("model") != model
        or data.get("codebase_signature") != codebase_signature(files)
    ):
        return None
    return data


def save_checkpoint(path: Path, state: dict[str, Any]) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp.replace(path)


def call_ai_with_resilience(
    provider: str,
    model: str,
    api_key: str | None,
    prompt: str,
    endpoint: str | None,
    max_attempts: int = 5,
) -> tuple[str, dict[str, Any]]:
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return call_ai(provider, model, api_key, prompt, endpoint)
        except Exception as exc:
            last_error = exc
            if is_context_error(exc):
                raise
            if not is_retryable_error(exc) or attempt >= max_attempts:
                raise

            wait = retry_after_seconds(exc, attempt)
            status = getattr(exc, "status", "retryable")
            print(
                f"    ⚠ Provider error ({status}); "
                f"retry {attempt}/{max_attempts - 1} in {wait:.1f}s..."
            )
            time.sleep(wait)

    raise last_error or RuntimeError("Unknown AI provider error")



def probe_rate_limit_headers(
    provider: str,
    model: str,
    api_key: str | None,
    endpoint: str | None = None,
) -> dict[str, Any]:
    """Tiny request that captures rate-limit headers when the provider exposes them."""
    if requests is None:
        return {}
    if provider != "groq":
        return {}
    url = "https://api.groq.com/openai/v1/chat/completions"
    key = (api_key or "").strip()
    if key.lower().startswith("bearer "):
        key = key[7:].strip()
    r = requests.post(
        url,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": "Reply only: OK"}],
            "max_tokens": 4,
            "temperature": 0,
        },
        timeout=30,
    )
    if r.status_code >= 400:
        return {}
    h = {k.lower(): v for k, v in r.headers.items()}
    def as_int(name: str):
        try:
            return int(float(h.get(name, "0"))) or None
        except Exception:
            return None
    return {
        "tpm": as_int("x-ratelimit-limit-tokens"),
        "remaining_tokens": as_int("x-ratelimit-remaining-tokens"),
        "remaining_requests": as_int("x-ratelimit-remaining-requests"),
        "reset_tokens": h.get("x-ratelimit-reset-tokens"),
    }


def choose_rate_policy(provider: str, model: str, api_key: str | None, endpoint: str | None, context: int) -> dict[str, Any]:
    """Resolve a safe per-request code budget and pacing policy."""
    context_budget = max(1_500, min(100_000, int(context * 0.50)))
    info = probe_rate_limit_headers(provider, model, api_key, endpoint)
    tpm = info.get("tpm")

    if tpm:
        # Keep substantial room for instructions + output and avoid consuming the full minute in one request.
        rate_budget = max(1_200, int(tpm * 0.50) - 900)
        code_budget = max(1_200, min(context_budget, rate_budget))
        # Approximate prompt overhead + expected output. This deliberately paces conservatively.
        estimated_total = code_budget + 1_500
        delay = min(65.0, max(0.0, 60.0 * estimated_total / max(tpm, 1) * 1.08))
        return {"source": "live_headers", "tpm": tpm, "budget": code_budget, "delay": delay, **info}

    print("\nRate-limit metadata was not exposed by the provider preflight.")
    raw = input("Optional TPM/ITPM limit for safe pacing [Enter = context-only]: ").strip().replace(",", "")
    if raw:
        try:
            manual_tpm = max(1000, int(raw))
            rate_budget = max(1_200, int(manual_tpm * 0.50) - 900)
            code_budget = max(1_200, min(context_budget, rate_budget))
            estimated_total = code_budget + 1_500
            delay = min(65.0, max(0.0, 60.0 * estimated_total / manual_tpm * 1.08))
            return {"source": "manual", "tpm": manual_tpm, "budget": code_budget, "delay": delay}
        except ValueError:
            print("Invalid TPM value; using context-only budget.")
    return {"source": "context_only", "tpm": None, "budget": context_budget, "delay": 0.0}

def review_codebase(
    root: Path,
    files: list[FileInfo],
    provider: str,
    model: str,
    api_key: str | None,
    endpoint: str | None,
) -> dict[str, Any]:
    context = context_for_model(model)
    rate_policy = choose_rate_policy(provider, model, api_key, endpoint, context)
    input_budget = int(rate_policy["budget"])
    chunks = build_chunks(files, context, input_budget=input_budget)
    cp = checkpoint_path(root, provider, model)

    print(f"\nContext assumed: {context:,} tokens")
    print(f"Safe input budget: {input_budget:,} code tokens/chunk")
    if rate_policy.get("tpm"):
        print(f"Rate limit: {int(rate_policy['tpm']):,} tokens/minute ({rate_policy['source']})")
        print(f"Adaptive pacing: ~{float(rate_policy['delay']):.1f}s minimum between successful requests")
    else:
        print("Rate limit: not exposed; using context-only budget")
    print(f"Initial review chunks: {len(chunks):,}")

    if model.strip().lower() not in {k.lower() for k in MODEL_CONTEXTS}:
        print(
            "⚠ Model context is not in the built-in map; "
            f"conservative fallback {DEFAULT_CONTEXT:,} tokens is being used."
        )
    print("Resilience: proactive TPM pacing + 429/5xx retry + Retry-After + context-error auto-splitting + checkpoint/resume")

    state = load_checkpoint(cp, root, files, provider, model)
    if state:
        answer = input(
            "\nAn unfinished checkpoint was found. Resume it? [Y/N]: "
        ).strip().lower()
        if answer not in {"y", "yes"}:
            state = None
            try:
                cp.unlink()
            except OSError:
                pass

    if state is None:
        state = {
            "version": 3,
            "project_path": str(root),
            "project": root.name,
            "provider": provider,
            "model": model,
            "codebase_signature": codebase_signature(files),
            "completed_chunks": [],
            "findings": [],
            "positive_points": [],
            "recommendations": [],
            "summaries": [],
            "usage": {},
            "rate_policy": rate_policy,
            "failed_chunks": [],
            "started_at": datetime.now().isoformat(timespec="seconds"),
        }

    completed = set(state.get("completed_chunks", []))
    findings: list[dict[str, Any]] = list(state.get("findings", []))
    positives: list[str] = list(state.get("positive_points", []))
    recommendations: list[str] = list(state.get("recommendations", []))
    summaries: list[str] = list(state.get("summaries", []))
    usage: dict[str, int] = {
        str(k): int(v) for k, v in state.get("usage", {}).items()
        if isinstance(v, (int, float))
    }
    failed_chunks: list[dict[str, Any]] = list(state.get("failed_chunks", []))

    queue: list[list[FileInfo]] = [c for c in chunks if chunk_signature(c) not in completed]
    total_initial = len(chunks)
    processed = len(completed)
    last_success_at = 0.0

    while queue:
        chunk = queue.pop(0)
        sig = chunk_signature(chunk)
        if sig in completed:
            continue

        token_count = sum(f.tokens for f in chunk)
        print(
            f"\n[{processed + 1}/{max(total_initial, processed + len(queue) + 1)}] "
            f"Files: {len(chunk)} | Tokens: {token_count:,}"
        )

        prompt = review_prompt(root, chunk, 1, 1)

        # Proactive TPM pacing. 429 handling remains as a second line of defense.
        min_delay = float(rate_policy.get("delay") or 0.0)
        if min_delay > 0 and last_success_at > 0:
            elapsed = time.time() - last_success_at
            if elapsed < min_delay:
                wait_for = min_delay - elapsed
                print(f"  ⏳ Rate-limit pacing: waiting {wait_for:.1f}s...")
                time.sleep(wait_for)

        try:
            raw, call_usage = call_ai_with_resilience(
                provider, model, api_key, prompt, endpoint
            )
            result = parse_model_json(raw)

            findings.extend(result.get("findings", []))
            positives.extend(result.get("positive_points", []))
            recommendations.extend(result.get("recommendations", []))
            if result.get("summary"):
                summaries.append(str(result["summary"]))

            for key, value in (call_usage or {}).items():
                if isinstance(value, (int, float)):
                    usage[key] = usage.get(key, 0) + int(value)

            completed.add(sig)
            processed += 1
            # Remove any stale failed record for this exact chunk.
            failed_chunks = [x for x in failed_chunks if x.get("signature") != sig]
            last_success_at = time.time()
            print("  ✓ Review completed.")

        except Exception as exc:
            if is_context_error(exc):
                smaller = split_chunk_for_retry(chunk)
                if smaller:
                    print(
                        "  ⚠ Context/input limit detected. "
                        f"Auto-splitting {token_count:,} tokens into "
                        f"{len(smaller)} smaller chunk(s)."
                    )
                    queue = smaller + queue
                    continue

            # Permanent or exhausted failure: record it, checkpoint it, and
            # continue with other chunks rather than losing the whole review.
            print(f"  ✗ Chunk failed: {exc}")
            if isinstance(exc, ProviderHTTPError):
                print(f"    HTTP status : {exc.status}")
                if exc.detail.strip():
                    print(f"    Provider body: {exc.detail[:1500]}")
                else:
                    print("    Provider body: <empty>")
                if exc.status == 400:
                    print(
                        "    Hint: HTTP 400 is not automatically a rate-limit error. "
                        "It may be an invalid model/request or context/token limit."
                    )
            failed_chunks.append({
                "signature": sig,
                "files": [f.relative for f in chunk],
                "tokens": token_count,
                "error": str(exc),
            })

        state.update({
            "completed_chunks": sorted(completed),
            "findings": findings,
            "positive_points": positives,
            "recommendations": recommendations,
            "summaries": summaries,
            "usage": usage,
            "failed_chunks": failed_chunks,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        })
        save_checkpoint(cp, state)
        print(f"  ✓ Checkpoint saved: {cp.name}")

    # Deduplicate findings.
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for finding in findings:
        signature = "|".join([
            str(finding.get("category", "")),
            str(finding.get("severity", "")),
            str(finding.get("file", "")),
            str(finding.get("line", "")),
            str(finding.get("title", "")),
        ])
        digest = hashlib.sha256(signature.encode("utf-8")).hexdigest()
        if digest not in seen:
            seen.add(digest)
            unique.append(finding)

    severity_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3, "Info": 4}
    unique.sort(key=lambda item: (
        severity_order.get(str(item.get("severity")), 99),
        str(item.get("file", "")),
        int(item.get("line") or 0),
    ))

    if any(x.get("severity") == "Critical" for x in unique):
        status = "critical"
    elif unique:
        status = "needs_attention"
    elif failed_chunks:
        status = "review_incomplete"
    else:
        status = "positive"

    review = {
        "project": root.name,
        "path": str(root),
        "provider": provider,
        "model": model,
        "context_assumed": context,
        "chunks": len(completed),
        "initial_chunks": total_initial,
        "overall_status": status,
        "findings": unique,
        "positive_points": sorted(set(map(str, positives))),
        "recommendations": sorted(set(map(str, recommendations))),
        "summaries": summaries,
        "usage": usage,
        "failed_chunks": failed_chunks,
        "checkpoint_file": str(cp),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }

    # Keep checkpoint only when there are failed chunks, so the user can
    # rerun and resume/retry them without repeating successful work.
    if not failed_chunks:
        try:
            cp.unlink()
        except OSError:
            pass

    return review


# ============================================================
# REVIEW REPORT
# ============================================================

def make_html(
    review: dict[str, Any],
    files: list[FileInfo],
) -> str:
    findings = review["findings"]

    counts = {}

    for finding in findings:
        severity = str(
            finding.get(
                "severity",
                "Info",
            )
        )
        counts[severity] = (
            counts.get(severity, 0)
            + 1
        )

    if not findings:
        findings_html = """
        <div class="positive">
            <h2>✓ Positive Code Review</h2>
            <p>
            No actionable issues were identified by the selected
            AI model in the reviewed source.
            </p>
        </div>
        """
    else:
        blocks = []

        for finding in findings:
            line = finding.get("line")
            line_end = finding.get("line_end")

            loc = ""

            if line:
                loc = f"Line {line}"

                if line_end and line_end != line:
                    loc += f"-{line_end}"

            blocks.append(
                f"""
                <article class="finding">
                    <span class="badge">
                    {html.escape(str(
                        finding.get(
                            "severity",
                            "Info"
                        )
                    ))}
                    </span>

                    <h2>
                    {html.escape(str(
                        finding.get(
                            "title",
                            "Untitled finding"
                        )
                    ))}
                    </h2>

                    <p>
                    <b>Category:</b>
                    {html.escape(str(
                        finding.get(
                            "category",
                            ""
                        )
                    ))}
                    </p>

                    <p>
                    <b>File:</b>
                    <code>
                    {html.escape(str(
                        finding.get(
                            "file",
                            ""
                        )
                    ))}
                    </code>
                    {" &nbsp; <b>LOC:</b> " + html.escape(loc)
                     if loc else ""}
                    </p>

                    <p>
                    <b>Confidence:</b>
                    {html.escape(str(
                        finding.get(
                            "confidence",
                            ""
                        )
                    ))}
                    </p>

                    <h3>Evidence</h3>
                    <pre>{html.escape(str(
                        finding.get(
                            "evidence",
                            ""
                        )
                    ))}</pre>

                    <h3>Why it matters</h3>
                    <p>{html.escape(str(
                        finding.get(
                            "why",
                            ""
                        )
                    ))}</p>

                    <h3>Fix suggestion</h3>
                    <p>{html.escape(str(
                        finding.get(
                            "fix",
                            ""
                        )
                    ))}</p>
                </article>
                """
            )

        findings_html = "\n".join(blocks)

    positives = "".join(
        f"<li>{html.escape(str(item))}</li>"
        for item in review[
            "positive_points"
        ]
    )

    recommendations = "".join(
        f"<li>{html.escape(str(item))}</li>"
        for item in review[
            "recommendations"
        ]
    )

    summaries = "".join(
        f"<li>{html.escape(str(item))}</li>"
        for item in review[
            "summaries"
        ]
    )

    total_tokens = sum(
        f.tokens for f in files
    )

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>AI Code Review - {html.escape(review["project"])}</title>
<style>
body {{
    font-family: Arial, sans-serif;
    margin: 32px;
    color: #222;
    line-height: 1.5;
}}
h1 {{ margin-bottom: 4px; }}
.cards {{
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
    margin: 20px 0;
}}
.card {{
    border: 1px solid #ddd;
    border-radius: 10px;
    padding: 14px 18px;
    min-width: 140px;
}}
.value {{
    font-size: 24px;
    font-weight: 700;
}}
.finding {{
    border: 1px solid #ddd;
    border-radius: 10px;
    padding: 18px;
    margin: 18px 0;
}}
.badge {{
    display: inline-block;
    border: 1px solid #999;
    border-radius: 20px;
    padding: 3px 10px;
    font-weight: bold;
}}
.warning {{
    border: 1px solid #d99;
    border-radius: 10px;
    padding: 16px;
    margin: 18px 0;
}}
.positive {{
    border: 1px solid #999;
    border-radius: 10px;
    padding: 20px;
    margin: 20px 0;
}}
pre {{
    white-space: pre-wrap;
    background: #f6f6f6;
    padding: 12px;
    border-radius: 8px;
    overflow: auto;
}}
code {{
    background: #f3f3f3;
    padding: 2px 5px;
    border-radius: 4px;
}}
small {{ color: #666; }}
</style>
</head>

<body>

<h1>AI Code Review Report</h1>

<p>
<b>Project:</b>
{html.escape(review["project"])}<br>

<b>Path:</b>
{html.escape(review["path"])}<br>

<b>Provider:</b>
{html.escape(review["provider"])}<br>

<b>Model:</b>
{html.escape(review["model"])}<br>

<b>Status:</b>
{html.escape(review["overall_status"])}<br>

<b>Generated:</b>
{html.escape(review["generated_at"])}
</p>

<div class="cards">

<div class="card">
<div>Files</div>
<div class="value">{len(files):,}</div>
</div>

<div class="card">
<div>LOC</div>
<div class="value">
{sum(f.lines for f in files):,}
</div>
</div>

<div class="card">
<div>Tokens</div>
<div class="value">
{total_tokens:,}
</div>
</div>

<div class="card">
<div>AI Response</div>
<div class="value">Structured JSON ✓</div>
</div>

<div class="card">
<div>Critical</div>
<div class="value">
{counts.get("Critical", 0)}
</div>
</div>

<div class="card">
<div>High</div>
<div class="value">
{counts.get("High", 0)}
</div>
</div>

<div class="card">
<div>Medium</div>
<div class="value">
{counts.get("Medium", 0)}
</div>
</div>

<div class="card">
<div>Low</div>
<div class="value">
{counts.get("Low", 0)}
</div>
</div>

</div>

<h2>AI Summary</h2>
<ul>
{summaries or "<li>No summary returned.</li>"}
</ul>

<h2>Findings</h2>
{findings_html}

{("<div class=\"warning\"><h2>⚠ Review Incomplete</h2><p>" + html.escape(str(len(review.get("failed_chunks", [])))) + " chunk(s) could not be processed by the provider. These are execution failures, not AI code findings. Retry or switch model/provider.</p></div>") if review.get("failed_chunks") else ""}

<h2>Positive Points</h2>
<ul>
{positives or "<li>No specific positive points returned.</li>"}
</ul>

<h2>Recommendations</h2>
<ul>
{recommendations or "<li>No additional recommendations returned.</li>"}
</ul>

<hr>

<p>
<small>
AI-generated report. Verify findings before applying production changes.
Token counts and context values are estimates unless confirmed by the
specific model/provider tokenizer.
</small>
</p>

</body>
</html>
"""


def save_reports(
    root: Path,
    review: dict[str, Any],
    files: list[FileInfo],
) -> Path:
    """
    Save ONE final HTML report only.

    Tokenizer/source statistics and review findings are already included in the
    HTML report. JSON/checkpoint files are internal runtime artifacts and are
    removed after a fully successful review.
    """
    out_dir = root / "ai_code_review_reports"
    out_dir.mkdir(exist_ok=True)

    subject_name = (
        Path(review.get("path", root)).stem
        if review.get("target_type") == "file"
        else root.name
    )

    base = (
        f"{safe_name(subject_name)}-"
        f"{safe_name(review['provider'])}-"
        f"{safe_name(review['model'])}-"
        f"{timestamp()}"
    )

    html_path = out_dir / f"{base}.html"
    html_path.write_text(
        make_html(review, files),
        encoding="utf-8",
    )

    return html_path



# ============================================================
# LIVE ACTIVE MODEL DISCOVERY - ALL PROVIDERS (v6)
# ============================================================

def provider_get_json(
    url: str,
    api_key: str | None = None,
    extra_headers: dict | None = None,
    timeout: int = 20,
) -> dict[str, Any]:
    """Robust provider model-list GET: requests first, urllib fallback."""
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "AI-Code-Reviewer/6.2",
    }
    if extra_headers:
        headers.update(extra_headers)

    clean_key = (api_key or "").strip()
    if clean_key.lower().startswith("bearer "):
        clean_key = clean_key[7:].strip()

    if clean_key and "Authorization" not in headers and "x-api-key" not in headers:
        headers["Authorization"] = f"Bearer {clean_key}"

    if requests is not None:
        try:
            response = requests.get(
                url,
                headers=headers,
                timeout=timeout,
            )
            request_id = (
                response.headers.get("x-request-id")
                or response.headers.get("request-id")
                or response.headers.get("cf-ray")
                or ""
            )
            if response.status_code >= 400:
                body = (response.text or "").strip()
                hint = {
                    400: "Bad request; this is not normally a rate-limit response.",
                    401: "Authentication failed; verify the API key.",
                    403: "Access forbidden by account/project permissions.",
                    429: "Rate limit reached.",
                }.get(response.status_code, "")
                raise RuntimeError(
                    f"HTTP {response.status_code} while fetching active models. "
                    f"Body: {body[:3000] if body else '<empty>'}"
                    + (f" | Request ID: {request_id}" if request_id else "")
                    + (f" | Hint: {hint}" if hint else "")
                )
            if not response.text.strip():
                raise RuntimeError("Provider returned an empty active-model response.")
            try:
                return response.json()
            except Exception as exc:
                raise RuntimeError(
                    f"Provider returned non-JSON model-list data: "
                    f"{response.text[:3000]}"
                ) from exc
        except requests.RequestException as exc:
            raise RuntimeError(
                f"Could not reach provider model endpoint: {exc}"
            ) from exc

    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            if not raw.strip():
                raise RuntimeError("Provider returned an empty active-model response.")
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            f"HTTP {exc.code} while fetching active models. "
            f"Body: {body[:3000] if body else '<empty>'}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Could not reach provider model endpoint: {exc}"
        ) from exc

def normalize_live_models(provider: str, payload: Any) -> list[dict[str, Any]]:
    models: list[dict[str, Any]] = []

    if provider == "gemini":
        if not isinstance(payload, dict):
            return models
        for item in payload.get("models", []) or []:
            if not isinstance(item, dict):
                continue
            methods = item.get("supportedGenerationMethods") or []
            if methods and "generateContent" not in methods:
                continue
            model_id = str(item.get("name", ""))
            if model_id.startswith("models/"):
                model_id = model_id[7:]
            if not model_id:
                continue
            models.append({
                "id": model_id,
                "name": item.get("displayName") or model_id,
                "context": item.get("inputTokenLimit"),
                "active": True,
                "raw": item,
            })
        return models

    if isinstance(payload, list):
        data = payload
    elif isinstance(payload, dict):
        data = payload.get("data", [])
        if not isinstance(data, list):
            data = payload.get("models", [])
    else:
        return models

    if not isinstance(data, list):
        return models

    for item in data:
        if not isinstance(item, dict):
            continue

        model_id = item.get("id") or item.get("name") or item.get("model")
        if not model_id:
            continue

        if item.get("active") is False or item.get("archived") is True:
            continue

        context = (
            item.get("context_window")
            or item.get("context_length")
            or item.get("max_context_length")
            or item.get("max_input_tokens")
            or item.get("input_token_limit")
            or (item.get("top_provider") or {}).get("context_length")
            or (item.get("limits") or {}).get("context")
        )

        models.append({
            "id": str(model_id),
            "name": item.get("display_name") or item.get("name") or str(model_id),
            "context": context,
            "active": True,
            "raw": item,
        })

    return models

def groq_native_client(api_key: str | None):
    """Create the official Groq Python SDK client."""
    if Groq is None:
        raise RuntimeError(
            "Groq SDK is not installed. Run: py -m pip install -U groq"
        )
    key = sanitize_api_key(api_key)
    if not key:
        raise RuntimeError("Groq API key is empty.")
    return Groq(api_key=key)


def groq_native_models(api_key: str | None) -> list[dict[str, Any]]:
    """List models through Groq's official SDK instead of raw HTTP."""
    client = groq_native_client(api_key)
    page = client.models.list()
    items = getattr(page, "data", page)
    result: list[dict[str, Any]] = []
    for item in items or []:
        active = getattr(item, "active", True)
        if active is False:
            continue
        model_id = getattr(item, "id", None)
        if not model_id:
            continue
        result.append({
            "id": str(model_id),
            "name": str(model_id),
            "context": getattr(item, "context_window", None),
            "active": True,
            "raw": {"owned_by": getattr(item, "owned_by", None)},
        })
    return result


def groq_native_preflight(model: str, api_key: str | None) -> bool:
    """Tiny official-SDK generation before any source code is sent."""
    client = groq_native_client(api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "Reply only: OK"}],
        temperature=0,
        max_tokens=8,
    )
    return bool(getattr(response, "choices", None))


def groq_native_review(model: str, api_key: str | None, prompt: str) -> tuple[str, dict[str, Any]]:
    """Run Groq reviews with the official SDK and request strict JSON output."""
    client = groq_native_client(api_key)

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "max_completion_tokens": 4096,
        "response_format": {"type": "json_object"},
    }

    # GPT-OSS reasoning models can consume their completion budget on hidden
    # reasoning and return an empty message.content. Low reasoning effort leaves
    # more budget for the actual structured review.
    if "gpt-oss" in model.lower():
        kwargs["reasoning_effort"] = "low"

    try:
        response = client.chat.completions.create(**kwargs)
    except Exception:
        # Some Groq models may not support one of the optional structured-output
        # parameters. Retry with a portable request rather than failing the review.
        kwargs.pop("reasoning_effort", None)
        kwargs.pop("response_format", None)
        response = client.chat.completions.create(**kwargs)

    message = response.choices[0].message
    content = getattr(message, "content", None) or ""

    # Defensive fallback: some reasoning-model SDK responses may expose useful
    # text under reasoning when content is unexpectedly empty.
    if not content.strip():
        reasoning = getattr(message, "reasoning", None)
        if isinstance(reasoning, str) and reasoning.strip().startswith("{"):
            content = reasoning

    if not content.strip():
        finish_reason = getattr(response.choices[0], "finish_reason", None)
        raise RuntimeError(
            "Groq returned an empty final message. "
            f"finish_reason={finish_reason!r}. "
            "Try a larger completion budget or a different active model."
        )

    usage_obj = getattr(response, "usage", None)
    usage = {}
    if usage_obj is not None:
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            value = getattr(usage_obj, key, None)
            if value is not None:
                usage[key] = value
    return content, usage


def fetch_live_models(provider: str, api_key: str | None, endpoint: str | None = None) -> list[dict[str, Any]]:
    if provider == "openrouter":
        url = "https://openrouter.ai/api/v1/models/user" if api_key else "https://openrouter.ai/api/v1/models"
        return normalize_live_models(provider, provider_get_json(url, api_key))
    if provider == "openai":
        return normalize_live_models(provider, provider_get_json("https://api.openai.com/v1/models", api_key))
    if provider == "anthropic":
        headers = {"x-api-key": api_key or "", "anthropic-version": "2023-06-01"}
        return normalize_live_models(provider, provider_get_json("https://api.anthropic.com/v1/models", None, headers))
    if provider == "xai":
        return normalize_live_models(provider, provider_get_json("https://api.x.ai/v1/models", api_key))
    if provider == "deepseek":
        return normalize_live_models(provider, provider_get_json("https://api.deepseek.com/models", api_key))
    if provider == "gemini":
        if not api_key:
            raise RuntimeError("Gemini API key is required to list active models.")
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}&pageSize=1000"
        return normalize_live_models(provider, provider_get_json(url))
    if provider == "mistral":
        return normalize_live_models(provider, provider_get_json("https://api.mistral.ai/v1/models", api_key))
    if provider == "groq":
        return groq_native_models(api_key)
    if provider == "together":
        return normalize_live_models(provider, provider_get_json("https://api.together.xyz/v1/models", api_key))
    if provider == "ollama":
        base = (endpoint or DEFAULT_ENDPOINTS["ollama"]).rstrip("/")
        payload = provider_get_json(base + "/api/tags")
        return [
            {"id": str(x.get("name") or x.get("model")), "name": str(x.get("name") or x.get("model")), "context": None, "active": True, "raw": x}
            for x in payload.get("models", []) if x.get("name") or x.get("model")
        ]
    if provider in {"lmstudio", "vllm"}:
        base = (endpoint or DEFAULT_ENDPOINTS[provider]).rstrip("/")
        return normalize_live_models(provider, provider_get_json(base + "/models", api_key))
    if provider == "custom":
        if not endpoint:
            raise RuntimeError("Custom endpoint is required before model discovery.")
        return normalize_live_models(provider, provider_get_json(endpoint.rstrip("/") + "/models", api_key))
    raise RuntimeError(f"No live model discovery adapter configured for provider: {provider}")


def model_display_sort(item: dict[str, Any]):
    model_id = str(item.get("id", "")).lower()
    non_chat_terms = ("embed", "embedding", "whisper", "tts", "speech", "audio", "moderation", "guard")
    penalty = 1 if any(term in model_id for term in non_chat_terms) else 0
    try:
        context = int(item.get("context") or 0)
    except Exception:
        context = 0
    return (penalty, -context, model_id)



def provider_key_sanity_check(provider: str, api_key: str | None) -> None:
    if provider in {"ollama", "lmstudio", "vllm", "custom"}:
        return

    key = sanitize_api_key(api_key)

    if not key:
        raise RuntimeError(f"{provider} API key is empty.")

    safe_key_diagnostics(provider, key)

    typical_prefixes = {
        "groq": ("gsk_",),
        "openrouter": ("sk-or-",),
    }

    prefixes = typical_prefixes.get(provider)

    if prefixes and not key.startswith(prefixes):
        print(
            f"WARNING: Sanitized API key still does not look like a typical "
            f"{provider.upper()} key."
        )

def minimal_model_preflight(
    provider: str,
    model: str,
    api_key: str | None,
    endpoint: str | None = None,
) -> bool:
    """Send a tiny test request before any source code is uploaded."""
    if provider == "groq":
        return groq_native_preflight(model, api_key)

    if provider == "anthropic":
        response = post_json(
            "https://api.anthropic.com/v1/messages",
            {
                "model": model,
                "max_tokens": 8,
                "messages": [{"role": "user", "content": "Reply only: OK"}],
            },
            {
                "Content-Type": "application/json",
                "x-api-key": api_key or "",
                "anthropic-version": "2023-06-01",
            },
            timeout=30,
        )
        return bool(response.get("content"))

    urls = {
        "openrouter": "https://openrouter.ai/api/v1/chat/completions",
        "openai": "https://api.openai.com/v1/chat/completions",
        "xai": "https://api.x.ai/v1/chat/completions",
        "deepseek": "https://api.deepseek.com/chat/completions",
        "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "mistral": "https://api.mistral.ai/v1/chat/completions",
        "groq": "https://api.groq.com/openai/v1/chat/completions",
        "together": "https://api.together.xyz/v1/chat/completions",
    }

    if provider == "ollama":
        base = (endpoint or DEFAULT_ENDPOINTS["ollama"]).rstrip("/")
        url = base + "/v1/chat/completions"
        key = api_key or "ollama"
    elif provider in {"lmstudio", "vllm"}:
        base = (endpoint or DEFAULT_ENDPOINTS[provider]).rstrip("/")
        url = base + "/chat/completions"
        key = api_key or "local"
    elif provider == "custom":
        if not endpoint:
            raise RuntimeError("Custom endpoint is required.")
        url = endpoint.rstrip("/") + "/chat/completions"
        key = api_key or ""
    else:
        url = urls[provider]
        key = api_key or ""

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if provider == "openrouter":
        headers["HTTP-Referer"] = "http://localhost"
        headers["X-Title"] = "AI Code Reviewer"

    response = post_json(
        url,
        {
            "model": model,
            "messages": [{"role": "user", "content": "Reply only: OK"}],
            "temperature": 0,
            "max_tokens": 8,
        },
        headers,
        timeout=30,
    )
    return bool(response.get("choices"))

def select_live_model(provider: str, api_key: str | None, endpoint: str | None = None) -> tuple[str, int | None]:
    print("\nChecking provider's ACTIVE model list...")
    try:
        models = sorted(fetch_live_models(provider, api_key, endpoint), key=model_display_sort)
    except Exception as exc:
        print(f"WARNING: Could not fetch active model list: {exc}")

        if provider == "groq":
            groq_transport_diagnostics(api_key)
            print("\nGroq fallback models:")
            print("  1. openai/gpt-oss-120b")
            print("  2. openai/gpt-oss-20b")
            print("  3. qwen/qwen3.6-27b")
            print("  4. Retry active-model fetch")
            print("  5. Run Groq connection diagnostics")
            print("  6. Enter model ID manually")

            while True:
                choice = input("Select [1-6]: ").strip()
                fallback = {
                    "1": ("openai/gpt-oss-120b", 131072),
                    "2": ("openai/gpt-oss-20b", 131072),
                    "3": ("qwen/qwen3.6-27b", 131072),
                }
                if choice in fallback:
                    return fallback[choice]
                if choice == "4":
                    return select_live_model(provider, api_key, endpoint)
                if choice == "5":
                    groq_transport_diagnostics(api_key)
                    continue
                if choice == "6":
                    return input("Enter model ID manually: ").strip(), None
                print("Invalid selection.")

        return input("Enter model ID manually: ").strip(), None
    if not models:
        print("WARNING: Provider returned no usable active models.")
        return input("Enter model ID manually: ").strip(), None

    page_size = 25
    page = 0
    while True:
        start = page * page_size
        end = min(start + page_size, len(models))
        subset = models[start:end]
        print("\n" + "=" * 92)
        print(f"ACTIVE MODELS - {provider.upper()} | {len(models)} available")
        print("=" * 92)
        for number, item in enumerate(subset, start + 1):
            try:
                ctx = f"{int(item.get('context')):,}" if item.get("context") else "unknown"
            except Exception:
                ctx = "unknown"
            print(f"{number:>3}. {item['id']:<62} context: {ctx}")
        print("-" * 92)
        commands = []
        if end < len(models): commands.append("N=next")
        if page > 0: commands.append("P=previous")
        commands += ["S=search", "M=manual"]
        print(" | ".join(commands))
        raw = input("Select model number or command: ").strip()
        low = raw.lower()
        if low == "n" and end < len(models):
            page += 1; continue
        if low == "p" and page > 0:
            page -= 1; continue
        if low == "m":
            return input("Enter model ID manually: ").strip(), None
        if low == "s":
            query = input("Search model ID/name: ").strip().lower()
            matches = [m for m in models if query in str(m.get("id", "")).lower() or query in str(m.get("name", "")).lower()]
            if not matches:
                print("No matching active models."); continue
            print("\nSearch results:")
            for i, item in enumerate(matches[:50], 1):
                try: ctx = f"{int(item.get('context')):,}" if item.get("context") else "unknown"
                except Exception: ctx = "unknown"
                print(f"{i:>3}. {item['id']:<62} context: {ctx}")
            pick = input("Select result number (Enter = cancel): ").strip()
            if not pick: continue
            try:
                idx = int(pick)
                if 1 <= idx <= min(50, len(matches)):
                    item = matches[idx - 1]
                    return item["id"], item.get("context")
            except ValueError:
                pass
            print("Invalid selection."); continue
        try:
            idx = int(raw)
            if 1 <= idx <= len(models):
                item = models[idx - 1]
                return item["id"], item.get("context")
        except ValueError:
            pass
        print("Invalid selection.")


def live_model_preflight(provider: str, model: str, api_key: str | None, endpoint: str | None = None) -> tuple[bool, int | None]:
    try:
        models = fetch_live_models(provider, api_key, endpoint)
    except Exception as exc:
        print(f"WARNING: Live model re-validation unavailable: {exc}")
        return True, None
    for item in models:
        if item.get("id") == model:
            return True, item.get("context")
    return False, None

# ============================================================
# MAIN
# ============================================================

def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Interactive AI code reviewer. "
            "Only the codebase path is required."
        )
    )

    parser.add_argument(
        "path",
        help="Folder OR specific source/text file to review",
    )

    args = parser.parse_args()

    target = Path(
        args.path
    ).expanduser().resolve()

    if not target.exists():
        print(
            f"ERROR: Target does not exist:\n{target}"
        )
        return 1

    print("=" * 76)
    print("                     AI CODE REVIEWER")
    print("=" * 76)
    print(f"Target: {target}")
    print(
        f"Mode  : {'Specific File Review' if target.is_file() else 'Folder Review'}"
    )

    # API keys are configured BEFORE codebase scanning/tokenization.
    api_setup_menu()

    print("\n[1/2] Scanning + tokenizer...")

    start = time.time()

    try:
        root, files, target_type = scan_target(target)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1

    if not files:
        print(
            "\nNo supported source/text files found."
        )
        return 1

    # Tokenizer data is included in the final consolidated HTML report.
    tokenizer_report = None

    total_size = sum(
        f.size for f in files
    )
    total_lines = sum(
        f.lines for f in files
    )
    total_tokens = sum(
        f.tokens for f in files
    )

    print(
        f"Files: {len(files):,} | "
        f"Size: {format_bytes(total_size)} | "
        f"LOC: {total_lines:,} | "
        f"Tokens: {total_tokens:,}"
    )

    print("Tokenizer: included in final HTML report (no separate file).")

    print("\n[2/2] AI Code Review")

    answer = input(
        "\nDo you want to perform AI Code Review? [Y/N]: "
    ).strip().lower()

    if answer not in {
        "y",
        "yes",
    }:
        print(
            "\nAI Code Review skipped."
        )
        print(
            "Tokenizer completed. No report file was created because AI review was skipped."
        )
        return 0

    provider = select_provider()

    endpoint = None
    if provider in {"ollama", "lmstudio", "vllm"}:
        default_endpoint = DEFAULT_ENDPOINTS[provider]
        endpoint = input(
            f"\n{provider.upper()} endpoint [Enter = {default_endpoint}]: "
        ).strip() or default_endpoint
        if check_local_runtime(provider, endpoint):
            print("Local runtime detected.")
        else:
            print("WARNING: Local runtime not detected yet; discovery may fail.")
    elif provider == "custom":
        endpoint = input(
            "\nCustom OpenAI-compatible base URL (example: https://host/v1): "
        ).strip().rstrip("/")

    # Key comes first because many provider model lists are account-specific.
    api_key = get_api_key(provider)

    if provider not in {"ollama", "lmstudio", "vllm", "custom"} and not api_key:
        print("ERROR: API key is required.")
        return 1

    provider_key_sanity_check(provider, api_key)

    # Fetch CURRENT active model list for every provider.
    model, discovered_context = select_live_model(provider, api_key, endpoint)
    if not model:
        print("ERROR: Model name cannot be empty.")
        return 1

    active, validated_context = live_model_preflight(provider, model, api_key, endpoint)
    if not active:
        print(f"\nERROR: Model '{model}' is not present in the provider's current active model list.")
        return 1

    live_context = validated_context or discovered_context
    if live_context:
        try:
            MODEL_CONTEXTS[model] = int(live_context)
            print(f"Active model verified. Live context: {int(live_context):,} tokens")
        except Exception:
            print("Active model verified. Context metadata could not be parsed.")
    else:
        print("Active model verified. Provider did not expose context metadata.")

    print("\nRunning tiny model usability preflight (NO source code is sent)...")
    try:
        if minimal_model_preflight(provider, model, api_key, endpoint):
            print("✓ Model accepted the test request.")
        else:
            print("ERROR: Model returned an unexpected preflight response.")
            print("No source code has been sent.")
            return 1
    except Exception as exc:
        print(f"ERROR: Selected model failed usability preflight: {exc}")
        print("No source code has been sent.")
        return 1

    print("\n" + "=" * 76)
    print("                 STARTING AI CODE REVIEW")
    print("=" * 76)

    print(
        f"Provider: {provider}"
    )
    print(
        f"Model:    {model}"
    )
    print("Resilience: live model validation, rate-aware chunking/pacing, 429/5xx retry, Retry-After, context-error splitting, checkpoint/resume")

    if endpoint:
        print(
            f"Endpoint: {endpoint}"
        )

    try:
        review = review_codebase(
            root,
            files,
            provider,
            model,
            api_key,
            endpoint,
        )

        if target_type == "file":
            review["project"] = target.name
            review["path"] = str(target)
            review["target_type"] = "file"
        else:
            review["target_type"] = "folder"

        html_path = save_reports(
            root,
            review,
            files,
        )

        # A checkpoint is useful only while a review is incomplete/interrupted.
        # Remove it after a fully successful review so the report folder ends
        # with one final HTML file for this run.
        if not review.get("failed_chunks"):
            cp_value = review.get("checkpoint_file")
            if cp_value:
                try:
                    Path(cp_value).unlink(missing_ok=True)
                except Exception:
                    pass

    except KeyboardInterrupt:
        print(
            "\nReview cancelled by user."
        )
        return 130

    except Exception as exc:
        print(
            "\nERROR during AI code review:"
        )
        print(exc)
        return 1

    elapsed = time.time() - start

    print("\n" + "=" * 76)
    print("                      REVIEW COMPLETE")
    print("=" * 76)

    print(
        f"Status:       {review['overall_status']}"
    )
    print(
        f"Findings:     {len(review['findings'])}"
    )
    print(
        f"Final report: {html_path}"
    )
    if review.get("failed_chunks"):
        print(f"Checkpoint:    {review.get('checkpoint_file')}")
        print(f"Failed chunks: {len(review.get('failed_chunks', []))}")
    print(
        f"Total time:   {elapsed:.1f} seconds"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
