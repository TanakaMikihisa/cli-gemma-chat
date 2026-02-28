#!/usr/bin/env python3
"""
Gemma を使った CLI チャット。
会話履歴は「記憶」として適度に MD 要約し、コンテキストを圧縮する。
- memory/ … 記憶の棚（会話の要約メモ）。起動時に読み込み、コンテキストで最優先
- pre_loading_data/ … フォルダ内の全 .md（サブフォルダ含む）を起動時に読み込み、記憶の次に参照
- いま … 起動時の現在地・天気・日時を取得し、補足（+alpha）としてコンテキストに含める
"""
import contextlib
import json
import os
import sys
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path

# 入力欄をエディタのようにする（Ctrl+A/Ctrl+E 等が効き、変な記号が入らない）
def _input_line(prompt: str) -> str:
    try:
        from prompt_toolkit import prompt as pt_prompt
        from prompt_toolkit.formatted_text import ANSI
        # ANSI でプロンプトの色を解釈（そのまま渡すと ^[[36m のように出るため）
        return pt_prompt(ANSI(prompt)).strip()
    except Exception:
        pass
    try:
        import readline  # noqa: F401 - Unix で input() を readline に
    except ImportError:
        pass
    return input(prompt).strip()

# 起動直後に警告を抑制（CLI を読みやすくする）
# pipe_loader が import する前に TRANSFORMERS_VERBOSITY を置くと、
# transformers の初回設定で error が使われる
import os
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
import logging
import warnings
logging.getLogger("transformers").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

BASE_DIR = Path(__file__).resolve().parent
PRE_LOADING_DIR = BASE_DIR / "pre_loading_data"
MEMORY_DIR = BASE_DIR / "memory"
MEMORY_FILE = MEMORY_DIR / "memory.md"

CONSOLIDATE_AFTER = 10  # 5往復（ユーザー+応答×5）たまったら要約して記憶に固着

# 表示スタイル（ターミナルが TTY のときだけ色付け。パイプ時は無効）
def _style():
    if not sys.stdout.isatty():
        return type("Style", (), {"dim": "", "bold": "", "you": "", "gemma": "", "ok": "", "yellow": "", "reset": ""})()
    return type("Style", (), {
        "dim": "\033[2m",
        "bold": "\033[1m",
        "you": "\033[36m",
        "gemma": "\033[32m",
        "ok": "\033[32m",
        "yellow": "\033[33m",
        "reset": "\033[0m",
    })()


def load_pre_loading_data() -> str:
    """pre_loading_data/ フォルダ内の全 .md（サブフォルダ含む）を読み込み、1つの文字列にまとめる。"""
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
    """memory/memory.md があればその内容を返し、なければ空文字。"""
    if not MEMORY_FILE.is_file():
        return ""
    try:
        return MEMORY_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


# 英語の日付表記用（月名略称）
_MONTHS_EN = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def fetch_current_context_md() -> str:
    """
    現在地（IPベース）・天気・日時を取得し、1つの Markdown にまとめる。表記は英語。
    記憶は最優先・これは +alpha の補足用。取得失敗時は日時だけなど部分的な返却。
    """
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
        lat = loc.get("lat")
        lon = loc.get("lon")
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

    if len(lines) <= 1:
        return lines[0] if lines else ""
    return "\n".join(lines)


def _weather_code_to_short(code: int) -> str:
    """WMO weather code to short English label."""
    if code == 0:
        return "Clear"
    if code in (1, 2, 3):
        return "Partly cloudy"
    if code in (45, 48):
        return "Fog"
    if code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82):
        return "Rain"
    if code in (71, 73, 75, 77, 85, 86):
        return "Snow"
    if code in (95, 96, 99):
        return "Thunderstorm"
    return "Cloudy"


