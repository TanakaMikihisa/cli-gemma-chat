"""
チャット中の要約を made_in_currentchat/ に保存し、終了時に memory/ に保存する。

・session_*.md … セッションごとの「その回のまとめ」。タイトル・概要・3セクションは各1回ずつ生成。
・memory.md … 「話したこと(超要約)」「関係性」「ユーザーの人物像」の3セクションで構成。
  既存の memory.md と今回のセッションのまとめを統合・追加調整して更新する。
"""
import contextlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from transformers import GenerationConfig

from pipe_loader import run_chat

BASE_DIR = Path(__file__).resolve().parent
MEMORY_DIR = BASE_DIR / "memory"
MADE_IN_CURRENTCHAT_DIR = MEMORY_DIR / "made_in_currentchat"
MEMORY_FILE = MEMORY_DIR / "memory.md"

# チャット・記憶とも 4B のみ運用
FINALIZE_MAX_NEW_TOKENS = 18000   # 8000 の 3 倍（セクション見切れ防止）
FINALIZE_MAX_LENGTH = 98304       # 16384 の 3 倍
MERGE_MAX_NEW_TOKENS = 72000     # 16384 の 3 倍
MERGE_MAX_LENGTH = 393216        # 65536 の 3 倍

# memory.md の固定3セクション（見出しはこの表記に揃える）
MEMORY_SECTIONS = (
    "話したこと(超要約)",
    "関係性",
    "ユーザーの人物像",
)

# 各セクションの「形成に重要であるもの」の説明（生成時の優先指示用）
MEMORY_SECTION_PURPOSE = {
    "話したこと(超要約)": "テーマ・出来事・決まったこと・時系列がわかる情報。重複は1つにまとめ、このセクションの形成に重要であるものを優先的に採用する。",
    "関係性": "ユーザーとアシスタントの関係性・役割・トーン・距離感。関係性の形成に重要であるものを優先的に採用する。",
    "ユーザーの人物像": "興味・仕事・性格・よく出る話題・言動の傾向。ユーザー像の形成に重要であるものを優先的に採用する。",
}


def _session_json_to_md(data: dict) -> str:
    """スキーマに沿った JSON を session_*.md 用の Markdown に変換する。タイトル・概要・3セクション形式。"""
    title = data.get("title", "").strip() or "セッション"
    date = data.get("date", "").strip() or datetime.now().strftime("%Y-%m-%d")
    summary = data.get("summary", "").strip()
    lines = [f"## {title} ({date})", ""]
    if summary:
        lines.append(f"**概要:** {summary}")
        lines.append("")
    for section_title in MEMORY_SECTIONS:
        body = data.get(section_title, "")
        if isinstance(body, list):
            body = "\n".join(str(x).strip() for x in body if str(x).strip())
        else:
            body = (body or "").strip()
        lines.append(f"## {section_title}")
        lines.append("")
        lines.append(body or "（未記入）")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _to_content(text: str):
    return [{"type": "text", "text": text}]


@contextlib.contextmanager
def _suppress_stderr():
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


def _ensure_memory_sections(md: str) -> str:
    """
    モデル出力を検査し、3セクションを抽出。欠けていれば見出しを補い、順序を統一する。
    見出しが一つもない場合は全文を「話したこと(超要約)」に格納する。
    """
    sections_found = {t: "" for t in MEMORY_SECTIONS}
    stripped = md.strip()
    blocks = re.split(r"\n(?=#{2,3}\s)", stripped) if stripped else []
    for block in blocks:
        if not block.strip():
            continue
        first_line, _, body = block.partition("\n")
        title_candidate = re.sub(r"^#{2,3}\s*", "", first_line).strip()
        for canonical in MEMORY_SECTIONS:
            if title_candidate.strip() == canonical:
                sections_found[canonical] = body.strip()
                break
    # どのセクションにも入らなかった場合は「話したこと」に全文を
    if stripped and not any(sections_found.values()):
        sections_found[MEMORY_SECTIONS[0]] = stripped
    parts = []
    for title in MEMORY_SECTIONS:
        body = (sections_found.get(title) or "").strip()
        parts.append(f"## {title}\n\n{body or '（未記入）'}")
    return "\n\n".join(parts).strip() + "\n"


