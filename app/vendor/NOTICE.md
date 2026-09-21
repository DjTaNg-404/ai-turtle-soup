# Laya third-party code

- File in this project: `laya_common.py`.
- Upstream file: `rl_common.py`, copied without modification.
- Author: Convai Innovations / NandhaKishorM.
- License: Apache-2.0; the supplied terms are preserved in [LICENSE.laya](LICENSE.laya).
- Project: https://github.com/NandhaKishorM/laya
- Exact source: https://huggingface.co/convaiinnovations/laya/blob/1c5edc17a7acd8701df6fc341c0d179f1c62c982/rl_common.py
- SHA-256: `8d83611d480c971d640a7b7d3aa2f2219c5e8455e9cc2329fd073681bd8be23e`.

The vendored file was compared byte-for-byte with that upstream revision.
Game prompts, checkpoint loading, tokenizer compatibility handling and the
web application are maintained outside this file.

Weights and tokenizer data are not distributed with this source tree.
The download helper fetches the `multilingual/` checkpoint from the same
pinned Hugging Face revision. See the [upstream model card](https://huggingface.co/convaiinnovations/laya)
for model information and licensing.
