# 仮想環境のパス
VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: run install install-ui venv ui-build convert-mlx-4bit

# デフォルト: リッチ UI で起動（Node.js + Ink）
run: venv install install-ui ui-build
	cd ui && node dist/index.js

# HF モデルをダウンロードして MLX 4bit に変換
convert-mlx-4bit: venv install
	$(PYTHON) scripts/convert_hf_to_mlx_4bit.py

# requirements を仮想環境にインストール（ログ非表示）
install: venv
	PIP_DISABLE_PIP_VERSION_CHECK=1 $(PIP) install -q -r requirements.txt

# Node.js 依存をインストール
install-ui:
	@if [ ! -d ui/node_modules ]; then cd ui && npm install; fi

# TypeScript UI をビルド
ui-build:
	@if [ ! -d ui/dist ] || [ "$$(find ui/src -newer ui/dist -name '*.ts' -o -name '*.tsx' 2>/dev/null | head -1)" ]; then cd ui && npm run build; fi

# 仮想環境がなければ作成
venv:
	@if [ ! -d $(VENV) ]; then python3 -m venv $(VENV); fi