def _generate_memory_section(
    pipe,
    existing_memory_full: str,
    combined_sessions_md: str,
    section_title: str,
    *,
    max_new_tokens: int = MERGE_MAX_NEW_TOKENS,
    max_length: int = MERGE_MAX_LENGTH,
) -> str:
    """
    1セクション分だけ生成する。他セクションの内容も踏まえ、このセクションの形成に重要であるものを優先する。
    戻り値は見出しを含まない本文のみ。
    """
    purpose = MEMORY_SECTION_PURPOSE.get(section_title, "このセクションにふさわしい内容を統合する。")
    other_sections = [s for s in MEMORY_SECTIONS if s != section_title]
    system = (
        "あなたは「memory.md」の**1つのセクションだけ**を書く役割です。\n\n"
        f"**今回書くセクション:** 「{section_title}」\n\n"
        "**指示:**\n"
        "・【今までの memory.md】全体と【今回まとめたセッション群】の両方を見て、**このセクションの内容だけ**を統合・追加調整して出力してください。\n"
        f"・他のセクション（{', '.join(other_sections)}）の内容も踏まえ、{purpose}\n"
        "・**要約を心がけ、重点を意識する:** 細部や重複を省き、このセクションで重要な点だけを簡潔にまとめる。長く書かず、要点に絞る。\n"
        "・見出し（##）は書かず、**このセクションの本文だけ**を出力する。前置きや「以上」も不要。"
    )
    user = (
        "【今までの memory.md（全セクション）】\n\n" + (existing_memory_full.strip() or "(なし)") + "\n\n"
        "【今回まとめたセッション群】\n\n" + combined_sessions_md.strip()
    )
    msgs = [
        {"role": "system", "content": _to_content(system)},
        {"role": "user", "content": _to_content(user)},
    ]
    gen_cfg = GenerationConfig(max_new_tokens=max_new_tokens, max_length=max_length, do_sample=False)
    with _suppress_stderr():
        body = run_chat(pipe, msgs, gen_cfg).strip()
    # 見出し行が含まれていたら除去
    for st in MEMORY_SECTIONS:
        if body.startswith(f"## {st}"):
            body = body[len(f"## {st}"):].lstrip("\n")
            break
    return body.strip() or "（未記入）"


def _merge_memory(
    pipe,
    existing_md: str,
    new_session_md: str,
    *,
    max_new_tokens: int = MERGE_MAX_NEW_TOKENS,
    max_length: int = MERGE_MAX_LENGTH,
) -> str:
    """
    既存の memory.md と今回のセッション要約を統合する。
    各セクションごとに1回ずつ生成し（計3回）、3セクション形式で返す。
    """
    existing = existing_md.strip() or "(なし)"
    combined = new_session_md.strip()
    if not combined:
        return _ensure_memory_sections(existing) if existing != "(なし)" else ""
    sections_body = {}
    for section_title in MEMORY_SECTIONS:
        body = _generate_memory_section(
            pipe, existing, combined, section_title,
            max_new_tokens=max_new_tokens, max_length=max_length,
        )
        sections_body[section_title] = body
    parts = [f"## {title}\n\n{sections_body[title]}" for title in MEMORY_SECTIONS]
    return "\n\n".join(parts).strip() + "\n"


def save_consolidation(md: str) -> None:
    """現在チャットで生成した要約を memory/made_in_currentchat/ に 1 ファイルで保存する。"""
    MADE_IN_CURRENTCHAT_DIR.mkdir(parents=True, exist_ok=True)
    existing = sorted(MADE_IN_CURRENTCHAT_DIR.glob("part_*.md"))
    next_num = len(existing) + 1
    path = MADE_IN_CURRENTCHAT_DIR / f"part_{next_num:03d}.md"
    path.write_text(md.strip() + "\n", encoding="utf-8")


