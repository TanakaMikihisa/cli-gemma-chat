import os
import sys
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")

import json
import logging
import warnings
from pathlib import Path
logging.getLogger("transformers").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

from transformers import pipeline
import torch

BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "config.json"

# チャット用モデル: 下の MLX が使えればそれ、なければ Hugging Face から上のモデルをダウンロードして利用
# 上: Transformers 用（Mac 以外 or MLX 失敗時）。5〜7B・テキスト専用（約14GB）
CHAT_MODEL_ID = "Qwen/Qwen2.5-7B-Instruct"
# 下: Mac (Apple Silicon) 用 MLX 8bit。優先して使用。
CHAT_MODEL_ID_MLX = "mlx-community/Gemma-3-Glitter-12B-8bit"
# ローカルに置いたモデル（例: huggingface-cli download ... --local-dir で取得）があればこちらを優先
_LOCAL_MLX_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "gemma-3-glitter-12b-8bit")


def _load_config() -> dict:
    if not CONFIG_FILE.is_file():
        return {}
    try:
        raw = CONFIG_FILE.read_text(encoding="utf-8")
        cfg = json.loads(raw)
        return cfg if isinstance(cfg, dict) else {}
    except Exception:
        return {}


def _get_model_priority(kind: str) -> list[str]:
    """
    kind: "mlx" or "transformers"
    config.json の model_priority から優先順を返す。未設定なら従来の既定値。
    """
    cfg = _load_config()
    mp = cfg.get("model_priority") if isinstance(cfg, dict) else None
    if isinstance(mp, dict):
        lst = mp.get(kind)
        if isinstance(lst, list) and all(isinstance(x, str) for x in lst):
            return [x for x in lst if x.strip()]
    if kind == "mlx":
        # 既定: ローカル → HF repo id
        return [str(Path(_LOCAL_MLX_DIR)), CHAT_MODEL_ID_MLX]
    return [CHAT_MODEL_ID]


def _resolve_local_candidate(candidate: str) -> str | None:
    """
    candidate がローカルパスなら絶対パスを返す。存在しなければ None。
    - 相対パスはプロジェクト直下（pipe_loader.py と同階層）基準で解決
    """
    p = Path(candidate)
    if not p.is_absolute():
        p = (BASE_DIR / p).resolve()
    if p.exists():
        return str(p)
    return None


def _display_name_from_id_or_path(x: str) -> str:
    # パスなら末尾ディレクトリ名、repo id なら最後のセグメント
    try:
        p = Path(x)
        if p.is_absolute() or x.startswith(".") or x.startswith("models/"):
            return p.name or x
    except Exception:
        pass
    return x.split("/")[-1] if "/" in x else x


def _get_device_and_dtype():
    if torch.cuda.is_available():
        return "cuda", torch.bfloat16
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps", torch.bfloat16
    return "cpu", torch.float32


_pipe = None
_using_mlx = False


class _MLXPipelineWrapper:
    """MLX の load/generate を transformers の pipeline と互換なインターフェースで包む。"""

    def __init__(self, model, tokenizer, model_id: str):
        self._model = model
        self.tokenizer = tokenizer
        self.model = type("_FakeConfig", (), {})()
        self.model.config = type("_Config", (), {"_name_or_path": model_id})()

    def __call__(self, prompt, generation_config=None, return_full_text=False):
        from mlx_lm import generate as mlx_generate
        max_tokens = 2048
        if generation_config is not None:
            max_tokens = getattr(generation_config, "max_new_tokens", max_tokens)
        response = mlx_generate(
            self._model,
            self.tokenizer,
            prompt=prompt,
            max_tokens=max_tokens,
            verbose=False,
        )
        text = response if isinstance(response, str) else getattr(response, "text", str(response))
        return [{"generated_text": text.strip()}]


