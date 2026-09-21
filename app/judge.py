from __future__ import annotations
import json
import os
import shutil
import threading
import time
from pathlib import Path
from .judging import DecisionJudge, JudgeError
from .model_files import missing_model_files, resolve_model_dir

# Explicitly offline model construction. No model code or weights are fetched at runtime.
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

class LayaJudge(DecisionJudge):
    def __init__(self, model_dir=None, cache_dir=None):
        self.model_dir = resolve_model_dir(model_dir)
        self.cache_dir = Path(cache_dir or Path(__file__).resolve().parents[1] / ".cache/tokenizer")
        self.lock = threading.Lock()
        self.ready = False
        self.loading = False
        self.device = None
        self.error = None

    def status(self):
        return {"ready": self.ready, "loading": self.loading, "device": self.device,
                "name": "Laya Multilingual", "provider": "laya", "model_dir": str(self.model_dir), "error": self.error,
                "context": getattr(self, "cfg", {}).get("max_len", 1024)}

    def load(self):
        with self.lock:
            if self.ready:
                return self.status()
            self.loading = True
            self.error = None
            try:
                missing = missing_model_files(self.model_dir)
                if missing:
                    raise JudgeError(
                        "Laya 模型文件不完整，缺少：" + "、".join(missing)
                        + "。请执行 python scripts/download_model.py 下载模型，"
                        + "或将 LAYA_MODEL_DIR 设置为已有的 multilingual 模型目录。"
                    )
                self._load()
                self.ready = True
            except JudgeError as exc:
                self.error = str(exc)
                raise
            except Exception as exc:
                self.error = f"Laya 加载失败：{type(exc).__name__}。请查看终端并检查本地模型目录与依赖。"
                import traceback
                traceback.print_exc()
                raise JudgeError(self.error) from None
            finally:
                self.loading = False
            return self.status()

    def _load(self):
        try:
            import torch
            from safetensors.torch import load_file
            from transformers import AutoTokenizer
        except ImportError:
            raise JudgeError("使用本地 Laya 请先执行 uv sync --locked --extra laya 安装可选依赖。") from None
        from .vendor.laya_common import build_model
        self.cfg = json.loads((self.model_dir / "rl_agent_config.json").read_text())
        # Normalize a project-local tokenizer copy, never edit original model files.
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        for p in (self.model_dir / "tokenizer").glob("*.json"):
            shutil.copyfile(p, self.cache_dir / p.name)
        config_path = self.cache_dir / "tokenizer_config.json"
        tc = json.loads(config_path.read_text())
        if tc.get("tokenizer_class") in (None, "TokenizersBackend"):
            tc["tokenizer_class"] = "PreTrainedTokenizerFast"
            tc.pop("backend", None)
        extra = tc.get("extra_special_tokens")
        if isinstance(extra, list):
            tc["extra_special_tokens"] = {f"extra_{i}": v for i, v in enumerate(extra)}
        config_path.write_text(json.dumps(tc, ensure_ascii=False))
        self.tok = AutoTokenizer.from_pretrained(str(self.cache_dir), local_files_only=True)
        self.model = build_model(self.cfg, encoder_dir=str(self.model_dir / "encoder"))
        self.model.encoder.config.reference_compile = False
        self.model.load_state_dict(load_file(str(self.model_dir / "model.safetensors")), strict=True)
        preferred = os.getenv("LAYA_DEVICE", "auto")
        if preferred == "auto":
            preferred = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
        if preferred not in {"cpu", "mps", "cuda"}:
            raise ValueError("LAYA_DEVICE must be auto, cpu, mps or cuda")
        self.device = preferred
        self.model.to(self.device).eval()
        if self.device == "cpu":
            torch.set_num_threads(min(8, os.cpu_count() or 4))

    def predict(self, state, instructions, criteria):
        import torch
        import numpy as np
        from .vendor.laya_common import build_sequence, collate_items, confidence_from_probs, temp_bucket
        if not self.ready:
            raise JudgeError("请先加载本地 Laya 裁判。")
        q = {"t": "choice", "ins": instructions, "crit": criteria}
        # Refuse silent truncation: the upstream builder otherwise silently drops late facts.
        ids_full, _ = build_sequence(self.tok, state, q, 100000, self.cfg["head_max_len"])
        if len(ids_full) > self.cfg["max_len"]:
            raise JudgeError(f"裁判输入需要 {len(ids_full)} tokens，超过模型的 {self.cfg['max_len']} 上限。请缩短汤底或问题后新开一局。")
        ids, markers = build_sequence(self.tok, state, q, self.cfg["max_len"], self.cfg["head_max_len"])
        items = [{"ids": ids, "markers": markers, "qtype": 0, "target": [0.0]*len(criteria), "label": -1,
                  "episode": 0, "ep_step": 0, "ep_len": 1, "src": "game"}]
        b = collate_items([items], self.tok.pad_token_id)
        with torch.inference_mode():
            logits, _ = self.model(*[b[k].to(self.device) for k in ["input_ids", "attention_mask", "marker_pos", "marker_mask", "qtype"]])
        z = logits[0, :len(criteria)].float().cpu().numpy()
        temperature = self.cfg.get("temperature_by_options", {}).get(temp_bucket(0, len(criteria)), self.cfg.get("temperature", [1])[0])
        z = z / temperature
        probs = np.exp(z - z.max())
        probs /= probs.sum()
        labels = list(criteria)
        return {"choice": labels[int(probs.argmax())], "probabilities": dict(zip(labels, [round(float(x), 4) for x in probs])),
                "confidence": round(confidence_from_probs(probs, len(probs)), 4), "tokens": len(ids)}

    def fits(self, state, instructions, criteria):
        from .vendor.laya_common import build_sequence
        q = {"t": "choice", "ins": instructions, "crit": criteria}
        ids, _ = build_sequence(self.tok, state, q, 100000, self.cfg["head_max_len"])
        return len(ids) <= self.cfg["max_len"]