def _weather_desc_to_emoji(desc: str) -> str:
    """天気の短い説明（英語または日本語）に合わせて絵文字を返す。"""
    if not desc:
        return "🌡"
    d = desc.strip().lower()
    if "clear" in d or "晴" in desc:
        return "☀️" if d == "clear" or desc.strip() == "晴" else "🌤️"
    if "fog" in d or "霧" in desc:
        return "🌫️"
    if "rain" in d or "雨" in desc:
        return "🌧️"
    if "snow" in d or "雪" in desc:
        return "❄️"
    if "thunder" in d or "雷" in desc:
        return "⛈️"
    if "cloud" in d or "曇" in desc or "partly" in d:
        return "☁️"
    return "🌡️"


def _print_current_context(current_md: str) -> None:
    """取得した日時・場所・天気をバナー下に表示する。天気に応じて絵文字をつける。TTY でないときは何もしない。"""
    if not sys.stdout.isatty() or not current_md or not current_md.strip():
        return
    s = _style()
    out = []
    for line in current_md.strip().split("\n"):
        line = line.strip()
        if not line or not line.startswith("- **"):
            continue
        rest = line[2:].strip()
        if rest.startswith("**Date/time**:"):
            value = rest.split(":", 1)[1].strip()
            out.append(f"  {s.dim}📅 {value}{s.reset}")
        elif rest.startswith("**Location**:"):
            value = rest.split(":", 1)[1].strip()
            out.append(f"  {s.dim}📍 {value}{s.reset}")
        elif rest.startswith("**Weather**:"):
            value = rest.split(":", 1)[1].strip()
            weather_desc = ""
            if "(" in value and ")" in value:
                weather_desc = value[value.index("(") + 1 : value.index(")")].strip()
                # 表示は括弧なし（絵文字でわかるため）
                value = value[: value.index("(")].strip()
            emoji = _weather_desc_to_emoji(weather_desc)
            out.append(f"  {s.dim}{emoji} {value}{s.reset}")
    if out:
        print("\n".join(out))
        print()


def save_memory(md: str) -> None:
    """会話の記憶を memory/memory.md に保存する。"""
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    MEMORY_FILE.write_text(md.strip() + "\n", encoding="utf-8")


def _to_content(text: str):
    return [{"type": "text", "text": text}]


def _build_messages(context_md: str | None, messages: list[dict]) -> list[dict]:
    """context_md = 記憶の棚(memory) + pre_loading_data + いま。優先度順。"""
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


@contextlib.contextmanager
def _suppress_stderr():
    """pipe() 実行中の transformers の警告ログを標準エラーに出さないようにする。"""
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
    """context_md に記憶・事前読み込み・いまをまとめた文字列を渡す。"""
    if not messages:
        return ""
    built = _build_messages(context_md, messages)
    # 応答の長さ: 長めに取って途中切れを防ぐ
    from transformers import GenerationConfig
    gen_cfg = GenerationConfig(max_new_tokens=2048, max_length=4096)
    with _suppress_stderr():
        out = pipe(text=built, generation_config=gen_cfg, return_full_text=False)
    gen = out[0].get("generated_text")
    if isinstance(gen, list):
        reply = gen[-1].get("content", "") if gen else ""
    else:
        reply = str(gen) if gen else ""
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
        "・「どんな話をしたか」がわかる程度の、非常にアバウトなメモでよい。\n"
        "・細かく書かず、5行で、それぞれの行は最大100文字です。\n"
        "・ユーザー名・端末名・メモリ容量など固定の個人情報は書かないでください。"
    )
    msgs = [
        {"role": "system", "content": _to_content(system)},
        {"role": "user", "content": _to_content(prompt)},
    ]
    from transformers import GenerationConfig
    with _suppress_stderr():
        out = pipe(text=msgs, generation_config=GenerationConfig(max_new_tokens=768, max_length=2048), return_full_text=False)
    gen = out[0].get("generated_text")
    if isinstance(gen, list):
        new_md = gen[-1].get("content", "") if gen else ""
    else:
        new_md = str(gen) if gen else ""
    return new_md.strip()


