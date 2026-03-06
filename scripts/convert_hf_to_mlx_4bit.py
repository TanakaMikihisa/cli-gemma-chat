#!/usr/bin/env python3
"""
HF モデル（キャッシュ）を MLX 用 4bit に量子化する。

既定: Qwen/Qwen3.5-35B-A3B → models/qwen3.5-35b-a3b-4bit
"""
import shutil
import subprocess
import sys
from pathlib import Path

HF_MODEL_ID = "Qwen/Qwen3.5-35B-A3B"
DEFAULT_MLX_PATH = Path(__file__).resolve().parent.parent / "models" / "qwen3.5-35b-a3b-4bit"


def main():
    mlx_path = DEFAULT_MLX_PATH
    if mlx_path.exists():
        shutil.rmtree(mlx_path)
    mlx_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, "-m", "mlx_lm.convert",
        "--hf-path", HF_MODEL_ID,
        "--mlx-path", str(mlx_path),
        "-q",
    ]
    print(f"Quantizing {HF_MODEL_ID} → {mlx_path}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        sys.exit(result.returncode)
    print(f"Done. Saved to: {mlx_path}")


if __name__ == "__main__":
    main()