def _load_memory_md() -> str:
    """memory.md の内容を返す。無ければ空文字。"""
    if not MEMORY_FILE.is_file():
        return ""
    try:
        return MEMORY_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _generate_session_title_summary(
    pipe,
    memory_md: str,
    combined: str,
    *,
    max_new_tokens: int = 800,
    max_length: int = 2048,
) -> dict:
    """タイトルと概要だけを生成する。memory.md を参照しその内容を踏まえる。戻り値は {"title": str, "summary": str}。"""
    system = (
        "あなたは「今回のセッションのまとめ」の**タイトルと概要だけ**を書く役割です。\n\n"
        "【memory.md】の内容を参照し、その文脈を踏まえて、今回のチャットにふさわしい短いタイトルと1〜2文の概要を考えてください。\n"
        "**必ず次の JSON 形式だけ**で出力すること。説明は不要。\n\n"
        '{"title": "セッションのタイトル（短い見出し）", "summary": "1〜2文で今回のチャットの概要"}'
    )
    user = (
        "【memory.md（参照用）】\n\n" + (memory_md.strip() or "(なし)") + "\n\n"
        "【今回のチャットで保存した記憶ノート】\n\n" + combined.strip()
    )
    msgs = [
        {"role": "system", "content": _to_content(system)},
        {"role": "user", "content": _to_content(user)},
    ]
    gen_cfg = GenerationConfig(max_new_tokens=max_new_tokens, max_length=max_length, do_sample=False)
    with _suppress_stderr():
        raw = run_chat(pipe, msgs, gen_cfg).strip()
    data = _extract_json(raw)
    if data and isinstance(data, dict):
        return {
            "title": (data.get("title") or "").strip() or "セッション",
            "summary": (data.get("summary") or "").strip() or "",
        }
    return {"title": "セッション", "summary": ""}


def _generate_session_section(
    pipe,
    memory_md: str,
    combined: str,
    section_title: str,
    *,
    max_new_tokens: int = 1024,
    max_length: int = 2048,
) -> str:
    """今回のセッションの、1セクション分の本文だけを生成する。memory.md を参照しその内容を踏まえる。"""
    purpose = MEMORY_SECTION_PURPOSE.get(section_title, "このセクションにふさわしい内容をまとめる。")
    system = (
        "あなたは「今回のセッションのまとめ」の**1つのセクションだけ**を書く役割です。\n\n"
        f"**今回書くセクション:** 「{section_title}」\n\n"
        "【memory.md】の内容を参照し、その文脈を踏まえて、**今回のセッションで得られた情報だけ**をこのセクション用にまとめてください。\n"
        f"{purpose}\n"
        "・**要約を心がけ、重点を意識する:** 重要な点だけを簡潔にまとめ、細部や重複は省く。\n"
        "見出し（##）は書かず、**このセクションの本文だけ**を出力する。前置き不要。"
    )
    user = (
        "【memory.md（参照用）】\n\n" + (memory_md.strip() or "(なし)") + "\n\n"
        "【今回のチャットで保存した記憶ノート】\n\n" + combined.strip()
    )
    msgs = [
        {"role": "system", "content": _to_content(system)},
        {"role": "user", "content": _to_content(user)},
    ]
    gen_cfg = GenerationConfig(max_new_tokens=max_new_tokens, max_length=max_length, do_sample=False)
    with _suppress_stderr():
        body = run_chat(pipe, msgs, gen_cfg).strip()
    for st in MEMORY_SECTIONS:
        if body.startswith(f"## {st}"):
            body = body[len(f"## {st}"):].lstrip("\n")
            break
    return body.strip() or "（未記入）"


def _generate_structured_with_outlines(pipe, combined: str, schema: dict, json_schema_str: str) -> dict | None:
    """Outlines で JSON 構造化出力を強制し、確実にスキーマ通りの dict を返す。失敗時は None。"""
    try:
        from outlines import models, generate
    except ImportError:
        return None
    model_name = getattr(
        getattr(pipe.model, "config", None),
        "name_or_path",
        getattr(getattr(pipe.model, "config", None), "_name_or_path", "Qwen/Qwen2.5-7B-Instruct"),
    )
    device = getattr(pipe, "device", None)
    if device is not None and not isinstance(device, str):
        device = "cuda" if str(device).startswith("cuda") else ("mps" if "mps" in str(device) else "cpu")
    elif device is None:
        device = "cpu"
    system_text = (
        "以下は今回のチャットで保存した記憶ノート（複数）です。"
        "これらを「このセッションのまとめ」として、タイトル・概要・話したこと(超要約)・関係性・ユーザーの人物像の形でまとめ、指定のJSON形式だけで出力してください。"
    )
    msgs = [
        {"role": "system", "content": system_text},
        {"role": "user", "content": combined},
    ]
    try:
        prompt = pipe.tokenizer.apply_chat_template(
            msgs,
            tokenize=False,
            add_generation_prompt=True,
        )
    except Exception:
        prompt = f"{system_text}\n\n{combined}\n\n"
    with _suppress_stderr():
        try:
            model = models.transformers(model_name, device=device)
            generator = generate.json(model, json_schema_str)
            result = generator(prompt)
        except Exception:
            return None
    # Outlines は JSON Schema 時に Pydantic インスタンスを返すことがある
    if hasattr(result, "model_dump"):
        return result.model_dump()
    if hasattr(result, "dict"):
        return result.dict()
    if isinstance(result, dict):
        return result
    return None


