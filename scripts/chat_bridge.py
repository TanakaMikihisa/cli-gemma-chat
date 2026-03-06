#!/usr/bin/env python3
"""
chat_bridge.py — TypeScript UI と Python バックエンドを stdio JSON で繋ぐブリッジ。
stdin から JSON コマンドを受け取り、stdout に JSON イベントを返す。
"""
import contextlib
import io
import json
import os
import shutil
import sys
import textwrap
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path

os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
import logging
import warnings

logging.getLogger("transformers").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

BASE_DIR = Path(__file__).resolve().parent.parent
PRE_LOADING_DIR = BASE_DIR / "pre_loading_data"
MEMORY_DIR = BASE_DIR / "memory"
MEMORY_FILE = MEMORY_DIR / "memory.md"
CONFIG_FILE = BASE_DIR / "config.json"

sys.path.insert(0, str(BASE_DIR))

CONSOLIDATE_AFTER = 10

_MONTHS_EN = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

_output_lock = threading.Lock()


def emit(event_type: str, data: dict | None = None):
    msg = json.dumps({"type": event_type, "data": data or {}}, ensure_ascii=False)
    with _output_lock:
        sys.__stdout__.write(msg + "\n")
        sys.__stdout__.flush()


# ── config / data loading ──

def load_config() -> dict:
    if not CONFIG_FILE.is_file():
        return {}
    try:
        raw = CONFIG_FILE.read_text(encoding="utf-8")
        cfg = json.loads(raw)
        return cfg if isinstance(cfg, dict) else {}
    except Exception:
        return {}


def load_pre_loading_data() -> str:
    if not PRE_LOADING_DIR.is_dir():
        return ""
    parts = []
    for path in sorted(PRE_LOADING_DIR.rglob("*.md")):
        try:
            parts.append(path.read_text(encoding="utf-8").strip())
        except OSError:
            continue
    return "\n\n---\n\n".join(p for p in parts if p)


def load_memory() -> str:
    if not MEMORY_FILE.is_file():
        return ""
    try:
        return MEMORY_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


# ── context (date/location/weather) ──

def fetch_current_context_md() -> str:
    lines = []
    now = datetime.now()
    date_str = f"{now.day} {_MONTHS_EN[now.month - 1]} {now.year}, {now.strftime('%H:%M')}"
    lines.append(f"- **Date/time**: {date_str}")
    try:
        req = urllib.request.Request(
            "http://ip-api.com/json/?fields=lat,lon,city,regionName,country",
            headers={"User-Agent": "GemmaChat/1.0"},
        )
        with urllib.request.urlopen(req, timeout=3) as r:
            loc = json.loads(r.read().decode())
        lat, lon = loc.get("lat"), loc.get("lon")
        city = loc.get("city") or ""
        region = loc.get("regionName") or ""
        country = loc.get("country") or ""
        place_parts = [p for p in (city, region, country) if p]
        if place_parts:
            lines.append(f"- **Location**: {', '.join(place_parts)}")
        if lat is not None and lon is not None:
            try:
                url = (
                    f"https://api.open-meteo.com/v1/forecast?"
                    f"latitude={lat}&longitude={lon}&current=temperature_2m,weather_code&timezone=auto"
                )
                with urllib.request.urlopen(url, timeout=3) as r:
                    w = json.loads(r.read().decode())
                cur = w.get("current", {})
                temp = cur.get("temperature_2m")
                code = cur.get("weather_code", 0)
                if temp is not None:
                    lines.append(f"- **Weather**: {temp}°C ({_weather_code_to_short(code)})")
            except Exception:
                pass
    except Exception:
        pass
    return "\n".join(lines) if len(lines) > 1 else (lines[0] if lines else "")


def _weather_code_to_short(code: int) -> str:
    if code == 0: return "Clear"
    if code in (1, 2, 3): return "Partly cloudy"
    if code in (45, 48): return "Fog"
    if code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82): return "Rain"
    if code in (71, 73, 75, 77, 85, 86): return "Snow"
    if code in (95, 96, 99): return "Thunderstorm"
    return "Cloudy"


# ── message building ──

def _to_content(text: str):
    return [{"type": "text", "text": text}]


