# AI 海龟汤 · AI Turtle Soup

[![Tests](https://github.com/DjTaNg-404/ai-turtle-soup/actions/workflows/ci.yml/badge.svg)](https://github.com/DjTaNg-404/ai-turtle-soup/actions/workflows/ci.yml)

让 AI 玩海龟汤，支持自定义题目、玩家模型和主持人模型。

你提供汤面和汤底，接入一个大模型 API 作为玩家，自选模型作为主持人（本地 Laya 或 Jev API）。玩家每轮问一个问题，裁判回答“是 / 不是 / 无关”，同时判断故事是否已经还原。

[English](README.en.md) · [上下文与架构](docs/architecture.md) · [参与贡献](CONTRIBUTING.md) · [安全问题反馈](SECURITY.md) · [Apache-2.0](LICENSE)

## 可以做什么

- 只填汤面与汤底，不需要通关要点或答案清单。
- 使用兼容 Chat Completions 的模型 API；玩家直接返回普通文字。
- 观看逐轮提问、裁判答案、候选项概率与耗时。
- 连续运行、暂停、单步推进、失败重试，或回看和导出对局。
- 主持人独立配置：本地 Laya Multilingual 或 Jev API；两边的密钥彼此独立。
- 只使用 Jev 时，无需安装 PyTorch、Transformers 或下载 Laya 权重。

这是一个实验性游戏和模型观察工具。主持人的判决可能出错，页面中的概率不是游戏准确率；“通关”表示所选主持人判定通过。

## 快速开始

需要 Python 3.12+。推荐使用 [uv](https://docs.astral.sh/uv/getting-started/installation/) 管理环境。网页不需要 Node.js 或前端构建。

克隆并启动：

```sh
git clone https://github.com/DjTaNg-404/ai-turtle-soup.git
cd ai-turtle-soup
uv sync --locked
uv run --locked python run.py
```

如果下载的是源码 ZIP，先解压，在解压后的项目目录运行以上两个 `uv` 命令。

打开 [http://127.0.0.1:8765/](http://127.0.0.1:8765/)：

1. 填写汤面和汤底，也可以点击“填入示例”。
2. 点击“接入玩家”，填写 API 地址、模型名称、API Key。
3. 点击“主持人配置”，选择 **Jev**，填写 TypeSafe 兼容端点、模型名称和独立的主持人 API Key，保存并测试。
4. 点击“测试玩家连接”，确认玩家也能收到文字回答。
5. 点击“开始对局”，或用“下一轮”单步观察。

以上是无需本地模型的 Jev 路径。要使用 Laya，按下面安装可选依赖，然后在“主持人配置”里选择 Laya。

玩家每轮请求一次 API；有肯定记录时，Jev 主持人每轮顺序请求两次 API；尚无肯定记录时只回答当前问题。连接测试也会发起请求，按服务商的计费方式计费。选择 Jev 时，完整汤底会发送到所配置的主持人 API；选择 Laya 时，裁判推理在本机进行。

### 使用本地 Laya（可选）

```sh
uv sync --locked --extra laya
uv run --locked --extra laya python scripts/download_model.py
uv run --locked --extra laya python run.py
```

在“主持人配置”中选择 Laya，可提前加载，也可在开局时自动加载。

### 已经下载过 Laya 模型

将 `LAYA_MODEL_DIR` 指向包含 `model.safetensors` 的 **multilingual 目录**：

```sh
# macOS / Linux
LAYA_MODEL_DIR="/path/to/laya/multilingual" uv run --locked --extra laya python run.py
```

```powershell
# Windows PowerShell
$env:LAYA_MODEL_DIR = "C:\models\laya\multilingual"
uv run --locked --extra laya python run.py
```

默认先查找项目的 `models/laya/multilingual/`；若不存在，也兼容早期安装位置 `~/model/laya/multilingual/`。显式设置的 `LAYA_MODEL_DIR` 优先。

模型下载脚本固定使用一个已核对的上游版本，只下载权重和 JSON 配置。它支持 `--dry-run` 查看待下载文件，以及 `--output-dir` 指定下载根目录。详见 [模型安装](docs/model-setup.md)。

### 不使用 uv

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock.txt
.venv/bin/python run.py
```

Windows 使用 `python -m venv .venv`，并把以上 `.venv/bin/python` 换为 `.venv\Scripts\python.exe`。macOS 安装完成后，也可以双击 `start.command`。

使用 Laya 时，另外安装 `requirements-laya.lock.txt` 并运行 `python scripts/download_model.py`。Laya 的可选依赖包含较大的 PyTorch 安装包。默认运行环境已在 macOS ARM64 / CPU 上验证；仓库包含 Linux CI 配置，其他设备和系统的真实模型推理仍需各自验证。

## 玩家 API

兼容 Chat Completions 的服务均可尝试。API 地址接受根地址、含 `/v1` 的地址，或完整的 `/chat/completions` 端点。模型名称填写服务商实际提供的 ID。

| 配置 | 示例 / 含义 |
|---|---|
| API 地址 | `https://api.deepseek.com` 或本地服务的 `http://127.0.0.1:8000/v1` |
| 模型名称 | 你的服务商提供的模型 ID |
| API Key | 在网页中输入；无鉴权的本地服务可留空 |

每次请求仅指定 `model`、`messages`、`stream: false`。应用不设置生成 token 上限、思考模式、温度或 JSON 输出格式。游戏规则由提示词说明，应用不强制检查问题数量。提示词要求每个问题说清人物与事件，结合汤面即可独立理解，因为单题主持人不看历史。

玩家能看到游戏规则、汤面、全部已完成的问答和当前轮数。它看不到汤底、主持人的概率和阶段判断。单独返回的 `reasoning_content` 不作为提问，也不加入后续历史。

## 主持人如何裁判

Laya 和 Jev 使用同一套判断指令和通关条件。Laya 在本地执行，Jev 通过原生 System One API 执行。详细配置见 [主持人接入](docs/hosts.md)。

每轮回答当前问题；存在肯定记录时再判断进度：

| 判断 | 上下文 | 选项 |
|---|---|---|
| 回答问题 | 汤面、汤底、当前问题 | 是 / 不是 / 无关 |
| 判断进度 | 完整汤底、整局累计的 yes 记录（含当前轮新确认的问题） | 完整还原 / 尚不完整 / 存在矛盾 |

当本轮答案是“是”，且进度判定为完整还原时通关。玩家可以用一个完整的问题说出猜到的经过和原因，无需额外提交解答动作。

通关判断保留问题原文和否定词，只使用被主持人肯定的命题，检查它们能否共同覆盖汤底的核心事件、原因和结果。仅仅正确或不矛盾并不足以通关。没有 yes 记录时显示“尚无肯定线索”，不请求进度分类。

肯定记录跨整局累计，不截取最近 8 轮，也不自动改写成事实摘要。Laya 当前检查点的输入上限是 **1024 tokens**，包括指令和选项；全部肯定记录与汤底放不下时会暂停并提示切换支持更长输入的主持人，历史与当前问题保留。Jev 不使用 Laya 的 token 限制，服务商自己的限制仍然适用。

完整提示词、消息示例、状态流程和已知限制见 [架构文档](docs/architecture.md)。

## 配置、记录与隐私

| 设置 | 默认值 / 作用 |
|---|---|
| `LAYA_MODEL_DIR` | 指定本地 multilingual 模型目录 |
| `LAYA_DEVICE` | `auto`，依次选择 CUDA、MPS、CPU；可指定 `cpu`、`mps`、`cuda` |
| `python run.py --port 8767` | 更换端口；始终只监听 `127.0.0.1` |

环境变量由启动终端设置，应用不自动读取 `.env` 文件。

- 对局保存在 `.data/runs/`；玩家配置保存在 `.data/player-settings.json`，主持人配置保存在 `.data/judge-settings.json`。两个配置文件均不含密钥。
- API Key 只保存在服务内存中，重启后需要重新填写。同一 API 地址下修改配置，密钥留空可保留当前密钥。
- 草稿与选中的对局 ID 保存在浏览器本地；API Key 不进入浏览器存储。
- 汤底不会发给玩家 API；选择 Jev 时会发给主持人 API，也会包含在本地记录和导出文件中。分享对局前请检查其中的内容。
- 页面刷新不停止自动对局；暂停会等待当前轮完成后停止下一次请求。

本项目面向单用户本机使用，没有公网部署所需的用户认证或租户隔离。

## 常见问题

**找不到 Laya 模型**：执行 `uv run --locked --extra laya python scripts/download_model.py`，或检查 `LAYA_MODEL_DIR` 是否指向 multilingual 子目录。

**API 只返回思考，没有正式回答**：应用会提示重试，不会把思考内容冒充问题。检查服务或网关设置；应用没有给生成过程设置 token 上限。

**裁判输入超过 1024 tokens**：这个上限来自当前 Laya 检查点，独立于玩家 API 的生成设置。累计肯定记录超限时不会删除早期线索；可以切换支持更长输入的主持人后重试。单题输入过长则需缩短题目或问题。

**裁判判断不符合预期**：展开判决详情，导出对局，尝试更短或指代更明确的问句。此项目用于观察模型表现，没有另一套规则自动纠正模型答案。

**MPS / CUDA 加载失败**：先用 `LAYA_DEVICE=cpu` 验证本地模型和依赖，详见 [模型安装](docs/model-setup.md)。

## 开发

```sh
uv sync --locked --dev
uv run --locked pytest -q
```

自动测试不需要 API Key、PyTorch 或 Laya 权重，外部调用通过测试替身模拟。Jev 已按官方协议完成模拟联调，真实服务调用需要用户自己的 Jev Key。真实模型烟雾检查可以运行：

```sh
uv run --locked --extra laya python scripts/smoke_judge.py
```

开发流程、依赖更新与测试说明见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可证与致谢

本项目采用 [Apache License 2.0](LICENSE)。引用的 Laya 推理代码保留原始许可证和[来源说明](app/vendor/NOTICE.md)。

Laya 由 [Convai Innovations / NandhaKishorM](https://github.com/NandhaKishorM/laya) 提供，模型信息见 [Hugging Face 模型卡](https://huggingface.co/convaiinnovations/laya)。本项目是独立的游戏集成；源代码发行包不包含模型权重。

Jev 接入参考 [TypeSafe 官方 API 文档](https://docs.typesafe.ai/introduction/quickstart)，通过 HTTP 调用，不包含 Jev 权重或服务端代码。