def _try_load_mlx():
    """Mac (Darwin) かつ mlx_lm が使える場合に MLX パイプラインを返す。失敗時は None。"""
    if sys.platform != "darwin":
        return None
    try:
        from mlx_lm import load as mlx_load
    except ImportError:
        return None
    last_err: Exception | None = None
    for cand in _get_model_priority("mlx"):
        local = _resolve_local_candidate(cand)
        model_path = local or cand
        if local is None and (cand.startswith("/") or cand.startswith(".") or cand.startswith("models/")):
            continue
        if local is None:
            _ensure_huggingface_auth(cand)
        try:
            model, tokenizer = mlx_load(model_path)
            return _MLXPipelineWrapper(model, tokenizer, _display_name_from_id_or_path(model_path))
        except Exception as e:
            last_err = e
            continue
    if last_err is not None:
        print(f"MLX load failed: {last_err}", file=sys.stderr)
    return None


def _ensure_huggingface_auth(model_id: str | None = None):
    """Hugging Face に未ログインの場合は login を促し、対話的にログインする。"""
    try:
        from huggingface_hub import get_token, login
    except ImportError:
        return
    if get_token():
        return
    mid = model_id or CHAT_MODEL_ID
    print("Not logged in to Hugging Face.")
    print("Model use requires login and accepting the model license (Accept on the model page when required).")
    print(f"  Model: https://huggingface.co/{mid}")
    print("Starting login… (Get a token at https://huggingface.co/settings/tokens)")
    login()


def release_chat_pipe():
    """チャット用パイプラインを解放する。"""
    global _pipe, _using_mlx
    _pipe = None
    _using_mlx = False


def _messages_to_plain(messages: list[dict]) -> list[dict]:
    """content が [{"type":"text","text":...}] の形なら文字列に寄せる。"""
    out = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if isinstance(content, list):
            content = " ".join(
                x.get("text", "") for x in content if isinstance(x, dict) and x.get("type") == "text"
            )
        out.append({"role": role, "content": str(content)})
    return out


def run_chat(pipe, messages: list[dict], generation_config) -> str:
    """
    テキスト用パイプラインでメッセージから応答を生成する。
    messages は [{"role": "system"|"user"|"assistant", "content": str or [...]}]。
    戻り値はモデルの応答テキストのみ。
    """
    if not messages:
        return ""
    plain = _messages_to_plain(messages)
    tokenizer = pipe.tokenizer
    prompt = tokenizer.apply_chat_template(
        plain,
        tokenize=False,
        add_generation_prompt=True,
    )
    out = pipe(prompt, generation_config=generation_config, return_full_text=False)
    gen = out[0].get("generated_text") if out else None
    if isinstance(gen, list):
        return (gen[-1].get("content", "") if gen else "") or ""
    return (str(gen).strip() if gen else "") or ""


def get_pipe():
    """チャット・記憶用パイプライン（テキスト専用）。Mac では MLX を優先。"""
    global _pipe, _using_mlx
    if _pipe is None:
        if sys.platform == "darwin":
            _pipe = _try_load_mlx()
            if _pipe is not None:
                _using_mlx = True
                return _pipe
        _using_mlx = False
        device, torch_dtype = _get_device_and_dtype()
        model_kwargs = {"attn_implementation": "sdpa"}
        last_err: Exception | None = None
        for model_id in _get_model_priority("transformers"):
            _ensure_huggingface_auth(model_id)
            try:
                try:
                    _pipe = pipeline(
                        "text-generation",
                        model=model_id,
                        device=device,
                        torch_dtype=torch_dtype,
                        model_kwargs=model_kwargs,
                    )
                except (ValueError, TypeError, KeyError):
                    _pipe = pipeline(
                        "text-generation",
                        model=model_id,
                        device=device,
                        torch_dtype=torch_dtype,
                    )
                return _pipe
            except OSError as e:
                last_err = e
                # ログイン/許諾が必要、または取得できない場合は次の候補へ
                if "gated repo" in str(e).lower() or "401" in str(e):
                    continue
                continue
        if last_err is not None:
            raise last_err
        raise RuntimeError("No model could be loaded. Check config.json model_priority and network connectivity.")
    return _pipe
