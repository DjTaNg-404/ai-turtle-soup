# 选择主持人

玩家与主持人是两个独立角色，可以使用不同服务和不同密钥。在页面顶部点击“主持人配置”选择后端。

| 主持人 | 运行位置 | 要求 | 汤底去向 |
|---|---|---|---|
| Laya Multilingual | 本机 | 安装 `laya` 可选依赖并下载权重 | 仅本机 |
| Jev | 所配置的 API | TypeSafe System One 兼容地址、模型名称、主持人 API Key | 发送给主持人 API |

玩家 API 始终只接收汤面和公开问答。两种主持人都执行相同的“回答当前问题 + 对照完整汤底”流程。

## Laya

```sh
uv sync --locked --extra laya
uv run --locked --extra laya python scripts/download_model.py
uv run --locked --extra laya python run.py
```

选择 Laya 后点击“加载本地主持人”，或开局时自动加载。模型路径和设备通过启动环境变量设置。见[本地模型安装](model-setup.md)。

## Jev

基础安装即可，无需 PyTorch 或本地模型：

```sh
uv sync --locked
uv run --locked python run.py
```

在“主持人配置”中选择 Jev：

- API 地址默认 `https://api.typesafe.ai/v1/systemone`，也接受根地址或 `/v1`。
- 模型默认 `jev-latest`；可以填写账户实际可用的固定模型 ID。
- 填写独立的主持人 API Key，保存后点击“测试主持人连接”。

此适配器针对 [TypeSafe 原生 System One API](https://docs.typesafe.ai/introduction/quickstart)，不是 Chat Completions。其他服务商的 Jev 网关若采用不同协议，需要另写适配器，不能仅靠替换 URL 假定兼容。

存在肯定记录时每轮顺序调用两次，每次以 `state`、`model`、`questions.decision` 发送一个 choice 问题。读取 `answers.decision` 中的 choice 和概率。单题状态只有汤面、汤底和当前问题。第二次只包含整局被肯定的问题与汤底，当前问题仅在被肯定后加入；没有肯定记录时跳过第二次。候选分类协议见 [TypeSafe Choice 文档](https://docs.typesafe.ai/primitives/choice)。

“测试主持人连接”只发送一个简单的连接测试状态，不会读取你的汤底。实际对局则会将完整汤底与必要的问答发送到所填 API 地址。

当前已用官方请求、响应结构完成模拟协议测试和游戏联调。尚未用真实 Jev 账户完成在线验收；需要使用者自己的 API Key。模拟测试不代表服务实时可用或判决准确。

## 切换与回放

- 运行中的轮次禁止切换主持人；暂停后保存新主持人，下一轮生效。
- 每轮记录主持人类型、名称和配置的模型 ID。旧版没有这些字段的对局按 Laya 记录读取。
- 主持人调用失败时，玩家的问题保存在 pending，重试沿用该问题。
- 主持人配置保存在 `.data/judge-settings.json`，不含密钥。
- 密钥仅存内存；相同类型与地址下留空可以保留当前密钥，更换地址不会沿用旧密钥。

## 新增后端

实现 `DecisionJudge` 接口并在工厂、配置类型和页面中注册即可。共享逻辑与肯定证据上下文见[架构文档](architecture.md#扩展主持人后端)。
