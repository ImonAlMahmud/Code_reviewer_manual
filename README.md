# 🤖 AI Code Reviewer

A powerful **interactive, multi-provider AI-powered code review tool** written in Python.

AI Code Reviewer can scan an entire codebase or a specific source file, estimate its token usage, connect to a cloud or locally hosted AI model, and generate a structured **HTML code review report** containing bugs, security issues, code-quality problems, improvements, and actionable fix suggestions.

It is designed to work with codebases containing multiple programming languages and supports both **Cloud AI APIs** and **Local AI Models**.

---

## ✨ Features

### 🔍 Codebase Scanner

Scan either:

- An entire project folder
- A specific source file

Example:

```bash
py ai_code_reviewer.py "C:\Users\YourName\Downloads\My Project"
```

or:

```bash
py ai_code_reviewer.py "C:\Users\YourName\Downloads\My Project\index.html"
```

Linux:

```bash
python3 ai_code_reviewer.py "/var/www/my-project"
```

---

### 🧮 Built-in Tokenizer

Before starting the AI review, the application scans the target and provides information such as:

- Total files
- Total source size
- Lines of Code (LOC)
- Estimated tokens
- Language breakdown
- File-level token information

Example:

```text
============================================================
                     TOKENIZER REPORT
============================================================

Project Path : C:\Projects\my-app
Files        : 73
Total Size   : 1.60 MB
Total LOC    : 13,861
Tokens       : 606,913
Tokenizer    : tiktoken / cl100k_base
```

This is useful for estimating whether a project can fit inside an AI model's context window.

---

## 🧠 AI-Powered Code Review

After tokenization, the application can perform an AI-assisted review of the source code.

The reviewer looks for areas such as:

- 🐛 Bugs
- 🔐 Security vulnerabilities
- ⚠️ Potential runtime issues
- 🧹 Code quality problems
- 🚀 Performance improvements
- 🏗️ Architecture issues
- ♻️ Refactoring opportunities
- 📦 Dependency-related concerns
- 🧠 Logic problems
- 🛠️ Maintainability issues
- 📏 Best-practice violations
- 💡 General improvements

Where possible, findings include:

```text
Category
Severity
File Path
Line / LOC
Title
Evidence
Why it matters
Recommended Fix
Confidence
```

---

# 🌐 Supported AI Providers

The interactive provider selector supports multiple AI ecosystems.

Depending on the installed version and provider API availability, these include:

| # | Provider | Type |
|---|---|---|
| 1 | OpenRouter | Cloud API |
| 2 | OpenAI | Cloud API |
| 3 | Anthropic | Cloud API |
| 4 | xAI | Cloud API |
| 5 | DeepSeek | Cloud API |
| 6 | Google Gemini | Cloud API |
| 7 | Mistral | Cloud API |
| 8 | Groq | Cloud API |
| 9 | Together AI | Cloud API |
| 10 | Ollama | Local |
| 11 | LM Studio | Local |
| 12 | vLLM | Local |
| 13 | Custom OpenAI-Compatible | Cloud / Local |

> Model availability depends on the selected provider. Cloud providers can add, rename, deprecate, or remove models over time.

---

# 🔄 Interactive Workflow

The application is designed to be easy to use from a terminal.

Typical workflow:

```text
Select Target
     │
     ▼
Scan Codebase
     │
     ▼
Count Tokens + LOC
     │
     ▼
Generate Tokenizer Information
     │
     ▼
Do you want AI Code Review?
     │
     ▼
API / Provider Setup
     │
     ▼
Select AI Provider
     │
     ▼
Fetch / Select Active Model
     │
     ▼
Validate Model
     │
     ▼
Calculate Safe Context Budget
     │
     ▼
Split Code into Chunks
     │
     ▼
AI Code Review
     │
     ▼
Parse Structured Findings
     │
     ▼
Generate Consolidated HTML Report
```

---

# 🔑 API Key Management

The interactive application includes API-key management.

The setup menu allows you to:

```text
1. Continue to Codebase Scan
2. Set / Update API Key
3. View API Key Status
4. Remove Saved API Key
5. Continue with Local AI (no API key)
```

API keys can be stored in:

```text
api_keys.env
```

Example:

