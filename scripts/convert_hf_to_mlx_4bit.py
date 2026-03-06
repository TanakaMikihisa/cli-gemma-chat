#!/usr/bin/env python3
"""
既存の HF モデル（キャッシュまたはローカル）を MLX 用 4bit 量子化する。ダウンロードは行わない。

デフォルト: Qwen/Qwen3.5-35B-A3B（HF キャッシュ）を 4bit 量子化して models/qwen3.5-35b-a3b-4bit に保存。

注意: 35B クラスのモデルでは Metal GPU Timeout で落ちることがあります。その場合は
  - 他アプリを閉じて再実行する
  - 事前変換済みの mlx-community/Qwen3.5-35B-A3B-4bit を HF からそのまま利用する
  を検討してください。

使い方:
  python scripts/convert_hf_to_mlx_4bit.py
  python scripts/convert_hf_to_mlx_4bit.py --mlx-path ./my_output
  python scripts/convert_hf_to_mlx_4bit.py --hf-path google/gemma-3-4b-it
  python scripts/convert_hf_to_mlx_4bit.py --with-download   # 未キャッシュなら先にダウンロード
  python scripts/convert_hf_to_mlx_4bit.py --overwrite       # 既存の保存先を削除してから量子化
"""
import argparse
import subprocess
import sys
from pathlib import Path

# デフォルト: 変換元の Hugging Face モデル（キャッシュにあれば利用）
HF_MODEL_ID = "Qwen/Qwen3.5-35B-A3B"
# デフォルトの MLX 保存先
DEFAULT_MLX_PATH = Path(__file__).resolve().parent.parent / "models" / "qwen3.5-35b-a3b-4bit"


def ensure_model_downloaded(hf_path: str) -> None:
    """HF からモデルをダウンロード（未キャッシュの場合）。"""
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("huggingface_hub がありません。pip install huggingface_hub のうえ再実行してください。")
        raise SystemExit(1) from None
    print(f"Downloading model from Hugging Face: {hf_path}")
    snapshot_download(repo_id=hf_path, local_files_only=False)
    print("Download done.")


def convert_to_mlx_4bit(hf_path: str, mlx_path: Path, overwrite: bool = False) -> None:
    """MLX 用 4bit 量子化変換を行う。"""
    if mlx_path.exists():
        if overwrite:
            import shutil
            print(f"Removing existing output: {mlx_path}")
            shutil.rmtree(mlx_path)
        else:
            print(f"Error: output path already exists: {mlx_path}")
            print("Remove it, use --mlx-path, or add --overwrite to replace.")
            sys.exit(1)
    mlx_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "-m",
        "mlx_lm.convert",
        "--hf-path",
        hf_path,
        "--mlx-path",
        str(mlx_path),
        "-q",
    ]
    print("Quantizing to MLX 4-bit...")
    print("Running:", " ".join(cmd))
    result = subprocess.run(cmd)
    if result.returncode != 0:
        sys.exit(result.returncode)
    print(f"Done. MLX 4-bit model saved to: {mlx_path}")


def main():
    parser = argparse.ArgumentParser(
        description="HF モデル（キャッシュ）を MLX 4bit 量子化する。デフォルトでは量子化のみ実行。"
    )
    parser.add_argument(
        "--hf-path",
        type=str,
        default=HF_MODEL_ID,
        help=f"変換元 HF モデル ID またはローカルパス (default: {HF_MODEL_ID})",
    )
    parser.add_argument(
        "--mlx-path",
        type=Path,
        default=DEFAULT_MLX_PATH,
        help=f"MLX 4bit 保存先ディレクトリ (default: {DEFAULT_MLX_PATH})",
    )
    parser.add_argument(
        "--with-download",
        action="store_true",
        help="量子化の前に HF からダウンロードする（未キャッシュ時用）",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="既存の --mlx-path があれば削除してから量子化する",
    )
    args = parser.parse_args()
    hf_path = args.hf_path
    mlx_path = args.mlx_path.resolve()
    if args.with_download:
        ensure_model_downloaded(hf_path)
    convert_to_mlx_4bit(hf_path, mlx_path, overwrite=args.overwrite)


if __name__ == "__main__":
    main()
