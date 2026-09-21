# Contributing / 参与贡献

欢迎改进问题判定、上下文组织、界面、文档和测试。问题与建议可以使用仓库的 [Issues](https://github.com/DjTaNg-404/ai-turtle-soup/issues)；代码改动可以提交 Pull Request。Please use the repository's Issues and Pull Requests for bugs, ideas, documentation and code changes.

安全漏洞请按 [SECURITY.md](SECURITY.md) 的方式反馈。For vulnerabilities, follow the security policy rather than publishing sensitive details in an issue.

## 本地开发

```sh
uv sync --locked --dev
uv run --locked pytest -q
uv run --locked python -m compileall -q app scripts tests run.py
node --check static/app.js
```

Node.js 只用于可选的 JavaScript 语法检查，不是运行网页的依赖。

测试使用模拟 API 和裁判输出，不需要密钥或权重。测试不能证明真实 Laya 判决准确，也不能证明某个服务商的实际可用性。

如需测试真实裁判：

```sh
uv run --locked --extra laya python scripts/download_model.py
uv run --locked --extra laya python scripts/smoke_judge.py
```

`tests/mock_player_server.py` 提供端口 8766 的脚本化联调接口，名称和输出固定，不是真实玩家模型。只有主动将玩家 API 地址配置为该接口时才会使用它：

```sh
uv run --locked python tests/mock_player_server.py
```

网页配置地址 `http://127.0.0.1:8766/v1`、模型名称 `scripted-demo`，密钥留空。主持人另行配置为 Laya 或 Jev；这个脚本仅模拟玩家。

## 提交改动

- 描述具体问题、修改后的行为和已经完成的验证。
- 玩家消息不得包含汤底、裁判内部概率或私有推理。
- 修改提示词、历史窗口、通关条件时，同步更新 `docs/architecture.md`。
- 保留普通文字玩家调用，不引入强制 JSON 或固定输出上限作为默认设置。
- 对行为修复添加能重现问题的测试；文案等小改动无需机械增加测试。
- 不提交模型权重、API Key、`.data/`、本地缓存或私人对局。
- 上游代码集中在 `app/vendor/`。更新时记录版本和修改内容，保留原始许可。
- 贡献遵循本项目的 Apache-2.0 许可证，无需额外签署 CLA。

## 依赖

`pyproject.toml` 声明直接依赖，`uv.lock` 固定跨平台解析结果。`requirements.lock.txt`（基础）与 `requirements-laya.lock.txt`（包含本地模型依赖）由同一份锁文件导出，不手工维护：

```sh
uv lock
uv export --locked --format requirements-txt --all-groups --no-hashes --no-header --no-emit-project --output-file requirements.lock.txt
uv export --locked --format requirements-txt --all-groups --all-extras --no-hashes --no-header --no-emit-project --output-file requirements-laya.lock.txt
uv sync --locked --dev
uv run --locked pytest -q
```

升级 PyTorch、Transformers 或分词器依赖后，另跑真实模型烟雾检查，记录设备和版本。CI 不会下载 Laya 模型或调用付费 API。

## 准备发行包

仓库的 `.gitignore` 排除了运行数据、权重、环境和导出文件。发布前先检查 Git 中实际纳入的文件；从已提交的源码生成发行包可以使用：

```sh
git archive --format=zip --prefix=ai-turtle-soup/ --output=/tmp/ai-turtle-soup-source.zip HEAD
```

不要直接压缩整个使用中的工作目录：里面可能有本地记录和模型缓存。