```env
OPENROUTER_API_KEY=YOUR_KEY
OPENAI_API_KEY=YOUR_KEY
ANTHROPIC_API_KEY=YOUR_KEY
XAI_API_KEY=YOUR_KEY
DEEPSEEK_API_KEY=YOUR_KEY
GEMINI_API_KEY=YOUR_KEY
MISTRAL_API_KEY=YOUR_KEY
GROQ_API_KEY=YOUR_KEY
TOGETHER_API_KEY=YOUR_KEY
```

## ⚠️ Important Security Notice

Never commit API keys to GitHub.

Add the following to `.gitignore`:

```gitignore
api_keys.env
.env
*.env
ai_code_review_reports/
__pycache__/
*.pyc
```

If an API key has accidentally been committed to GitHub, revoke it immediately from the provider dashboard and generate a new one.

---

# 📡 Active Model Discovery

For supported providers, AI Code Reviewer attempts to retrieve the provider's currently available models.

Example:

```text
============================================================
ACTIVE MODELS | GROQ | 15 available
============================================================

1. groq/compound
2. groq/compound-mini
3. llama-3.1-8b-instant
4. llama-3.3-70b-versatile
5. openai/gpt-oss-120b
6. openai/gpt-oss-20b
7. qwen/qwen3-32b
...
```

You can then select a model interactively.

Where supported, the application also attempts to determine or estimate the model's context window.

---

# 🧪 Model Preflight Validation

Before sending the actual source code, the reviewer can perform a small model usability test.

Example:

```text
Running tiny model usability preflight
(NO source code is sent)...

✓ Model accepted the test request.
```

This helps detect problems such as:

- Invalid API key
- Invalid model ID
- Unsupported model
- Authentication failure
- Provider endpoint issues

before sending the actual codebase.

---

# 📦 Token-Aware Chunking

Large projects usually cannot be sent to an AI model in a single request.

AI Code Reviewer automatically divides the source code into manageable chunks based on the selected model's context budget.

Example:

```text
Context assumed: 131,072 tokens

Safe input budget: 3,100 code tokens/chunk

Initial review chunks: 278
```

This allows the application to review projects significantly larger than a model's individual context window.

---

# 🚦 Rate-Limit Awareness

Cloud AI APIs may enforce limits such as:

- Requests per minute
- Tokens per minute
- Daily quotas
- Concurrent request limits

The reviewer includes mechanisms for handling provider limitations.

Depending on the provider and available response headers, it can use:

- Token-aware chunking
- Adaptive pacing
- TPM-aware delays
- HTTP 429 retry
- `Retry-After`
- 5xx retry
- Context-error splitting
- Checkpoint/resume

Example:

```text
Rate limit: 8,000 tokens/minute

Adaptive pacing:
~37.3s minimum between successful requests
```

This helps reduce failed reviews caused by aggressive API usage.

---

# 💾 Checkpoint & Resume

Large code reviews may take a significant amount of time.

To reduce the impact of:

- Internet interruption
- API rate limits
- Provider errors
- Process termination
- Temporary server errors

the application can save review progress to a checkpoint.

Example:

```text
Checkpoint saved:
my_project-groq-openai_gpt-oss-20b-checkpoint.json
```

This architecture is intended to make large codebase reviews more resilient.

---

# 📊 Consolidated HTML Report

The final output is designed around a **single consolidated HTML report**.

The report can contain:

### Project Overview

- Project/file name
- Target path
- Target type
- Provider
- AI model
- Context window
- Total files
- LOC
- Token count
- Number of review chunks

### Tokenizer Information

- Language breakdown
- Files per language
- Size
- LOC
- Estimated tokens

### AI Findings

Each finding may contain:

```text
Severity
Category
File
Line
Issue
Evidence
Explanation
Fix Suggestion
Confidence
```

### Positive Findings

If the code contains good implementation patterns, the AI can also report positive observations.

### Recommendations

High-level recommendations may be included for improving:

- Architecture
- Security
- Performance
- Maintainability
- Code organization

---

# 📁 Output Directory

Reports are normally generated inside:

```text
ai_code_review_reports/
```

Example:

```text
my-project/
├── src/
├── public/
├── package.json
│
└── ai_code_review_reports/
    └── my-project-groq-openai_gpt-oss-20b-20260817-171833.html
```