def _extract_json(text: str) -> dict | None:
    """文字列から JSON を1つ取り出す。```json ... ``` があればその中身、なければ全体をパース。"""
    text = (text or "").strip()
    if not text:
        return None
    # コードブロックを除去
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        text = m.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


# memory.md を再調整する閾値（この本数以上、memory.md 以外の .md があればセッション終わりに実行）。1＝毎回書き換え。
MEMORY_MERGE_AFTER_SESSIONS = 1


def _consolidate_memory_if_needed(pipe) -> None:
    """memory/ 内で memory.md 以外の .md が MEMORY_MERGE_AFTER_SESSIONS 本以上あれば、まとめて memory.md を再調整し、使った session 用 .md は削除する。"""
    if not MEMORY_DIR.is_dir():
        return
    others = sorted(p for p in MEMORY_DIR.glob("*.md") if p.name != "memory.md")
    if len(others) < MEMORY_MERGE_AFTER_SESSIONS:
        return
    combined = "\n\n---\n\n".join(
        p.read_text(encoding="utf-8").strip() for p in others
    )
    if not combined.strip():
        return
    existing_memory = ""
    if MEMORY_FILE.is_file():
        try:
            existing_memory = MEMORY_FILE.read_text(encoding="utf-8").strip()
        except OSError:
            pass
    merge_kw = {"max_new_tokens": MERGE_MAX_NEW_TOKENS, "max_length": MERGE_MAX_LENGTH}
    memory_md_content = _merge_memory(
        pipe, existing_memory or "(なし)", combined, **merge_kw
    )
    MEMORY_FILE.write_text(memory_md_content.strip() + "\n", encoding="utf-8")
    for p in others:
        try:
            p.unlink()
        except OSError:
            pass


def finalize_session(pipe=None) -> None:
    """
    made_in_currentchat/ 内の全 MD を読み、4B モデルで「チャット全体のまとめ」を生成する。
    memory.md を参照し、タイトル・概要と3セクションを**各1回ずつ**生成して session_*.md に保存する。
    セッション終了のたびに、既存の session_*.md と合わせて memory.md を再調整する（MEMORY_MERGE_AFTER_SESSIONS=1 で毎回実行）。
    """
    if not MADE_IN_CURRENTCHAT_DIR.is_dir():
        return
    parts = sorted(MADE_IN_CURRENTCHAT_DIR.glob("*.md"))
    if not parts:
        return

    combined = "\n\n---\n\n".join(
        p.read_text(encoding="utf-8").strip() for p in parts
    )
    if not combined.strip():
        return

    if pipe is None:
        return

    pipe_for_memory = pipe
    memory_md = _load_memory_md()

    # 1) タイトル・概要を1回生成（memory.md を参照）
    title_summary = _generate_session_title_summary(pipe_for_memory, memory_md, combined)

    # 2) 各セクションを1回ずつ生成（memory.md を参照、計3回）
    sections_body = {}
    for section_title in MEMORY_SECTIONS:
        sections_body[section_title] = _generate_session_section(
            pipe_for_memory, memory_md, combined, section_title
        )

    normalized = {
        "title": title_summary["title"],
        "summary": title_summary["summary"],
        "date": datetime.now().strftime("%Y-%m-%d"),
        **sections_body,
    }
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_md_path = MEMORY_DIR / f"session_{stamp}.md"
    md_content = _session_json_to_md(normalized)
    session_md_path.write_text(md_content, encoding="utf-8")

    # セッション終了のたびに memory.md を再調整（session_*.md を統合してから削除）
    _consolidate_memory_if_needed(pipe_for_memory)

    for p in parts:
        try:
            p.unlink()
        except OSError:
            pass
