# 本地 Laya 安装（可选）

选择 Jev 主持人时可以跳过此文档，无需安装或下载本地模型。

本项目使用 [convaiinnovations/laya](https://huggingface.co/convaiinnovations/laya) 的 multilingual 子目录，适合当前中文游戏输入。版本固定在：

```text
1c5edc17a7acd8701df6fc341c0d179f1c62c982
```

该版本的 `rl_common.py` 与项目中引用的代码逐字节一致。[来源与校验值](../app/vendor/NOTICE.md)随源码保留。不要把英文根模型或 typed-decisions 目录直接替代 multilingual 目录并假定表现一致。

## 下载

从项目根目录执行：

```sh
uv run --locked --extra laya python scripts/download_model.py --dry-run
uv run --locked --extra laya python scripts/download_model.py
```

第一条命令只查询文件和大小。第二条通过 Hugging Face Hub 下载固定版本的权重和 JSON 文件，不下载或执行远程 Python 代码。下载完成后，运行中的游戏只读取本地文件。

预期目录：

```text
models/laya/multilingual/
├── model.safetensors
├── rl_agent_config.json
├── encoder/
│   └── config.json
└── tokenizer/
    ├── tokenizer.json
    └── tokenizer_config.json
```

下载脚本的默认目标相对于项目位置确定，与启动命令时的当前目录无关。`models/` 不会进入 Git。

### 自定义位置

```sh
uv run --locked --extra laya python scripts/download_model.py --output-dir /path/to/laya
LAYA_MODEL_DIR=/path/to/laya/multilingual uv run --locked --extra laya python run.py
```

下载根目录会自动包含 multilingual 子目录。直接启动应用时，`LAYA_MODEL_DIR` 应指向这个子目录。

环境变量优先，其次是项目内模型目录，最后兼容 `~/model/laya/multilingual/` 的旧位置。模型不完整时，页面会显示缺少的文件并提示下载。

### 更换版本

下载助手支持 `--revision COMMIT_OR_TAG`。更换检查点属于实验性操作：上游结构、分词器或权重可能变化，需要同时核对代码与配置，并执行真实推理检查。

完整模型文件默认不随源码发行包分发。模型许可证与说明见[上游模型卡](https://huggingface.co/convaiinnovations/laya)。

## 设备

`LAYA_DEVICE=auto` 根据 PyTorch 报告的可用性依次选择 CUDA、MPS、CPU。也可以显式选择：

```sh
LAYA_DEVICE=cpu uv run --locked --extra laya python scripts/smoke_judge.py
LAYA_DEVICE=cpu uv run --locked --extra laya python run.py
```

macOS ARM64 / CPU 的本地推理已验证。MPS / CUDA 依赖硬件、驱动和所安装的 PyTorch，无法保证每个环境都可用。如果自动选择的设备推理失败，可以先切换 CPU 验证文件与依赖。

输入限制来自检查点配置：当前 `max_len=1024`，`head_max_len=256`。不要把修改输入上限当作已经验证的模型能力提升。

## 下载或加载失败

- 下载需要访问 Hugging Face；网络中断可以重新执行同一命令，Hub 会利用已有缓存。
- 离线机器可以在另一台机器下载后复制整个 multilingual 目录。
- `HF_HUB_OFFLINE=1` 会阻止下载；游戏推理本身以离线方式构造模型。
- 模型 JSON 和权重必须来自兼容版本，不要混合不同目录的文件。
- 项目只在 `.cache/tokenizer/` 中调整兼容配置，不会修改原始模型。
- 真实烟雾检查不调用玩家 API：`uv run --locked --extra laya python scripts/smoke_judge.py`。