The goal is to keep the final review easy to open, share, and archive.

---

# 🖥️ Windows Installation

## 1. Install Python

Install a modern Python 3 release and verify:

```cmd
py --version
```

or:

```cmd
python --version
```

---

## 2. Download the Project

Clone the repository:

```cmd
git clone YOUR_REPOSITORY_URL
```

Then:

```cmd
cd ai-code-reviewer
```

Alternatively, download the repository as a ZIP and extract it.

---

## 3. Create Virtual Environment

Recommended:

```cmd
py -m venv .venv
```

Activate:

```cmd
.venv\Scripts\activate
```

---

## 4. Install Dependencies

If the repository contains `requirements.txt`:

```cmd
pip install -r requirements.txt
```

Common dependencies may include packages such as:

```cmd
pip install requests tiktoken groq
```

The exact dependencies should follow the version of the script in this repository.

---

# ▶️ Windows Usage

Review a folder:

```cmd
py ai_code_reviewer.py "C:\Users\YourName\Downloads\My Project"
```

Review one file:

```cmd
py ai_code_reviewer.py "C:\Users\YourName\Downloads\My Project\index.html"
```

> Always use quotation marks when the path contains spaces.

For example:

```cmd
py ai_code_reviewer.py "C:\Users\Imon\Downloads\Data Insight"
```

and **not**:

```cmd
py ai_code_reviewer.py C:\Users\Imon\Downloads\Data Insight
```

Without quotation marks, `Data` and `Insight` can be interpreted as separate command-line arguments.

---

# 🐧 Linux / Ubuntu Installation

## 1. Install Python

Ubuntu/Debian:

```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv git -y
```

Check:

```bash
python3 --version
```

---

## 2. Clone Repository

```bash
git clone YOUR_REPOSITORY_URL
cd ai-code-reviewer
```

---

## 3. Create Virtual Environment

```bash
python3 -m venv .venv
```

Activate:

```bash
source .venv/bin/activate
```

---

## 4. Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

---

# ▶️ Linux Usage

Review an entire application:

```bash
python3 ai_code_reviewer.py "/var/www/my-application"
```

Review a specific file:

```bash
python3 ai_code_reviewer.py "/var/www/my-application/index.html"
```

Example:

```bash
python3 ai_code_reviewer.py "/home/user/projects/my-app"
```

---

# 🖥️ Using Local AI Models

One of the major features of AI Code Reviewer is support for locally hosted models.

This can be useful when:

- Source code is confidential
- API cost should be minimized
- Large amounts of code need to be analyzed
- The machine/server has sufficient RAM/GPU resources
- Source code should remain inside the local environment

---

## Ollama

Select:

```text
Ollama (Local)
```

from the provider menu.

Make sure Ollama is already running and the required model has been downloaded.

Check installed models:

```bash
ollama list
```

Example:

```bash
ollama run qwen3-coder
```

No cloud API key is required for a local Ollama model.

---

## LM Studio

The application can work with an LM Studio local API when the OpenAI-compatible local server is enabled.

A typical local endpoint may look similar to:

```text
http://127.0.0.1:1234/v1
```

Use the model ID exposed by LM Studio.

---

## vLLM

vLLM can also expose an OpenAI-compatible inference endpoint.

A typical endpoint may look similar to:

```text
http://127.0.0.1:8000/v1
```

Use the exact model ID configured in the vLLM server.

---

# 🔌 Custom OpenAI-Compatible Endpoint

The Custom OpenAI-Compatible option can be useful for services or self-hosted runtimes that expose an OpenAI-compatible API.

Examples may include:

- Self-hosted inference servers
- AI gateways
- Internal enterprise AI endpoints
- OpenAI-compatible proxy services

You will normally need:

```text
Endpoint
Model ID
API Key (if required)
```

---

# 🧩 Multi-Language Codebase Support

The scanner is designed to work with text-based source code from many common development stacks.

Typical examples include:

```text
Python
PHP
JavaScript
TypeScript
HTML
CSS
SCSS
JSON
XML
YAML
Markdown
Java
C
C++
C#
Go
Rust
Ruby
Shell
SQL
Vue
React-related source files
Configuration files
```

