import os
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")

import logging
import warnings
logging.getLogger("transformers").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

from transformers import pipeline
import torch

CHAT_MODEL_ID = "google/gemma-3-4b-it"


def _get_device_and_dtype():
    if torch.cuda.is_available():
        return "cuda", torch.bfloat16
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps", torch.bfloat16
    return "cpu", torch.float32


_pipe = None


def _ensure_huggingface_auth():
    """Hugging Face に未ログインの場合は login を促し、対話的にログインする。"""
    try:
        from huggingface_hub import get_token, login
    except ImportError:
        return
    if get_token():
        return
    print("Not logged in to Hugging Face.")
    print("Model use requires login and accepting the model license (Accept on the model page when required).")
    print(f"  Model: https://huggingface.co/{CHAT_MODEL_ID}")
    print("Starting login… (Get a token at https://huggingface.co/settings/tokens)")
    login()


def release_chat_pipe():
    """チャット用4Bを解放する。"""
    global _pipe
    _pipe = None


def get_pipe():
    """チャット・記憶用パイプライン（4B）。"""
    global _pipe
    if _pipe is None:
        _ensure_huggingface_auth()
        try:
            device, torch_dtype = _get_device_and_dtype()
            _pipe = pipeline(
                "image-text-to-text",
                model=CHAT_MODEL_ID,
                device=device,
                torch_dtype=torch_dtype,
            )
        except OSError as e:
            if "gated repo" in str(e).lower() or "401" in str(e):
                print("To use Gemma: run 'huggingface-cli login' and accept the model license.")
                print(f"  https://huggingface.co/{CHAT_MODEL_ID}")
                raise SystemExit(1) from e
            raise
    return _pipe