def _build_messages(context_md: str | None, messages: list[dict]) -> list[dict]:
    out = []
    if context_md and context_md.strip():
        out.append({
            "role": "system",
            "content": _to_content(
                "以下は過去のメモ・事前情報の参照用です。必要に応じて使ってください。"
                "応答は**いまのユーザーの発言**を最優先し、過去の話題に引きずられないでください。"
                "会話では「記憶の棚」という語や、それについて尋ねる言い方はせず、自然に話してください。"
                "知らないことは知ったかぶりをせず、興味を持って聞き返してよい。無理に話を和ませる必要はない。\n\n"
                + context_md.strip()
            ),
        })
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if isinstance(content, list):
            out.append({"role": role, "content": content})
        else:
            out.append({"role": role, "content": _to_content(str(content))})
    return out


def _build_full_context(pre_loaded: str, memory_md: str, current_md: str = "") -> str:
    parts = []
    if memory_md.strip():
        parts.append("【記憶の棚】（最優先・必要時のみ参照）\n" + memory_md.strip())
    if pre_loaded.strip():
        parts.append("【事前読み込み】（pre_loading_data）\n" + pre_loaded.strip())
    if current_md.strip():
        parts.append("【いま】（補足・参考）\n" + current_md.strip())
    return "\n\n---\n\n".join(parts) if parts else ""


# ── inference ──

@contextlib.contextmanager
def _suppress_stderr():
    if not sys.stderr.isatty():
        yield
        return
    stderr_fd = sys.stderr.fileno()
    with open(os.devnull, "w") as devnull:
        save_fd = os.dup(stderr_fd)
        try:
            sys.stderr.flush()
            os.dup2(devnull.fileno(), stderr_fd)
            yield
        finally:
            sys.stderr.flush()
            os.dup2(save_fd, stderr_fd)
            os.close(save_fd)


def chat(pipe, context_md: str | None, messages: list[dict]) -> str:
    if not messages:
        return ""
    built = _build_messages(context_md, messages)
    from transformers import GenerationConfig
    from scripts.pipe_loader import run_chat
    gen_cfg = GenerationConfig(max_new_tokens=2048, max_length=4096, do_sample=False)
    with _suppress_stderr():
        reply = run_chat(pipe, built, gen_cfg)
    return reply.strip()


def summarize_memory(pipe, memory_md: str, messages: list[dict]) -> str:
    parts = []
    if memory_md.strip():
        parts.append("【既存の記憶】\n" + memory_md.strip())
    parts.append("【直近の会話】")
    for m in messages:
        role = m.get("role", "?")
        content = m.get("content", "")
        if isinstance(content, list):
            text = next((c.get("text", "") for c in content if c.get("type") == "text"), "")
        else:
            text = str(content)
        parts.append(f"- {role}: {text[:200]}{'...' if len(text) > 200 else ''}")
    prompt = "\n\n".join(parts)
    system = (
        "以下の会話を「記憶ノート」として、短い要約にまとめてください。\n"
        "・「どんな話をしたか」がわかる程度の、非常にアバウトなメモでよい。これは具体的な話の中身というよりも内容の種類などに注目してほしい。\n"
        "・細かく書かず、5行で、それぞれの行は最大100文字です。\n"
        "・ユーザー名・端末名・メモリ容量など固定の個人情報は書かないでください。"
    )
    msgs = [
        {"role": "system", "content": _to_content(system)},
        {"role": "user", "content": _to_content(prompt)},
    ]
    from transformers import GenerationConfig
    from scripts.pipe_loader import run_chat
    with _suppress_stderr():
        new_md = run_chat(pipe, msgs, GenerationConfig(max_new_tokens=768, max_length=2048, do_sample=False))
    return new_md.strip()


# ── context parsing for UI ──

def _parse_context_md(md: str) -> dict:
    info: dict = {}
    for line in (md or "").strip().split("\n"):
        line = line.strip()
        if not line.startswith("- **"):
            continue
        rest = line[2:].strip()
        if rest.startswith("**Date/time**:"):
            info["date"] = rest.split(":", 1)[1].strip()
        elif rest.startswith("**Location**:"):
            info["location"] = rest.split(":", 1)[1].strip()
        elif rest.startswith("**Weather**:"):
            value = rest.split(":", 1)[1].strip()
            weather_desc = ""
            if "(" in value and ")" in value:
                weather_desc = value[value.index("(") + 1: value.index(")")].strip()
                value = value[:value.index("(")].strip()
            info["weather"] = value
            info["weather_desc"] = weather_desc
    return info


