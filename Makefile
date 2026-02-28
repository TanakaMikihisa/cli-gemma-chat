# 仮想環境のパス
VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: run install venv

# デフォルト: 仮想環境を用意して requirements を入れ、チャットを起動
run: venv install
	$(PYTHON) chat_cli.py

# requirements を仮想環境にインストール（ログ非表示）
install: venv
	PIP_DISABLE_PIP_VERSION_CHECK=1 $(PIP) install -q -r requirements.txt

# 仮想環境がなければ作成
venv:
	@if [ ! -d $(VENV) ]; then python3 -m venv $(VENV); fi
