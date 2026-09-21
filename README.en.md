# AI Turtle Soup · AI 海龟汤

[![Tests](https://github.com/DjTaNg-404/ai-turtle-soup/actions/workflows/ci.yml/badge.svg)](https://github.com/DjTaNg-404/ai-turtle-soup/actions/workflows/ci.yml)

Watch an API language model solve a lateral-thinking mystery with a selectable host: local Laya or the Jev API.

You supply a **puzzle and its hidden solution**. The player asks one question per turn, and the host answers **yes / no / irrelevant** while also assessing whether the explanation has been reconstructed. No answer checklist is required.

[中文说明](README.md) · [Architecture](docs/architecture.md) · [Contributing](CONTRIBUTING.md) · [Security](SECURITY.md) · [Apache-2.0](LICENSE)

The interface and player prompt are currently in Chinese. This is an experimental game and observation tool; either host can make incorrect judgments.

## Quick start

Install Python 3.12+ and [uv](https://docs.astral.sh/uv/getting-started/installation/), then clone and start the app:

```sh
git clone https://github.com/DjTaNg-404/ai-turtle-soup.git
cd ai-turtle-soup
uv sync --locked
uv run --locked python run.py
```

For a downloaded source ZIP, extract it and run the two `uv` commands from the extracted project directory.

Open **http://127.0.0.1:8765/**. Enter a puzzle and its solution, configure a Chat Completions API URL, model ID and API key, test the connection, then open the host settings and configure Jev with its own API key. Start or advance one turn once both roles are configured.

The base installation runs the Jev path without PyTorch, Transformers or model weights. Jev receives the hidden solution and makes two sequential API requests per turn when affirmative evidence exists (otherwise only the current question is judged). Player and host credentials are configured separately.

For local Laya instead:

```sh
uv sync --locked --extra laya
uv run --locked --extra laya python scripts/download_model.py
uv run --locked --extra laya python run.py
```

Select Laya in the host settings. The model download is a separate, explicit step. It fetches the pinned Laya Multilingual checkpoint into `models/laya/multilingual/`. The web application loads it offline.

For an existing checkpoint:

```sh
LAYA_MODEL_DIR="/path/to/laya/multilingual" uv run --locked --extra laya python run.py
```

On Windows PowerShell, set `$env:LAYA_MODEL_DIR = "C:\models\laya\multilingual"` before starting. See [model setup](docs/model-setup.md) for the checkpoint layout and device options.

Without uv, create a virtual environment, install `requirements.lock.txt`, and run `run.py`. For Laya, also install `requirements-laya.lock.txt` and run the download helper. No Node.js or frontend build is required.

## How it works

1. The player receives the game rules, puzzle, full public dialogue and round count.
2. The selected host receives the puzzle, hidden solution and current question, and classifies it as yes, no or irrelevant.
3. The selected host compares the hidden solution against all questions affirmed with yes throughout the game, including the current question only if affirmed.
4. The game ends in a win when the current answer is yes and the second judgment is complete.

Player requests only specify `model`, `messages` and `stream: false`. There is no forced JSON format, output-token cap or thinking-mode override. Separate reasoning fields are not used as questions.

Player prompts ask for self-contained questions. Completion requires the confirmed propositions to jointly cover the core events, cause and outcome; merely being true or consistent is insufficient. Original wording and negations are preserved, and questions answered no or irrelevant are excluded. With zero affirmative evidence, completion inference is skipped.

Affirmed records accumulate across the whole game, without an eight-turn cutoff or automatic summaries. The current Laya checkpoint uses a 1,024-token input budget. If the full evidence and solution do not fit, the game pauses with an explicit error and retains the history and pending question; switch to a host supporting longer input and retry. Jev does not apply Laya's token budget; its own provider limits still apply.

See [architecture and prompts](docs/architecture.md) for implementation details.

## Data and operation

- Continuous play, pause after the current turn, single-step execution, retry, replay and JSON export.
- Runs are stored in `.data/runs/`; non-secret player settings in `.data/player-settings.json`, host settings in `.data/judge-settings.json`.
- API keys are held in server memory only and must be re-entered after restarting.
- The player API never receives the hidden solution. A remote Jev host **does receive it**. Local run files and exports **do contain it**.
- Browser drafts and the selected game ID use local storage; API keys do not.
- The server binds only to loopback. This is a single-user local application, without public-hosting authentication.
- API requests, including the connection test, may incur your provider's charges.

Use `LAYA_DEVICE=cpu`, `mps` or `cuda` to override automatic device selection, and `python run.py --port 8767` to change the port. Environment variables must be set in the launching shell; `.env` files are not loaded automatically.

Real inference has been checked on macOS ARM64 / CPU. Linux CI is configured; other real inference environments need their own validation.

## Development

```sh
uv sync --locked --dev
uv run --locked pytest -q
```

Tests use stubs for external APIs and model outputs, so they do not need credentials, PyTorch or checkpoint downloads. Jev protocol tests are mocked; live calls require your own TypeSafe key. For a real local-model check, run `uv run --locked --extra laya python scripts/smoke_judge.py`.

Read [CONTRIBUTING.md](CONTRIBUTING.md) before changing prompts, win conditions or checkpoint handling.

## License and credits

[Apache License 2.0](LICENSE). Vendored Laya code retains its [license and exact provenance](app/vendor/NOTICE.md).

Laya is developed by [Convai Innovations / NandhaKishorM](https://github.com/NandhaKishorM/laya).
Weights are downloaded separately from the [upstream model repository](https://huggingface.co/convaiinnovations/laya), and are not bundled with this independent game integration.


Jev integration follows the [official TypeSafe API](https://docs.typesafe.ai/introduction/quickstart). It uses HTTP and does not bundle Jev weights or server code. See [host configuration](docs/hosts.md).
