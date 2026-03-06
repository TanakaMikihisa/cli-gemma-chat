# 仮想環境のパス
VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: run install venv convert-mlx-4bit

# デフォルト: 仮想環境を用意して requirements を入れ、チャットを起動
run: venv install
	$(PYTHON) chat_cli.py

# HF モデルをダウンロードして MLX 4bit に変換（Mac 用・要 mlx-lm）。既定: Qwen/Qwen3.5-35B-A3B → models/qwen3.5-35b-a3b-4bit
convert-mlx-4bit: venv install
	$(PYTHON) scripts/convert_hf_to_mlx_4bit.py

# requirements を仮想環境にインストール（ログ非表示）
install: venv
	PIP_DISABLE_PIP_VERSION_CHECK=1 $(PIP) install -q -r requirements.txt

# 仮想環境がなければ作成
venv:
	@if [ ! -d $(VENV) ]; then python3 -m venv $(VENV); fi
