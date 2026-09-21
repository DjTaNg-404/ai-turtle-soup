# Security / 安全问题反馈

## Reporting a vulnerability / 报告漏洞

Use the repository's [private vulnerability reporting](https://github.com/DjTaNg-404/ai-turtle-soup/security/advisories/new) when available. Include the affected commit or version, a minimal reproduction with synthetic data, the expected boundary and the observed behavior.

If private reporting is unavailable, open an [issue](https://github.com/DjTaNg-404/ai-turtle-soup/issues/new) asking the maintainer for a private contact channel. Leave out exploit details, API keys, personal data and private puzzle contents until that channel is established. Ordinary bugs can use the bug-report template.

发现漏洞时，优先通过仓库的私密漏洞报告提交受影响版本、使用虚构数据的最小复现步骤，以及预期与实际行为。若该功能暂不可用，可以发一个仅请求私密联系方式的 Issue；请先不要公开利用细节、密钥、个人资料或私人题目。普通功能问题可直接使用 Bug 模板。

## Scope / 适用范围

The current `main` branch is the maintenance target; there is no separate long-term support branch. This is a single-user application intended to run on `127.0.0.1`. Public deployment, authentication and multi-user isolation are not provided.

API keys stay in server memory. Run records and exported JSON contain the hidden solution; a configured remote host receives the hidden solution as part of judging. Use synthetic records when reporting a problem. See the [README](README.md) for the data flow and local storage locations.

目前以 `main` 分支为维护对象，没有单独的长期支持分支。项目面向本机单用户使用；报告问题时请使用虚构的对局数据。数据流和存储位置见 README。
