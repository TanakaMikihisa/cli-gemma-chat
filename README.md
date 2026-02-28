# GEM CHAT

![GEM CHAT 起動画面](introduction.png)

軽量ローカルLLMであるGoogle Gemmaを使ったCLIチャットです。
会話は記憶としてMarkdownで蓄積され、次回起動時にコンテキストとして参照されます。

## 必要な環境

- Python 3.10 以上（3.14 では outlines はスキップされます）
- [Hugging Face](https://huggingface.co) のアカウントとログイン
- Gemma モデルの利用許諾（[モデルページ](https://huggingface.co/google/gemma-3-4b-it)で Accept が必要な場合があります）

初回起動時に未ログインの場合は、ログイン処理が案内されます。

## セットアップ・起動

```bash
make
```

## 主な機能

- **記憶（memory.md）**  
  会話の要約を「話したこと(超要約)」「関係性」「ユーザーの人物像」の3セクションで蓄積。起動時に最優先でコンテキストに含まれます。

- **pre_loading_data/**  
  フォルダ内の全`.md`(サブフォルダ含む)を起動時に読み込み、`memory.md`の次の優先度で参照されます。

- **いま（日付・場所・天気）**  
  起動時にIPから現在地を取得し、[Open-Meteo](https://open-meteo.com/) で天気を取得し、`pre_loading_data/`の次の優先度で参照されます。

- **セッションまとめ**  
  終了時に`memory/made_in_currentchat/`の内容を1つのmdにまとめ、`memory/session_*.md`として保存します。
  `memory.md`以外の`.md`が5本溜まったタイミングで、それらの内容と`memory.md`を統合します。

## ディレクトリ構成

| パス | 説明 |
|------|------|
| `chat_cli.py` | エントリポイント。会話ループ・コンテキスト組み立て |
| `pipe_loader.py` | Gemma 4B の読み込み・解放。HF 未ログイン時は login を促す |
| `session_memory.py` | セッションまとめ・memory.md の再調整 |
| `pre_loading_data/` | 起動時に読み込む .md（任意） |
| `memory/` | 記憶の棚（memory.md、session_*.md、made_in_currentchat/） |
| `banner.txt` | 起動時バナー（左→右グラデーション）。任意 |

## 操作

- 通常の入力で会話
- `quit` / `exit` / `q` で終了
- 5 往復ごとに会話が要約され、`memory/made_in_currentchat/` に追加されます

## スペックについて

M4 MacBook Air(24GBメモリ)ではレスポンスは最大でも10秒ほどで返ってきます。