Exact file-extension support depends on the scanner configuration in the current script.

---

# 📈 Example Review Session

```text
============================================================
                     TOKENIZER REPORT
============================================================

Project Path : C:\Projects\Data Insight
Files        : 73
Total Size   : 1.60 MB
Total LOC    : 13,861
Tokens       : 606,913

Do you want to perform AI Code Review? [Y/N]: Y
```

Provider selection:

```text
============================================================
                    AI PROVIDER SELECTOR
============================================================

1. OpenRouter
2. OpenAI
3. Anthropic
4. xAI
5. DeepSeek
6. Google Gemini
7. Mistral
8. Groq
9. Together AI
10. Ollama (Local)
11. LM Studio (Local)
12. vLLM (Local)
13. Custom OpenAI-Compatible
```

After selecting a provider/model:

```text
============================================================
                  STARTING AI CODE REVIEW
============================================================

Provider: groq
Model: openai/gpt-oss-20b

Context assumed: 131,072 tokens
Safe input budget: 3,100 code tokens/chunk
Initial review chunks: 5
```

Completion:

```text
============================================================
                      REVIEW COMPLETE
============================================================

Status:      needs_attention
Findings:    8
HTML report: ...\ai_code_review_reports\report.html
```

---

# 🛡️ Structured AI Output

The reviewer attempts to make AI responses machine-readable so findings can be converted into the final report.

A conceptual finding looks like:

```json
{
  "category": "Security",
  "severity": "High",
  "file": "src/auth.php",
  "line": 84,
  "line_end": 90,
  "title": "Potential SQL Injection",
  "evidence": "User input is concatenated into a query.",
  "why": "Untrusted input may alter the SQL statement.",
  "fix": "Use parameterized queries / prepared statements.",
  "confidence": "High"
}
```

Structured output makes it easier to organize findings by:

- Severity
- Category
- File
- Line number

---

# ⚠️ AI Response Validation

AI models do not always follow JSON instructions perfectly.

The application therefore attempts to validate structured responses before adding them to the final report.

If a model repeatedly returns invalid structured output, consider:

- Trying a stronger instruction-following model
- Reducing chunk size
- Using a model with better structured-output support
- Checking provider/model compatibility
- Retrying the review

---

# 🔒 Privacy Considerations

## Cloud AI

When using providers such as:

```text
OpenAI
Anthropic
xAI
DeepSeek
Gemini
Mistral
Groq
Together AI
OpenRouter
```

source-code chunks are sent to the selected external API.

Do not send confidential or proprietary code unless doing so is permitted by your organization's security policy and the selected provider's data-handling terms are acceptable for your use case.

## Local AI

When using:

```text
Ollama
LM Studio
vLLM
```

the review can remain within your local infrastructure, depending on how that runtime itself is configured.

---

# 🧠 Choosing a Model

There is no single best model for every project.

For small tests, a fast or free/low-cost model may be sufficient.

For deeper production reviews, prioritize:

- Strong code reasoning
- Reliable instruction following
- Structured JSON output
- Sufficient context window
- Acceptable API pricing
- Suitable rate limits

For very large repositories, a practical architecture is often:

```text
Local scanner/tokenizer
        ↓
Chunking
        ↓
Local or low-cost first-pass model
        ↓
Suspicious / important findings
        ↓
Higher-quality reasoning model
```

This can substantially reduce cloud API usage.

---

# 💰 API Cost Considerations

API cost depends on several factors:

```text
Total input tokens
+
Prompt/system instruction tokens
+
Repeated context
+
Output tokens
+
Retries
+
Number of review chunks
```

Therefore:

> Repository token count is not necessarily equal to final billed token usage.

A project containing 500,000 source tokens may consume more than 500,000 billed tokens because each review request also contains instructions and generates output.

Always check the current pricing of your selected provider/model before reviewing a very large repository.

---

# 🧹 Recommended Exclusions

For large applications, avoid sending generated or third-party files when they are not useful for review.

Typical directories to exclude include:

```text
.git/
node_modules/
vendor/
dist/
build/
coverage/
.cache/
__pycache__/
.venv/
venv/
logs/
tmp/
```

Other generated assets, binaries, archives, media files, dependency caches, and large datasets should generally not be included in source-code review.