# ── main loop ──

def main():
    cfg = load_config()
    assistant_name = str(cfg.get("assistant_name") or "Assistant")
    user_name = str(cfg.get("user_name") or "You")
    emit("config", {"assistant_name": assistant_name, "user_name": user_name})

    from scripts.pipe_loader import check_model_availability, set_load_progress_callback

    model_statuses = check_model_availability()
    emit("models", {"models": model_statuses})

    def _on_progress(loaded: int, total: int):
        emit("load_progress", {"loaded": loaded, "total": total})

    set_load_progress_callback(_on_progress)

    try:
        with _suppress_stderr(), contextlib.redirect_stdout(io.StringIO()):
            from scripts.pipe_loader import get_pipe
            pipe = get_pipe()
    except Exception as e:
        emit("error", {"message": f"モデルを読み込めませんでした: {e}"})
        sys.exit(1)
    finally:
        set_load_progress_callback(None)

    _cfg_pipe = getattr(pipe, "model", None) and getattr(pipe.model, "config", None)
    _model_id = getattr(_cfg_pipe, "_name_or_path", None) if _cfg_pipe else None
    _model_display = (_model_id.split("/")[-1] if _model_id and "/" in _model_id else _model_id) or ""

    emit("model_loaded", {"model_name": _model_display})

    pre_loaded = load_pre_loading_data()
    memory_md = load_memory()
    current_md = fetch_current_context_md()
    emit("context_info", _parse_context_md(current_md))

    recent_messages: list[dict] = []

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            cmd = json.loads(line)
        except json.JSONDecodeError:
            continue

        action = cmd.get("action", "")

        if action == "quit":
            _finalize_and_exit(pipe, memory_md, recent_messages)
            break

        if action == "chat":
            text = cmd.get("text", "").strip()
            if not text:
                continue

            recent_messages.append({"role": "user", "content": text})
            emit("reply_start")

            context = _build_full_context(pre_loaded, memory_md, current_md)
            t0 = time.perf_counter()

            try:
                reply = chat(pipe, context if context.strip() else None, recent_messages)
                elapsed = time.perf_counter() - t0
                text_out = reply or "(応答が空でした)"
                emit("reply_end", {"text": text_out, "elapsed": round(elapsed, 2)})
                recent_messages.append({"role": "assistant", "content": reply})
            except Exception as e:
                emit("error", {"message": str(e)})
                recent_messages.pop()
                continue

            if len(recent_messages) >= CONSOLIDATE_AFTER:
                emit("memory_update", {"status": "start"})
                try:
                    memory_md = summarize_memory(pipe, memory_md, recent_messages)
                    recent_messages = recent_messages[-2:]
                    import scripts.session_memory as session_memory
                    session_memory.save_consolidation(memory_md)
                    emit("memory_update", {"status": "done"})
                except Exception as e:
                    emit("memory_update", {"status": "error", "message": str(e)})

    emit("exit", {"code": 0})


def _finalize_and_exit(pipe, memory_md: str, recent_messages: list[dict]):
    import scripts.session_memory as session_memory

    made_dir = MEMORY_DIR / "made_in_currentchat"
    has_parts = made_dir.is_dir() and list(made_dir.glob("*.md"))

    if len(recent_messages) >= 2 and not has_parts:
        try:
            _md = summarize_memory(pipe, memory_md, recent_messages)
            session_memory.save_consolidation(_md)
        except Exception as e:
            emit("error", {"message": f"save_consolidation failed: {e}"})

    try:
        session_memory.finalize_session(pipe=pipe)
    except Exception as e:
        emit("error", {"message": f"finalize_session failed: {e}"})

    emit("finalize_done")

    from scripts.pipe_loader import release_chat_pipe
    release_chat_pipe()

    import gc
    gc.collect()
    try:
        import torch
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            torch.mps.empty_cache()
    except Exception:
        pass


if __name__ == "__main__":
    main()