# 生成中アニメーション
_SPARKLE_FRAMES = [
    " ·  ",
    "  ✧ ",
    "   ·",
    "  ✧ ",
    " · ✧",
    "  · ✧",
    " ✧ · ",
    "  ✧  ",
]


@contextlib.contextmanager
def _suppress_stderr():
    """標準エラーを抑制（モデル読み込み時の Progress 表示などを隠す）。"""
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


def _sparkle_animation(stop_flag: threading.Event, prefix: str, message: str = "Thinking...", color: str = ""):
    reset = "\033[0m" if color else ""
    i = 0
    while not stop_flag.is_set():
        frame = _SPARKLE_FRAMES[i % len(_SPARKLE_FRAMES)]
        print(f"\r{prefix}{color}{message}{reset}{frame}", end="", flush=True)
        i += 1
        stop_flag.wait(0.12)


# バナー表示用。プロジェクト直下の banner.txt を読み、左→右のグラデーションを付けて表示
BANNER_FILE = BASE_DIR / "banner.txt"

# グラデーション用の ANSI 256色（左→右の順）
_BANNER_GRADIENT = (153, 117, 111, 104, 183, 169, 225, 168)


def _apply_gradient_line(line: str, use_color: bool) -> str:
    """1行を左から右へグラデーションで塗る。"""
    if not use_color or not line:
        return line
    n = len(_BANNER_GRADIENT)
    L = len(line)
    out = []
    last_idx = -1
    for i, c in enumerate(line):
        idx = (i * n) // L if L else 0
        if idx != last_idx:
            out.append(f"\033[38;5;{_BANNER_GRADIENT[idx]}m")
            last_idx = idx
        out.append(c)
    out.append("\033[0m")
    return "".join(out)


def _print_banner():
    """モデル読み込み完了後：banner.txt を読み、左→右グラデーションで表示。"""
    s = _style()
    use_color = sys.stdout.isatty()
    print()
    if BANNER_FILE.is_file():
        try:
            raw = BANNER_FILE.read_text(encoding="utf-8")
            lines = [ln.rstrip() for ln in raw.splitlines() if ln.strip()]
            for line in lines:
                grad_line = _apply_gradient_line(line, use_color)
                print(f"  {s.bold}{grad_line}{s.reset}")
        except OSError:
            print(f"  {s.bold}{s.gemma}GEM CHAT{s.reset}")
    else:
        print(f"  {s.bold}{s.gemma}GEM CHAT{s.reset}")
    print()
    print(f"  {s.dim}▸ Talk to me. Type quit or exit to end.{s.reset}")
    print()


def _build_full_context(pre_loaded: str, memory_md: str, current_md: str = "") -> str:
    """コンテキストを組み立てる。優先度: memory.md 最優先 → pre_loading_data → いま（天気など）。"""
    parts = []
    if memory_md.strip():
        parts.append("【記憶の棚】（最優先・必要時のみ参照）\n" + memory_md.strip())
    if pre_loaded.strip():
        parts.append("【事前読み込み】（pre_loading_data）\n" + pre_loaded.strip())
    if current_md.strip():
        parts.append("【いま】（補足・参考）\n" + current_md.strip())
    return "\n\n---\n\n".join(parts) if parts else ""