---

# 🐞 Troubleshooting

## `unrecognized arguments`

If your path contains spaces:

❌ Wrong:

```cmd
py ai_code_reviewer.py C:\Users\User\Data Insight
```

✅ Correct:

```cmd
py ai_code_reviewer.py "C:\Users\User\Data Insight"
```

---

## HTTP 400

HTTP `400 Bad Request` does **not automatically mean rate limiting**.

Possible causes include:

- Invalid model ID
- Invalid request format
- Unsupported parameter
- Context limit exceeded
- Provider-specific API incompatibility

Rate limiting is commonly returned as HTTP `429`.

---

## HTTP 401 / 403

Usually check:

- API key
- Provider permissions
- Account/project permissions
- Environment-variable configuration

---

## HTTP 429

Usually indicates API throttling or quota/rate-limit conditions.

The reviewer can use retry and pacing mechanisms where supported.

---

## Context Limit Error

Try:

- Smaller chunks
- A larger-context model
- Removing unnecessary generated files
- Excluding dependencies
- Reviewing individual modules separately

---

## Local Model Not Found

Check:

```bash
ollama list
```

or inspect the active models exposed by LM Studio/vLLM.

Make sure the configured model ID exactly matches the model served by the local runtime.

---

# 📋 Requirements

Recommended environment:

```text
Python 3.10+
Internet connection for Cloud AI APIs
API key for selected Cloud provider
```

For local AI:

```text
Ollama / LM Studio / vLLM
Sufficient system RAM
Optional NVIDIA GPU
Enough VRAM for the selected model
```

---

# 🚀 Planned / Possible Improvements

Potential future improvements include:

- [ ] Git diff-only review
- [ ] Pull Request review
- [ ] GitHub Actions integration
- [ ] SARIF output
- [ ] CI/CD integration
- [ ] Incremental review
- [ ] Changed-files-only mode
- [ ] Automatic issue deduplication
- [ ] Cross-file dependency analysis
- [ ] Multi-model verification
- [ ] Local-model first-pass + cloud verification
- [ ] Historical report comparison
- [ ] Review dashboard
- [ ] Email/Slack notifications
- [ ] Automatic scheduled review
- [ ] Severity-based quality gate
- [ ] Repository risk score

---

# 🕒 Automated / Cron Edition

This repository may also include or provide a separate **non-interactive edition** intended for:

- Ubuntu servers
- Cron jobs
- Scheduled security reviews
- Automated nightly/weekly scans
- CI/CD-style workflows

The interactive edition is intended for manual terminal use, while the non-interactive edition reads its settings from configuration/environment files and can run without user input.

---

# ⚖️ Disclaimer

AI Code Reviewer is an **AI-assisted development tool**, not a replacement for:

- Human code review
- Security audits
- Penetration testing
- Static Application Security Testing (SAST)
- Dependency vulnerability scanning
- Unit/integration testing
- Professional security assessment

AI-generated findings may contain false positives, false negatives, incorrect line references, or incomplete recommendations.

Always verify important findings before modifying production code.

---

# 🤝 Contributing

Contributions are welcome.

You can contribute by:

1. Forking the repository
2. Creating a feature branch

```bash
git checkout -b feature/my-improvement
```

3. Making your changes
4. Testing them
5. Committing

```bash
git commit -m "Add my improvement"
```

6. Pushing the branch

```bash
git push origin feature/my-improvement
```

7. Opening a Pull Request

---

# 🔐 Reporting Security Issues

If you discover a security issue in the reviewer itself, avoid publishing sensitive exploit details in a public GitHub issue.

Use the repository's private security reporting mechanism if one is configured.

---

# 📄 License

Add the license you want to use for this project.

For example:

```text
MIT License
```

If you choose MIT, add a separate `LICENSE` file to the repository.

---

# ⭐ Support

If this project is useful to you:

- ⭐ Star the repository
- 🍴 Fork it
- 🐛 Report bugs
- 💡 Suggest improvements
- 🔧 Submit pull requests

---

## AI Code Reviewer

**Scan. Analyze. Review. Improve.**

Built for developers who want a flexible AI-assisted code review workflow across both **Cloud APIs and Local AI models**.