def main():
    s = _style()
    # 起動中はキラキラアニメーションを表示し、モデル読み込みログは出さない
    stop_startup = threading.Event()
    anim_startup = threading.Thread(
        target=_sparkle_animation,
        args=(stop_startup, "  ", "Starting...", s.yellow),
        daemon=True,
    )
    anim_startup.start()
    try:
        with _suppress_stderr():
            from pipe_loader import get_pipe
            pipe = get_pipe()
    finally:
        stop_startup.set()
        anim_startup.join(timeout=0.5)
        print(f"\r  {' ' * 24}\r", end="", flush=True)

    pre_loaded = load_pre_loading_data()
    memory_md = load_memory()
    current_md = fetch_current_context_md()
    _print_banner()
    _print_current_context(current_md)

    recent_messages: list[dict] = []
    gemma_label = f"  {s.gemma}Gemma{s.reset} "
    you_prompt = f"  {s.you}You{s.reset} ▸ "

    try:
        while True:
            try:
                line = _input_line(you_prompt)
            except (EOFError, KeyboardInterrupt):
                print(f"\n  {s.dim}Bye!{s.reset}\n")
                break
            if not line or line.lower() in ("quit", "exit", "q"):
                print(f"  {s.dim}Bye!{s.reset}\n")
                break

            recent_messages.append({"role": "user", "content": line})
            anim_prefix = f"  {s.gemma}Gemma{s.reset} "
            stop_flag = threading.Event()
            anim = threading.Thread(target=_sparkle_animation, args=(stop_flag, anim_prefix), daemon=True)
            anim.start()
            try:
                context = _build_full_context(pre_loaded, memory_md, current_md)
                reply = chat(pipe, context if context.strip() else None, recent_messages)
                stop_flag.set()
                anim.join(timeout=0.5)
                text = reply or "(応答が空でした)"
                # 複数行はインデントを揃える
                lines = text.split("\n")
                print(f"\r{anim_prefix}{' ' * 24}\r{gemma_label}{lines[0]}")
                for L in lines[1:]:
                    print(f"  {s.dim}│{s.reset} {L}")
                recent_messages.append({"role": "assistant", "content": reply})
            except Exception as e:
                stop_flag.set()
                anim.join(timeout=0.5)
                print(f"\r{anim_prefix}{' ' * 24}\r{gemma_label}{s.dim}Error: {e}{s.reset}")
                recent_messages.pop()
                continue

            if len(recent_messages) >= CONSOLIDATE_AFTER:
                stop_summary = threading.Event()
                anim_summary = threading.Thread(
                    target=_sparkle_animation,
                    args=(stop_summary, "  ", "Organizing memory...", s.yellow),
                    daemon=True,
                )
                anim_summary.start()
                try:
                    memory_md = summarize_memory(pipe, memory_md, recent_messages)
                    recent_messages = recent_messages[-2:]
                    import session_memory
                    session_memory.save_consolidation(memory_md)
                    stop_summary.set()
                    anim_summary.join(timeout=0.5)
                    print(f"\r  {' ' * 24}\r  {s.dim}◇ Memory updated{s.reset}", flush=True)
                except Exception as e:
                    stop_summary.set()
                    anim_summary.join(timeout=0.5)
                    print(f"\r  {' ' * 24}\r  {s.dim}Summary error: {e}{s.reset}", flush=True)
            print()
    finally:
        # 5往復未満で終了した場合も、会話があれば要約を1回保存してから finalize する
        import session_memory
        made_dir = MEMORY_DIR / "made_in_currentchat"
        has_parts = made_dir.is_dir() and list(made_dir.glob("*.md"))
        if len(recent_messages) >= 2 and not has_parts:
            try:
                _md = summarize_memory(pipe, memory_md, recent_messages)
                session_memory.save_consolidation(_md)
            except Exception:
                pass
        # 4Bのまま finalize（セッションまとめ・memory.md 統合）してから解放
        stop_finalize = threading.Event()
        anim_finalize = threading.Thread(
            target=_sparkle_animation,
            args=(stop_finalize, "  ", "Organizing memory...", s.yellow),
            daemon=True,
        )
        anim_finalize.start()
        try:
            session_memory.finalize_session(pipe=pipe)
        finally:
            stop_finalize.set()
            anim_finalize.join(timeout=0.5)
            print(f"\r  {' ' * 24}\r", end="", flush=True)
        pipe = None
        from pipe_loader import release_chat_pipe
        release_chat_pipe()
        import gc
        gc.collect()
        try:
            import torch
            if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
                torch.mps.empty_cache()
        except Exception:
            pass

    sys.exit(0)


if __name__ == "__main__":
    main()
