# Mathematics Solver

大学入試レベルの数学問題を **画像 → OCR → qmd → HTML プレビュー → 模範解答生成 → handout 作成** まで一気通貫で処理する Flask Web アプリ。

* Version **1.0.0**
* コア技術：OpenAI Vision / GPT / Quarto / MathJax
* 目的：問題管理・演習プリント生成・ handout 作成を Web 上で完結させる

---

# 1. 何ができるアプリか（機能の全体像）

このアプリの機能は以下の 4 つに整理できる。

## 1.1 画像 → qmd（OCR）

* JPG/PNG をアップロードすると OpenAI Vision で OCR。
* Quarto 互換 `.qmd` を生成し `problems/` に保存。
* 数式は `$...$` / `$$...$$` に正規化。

## 1.2 qmd の編集 & プレビュー

* ブラウザで qmd 全体を編集。右側で MathJax プレビュー。
* YAML ヘッダは保持しつつ本文のみレンダリング。

## 1.3 模範解答 qmd の自動生成

* GPT による日本語の解答生成。
* 解答 qmd は `solutions/` に保存。
* `## 解答` など余計な見出しは自動除去。

## 1.4 handout / テストプリント生成（HTML）

* 検索画面から複数問題を選んで **テストプリント HTML** を生成。
* 各問題単体でも **問題＋解答の handout HTML** を生成。
* すべてブラウザ印刷前提（1カラム・MathJax）。

---

# 2. 画面一覧（ユーザーが実際に触る場所）

| 画面       | URL                      | 説明                          |
| -------- | ------------------------ | --------------------------- |
| 問題検索     | `/search`                | 大学・年度・分野でフィルタ。ランダム演習。テスト作成。 |
| 画像アップロード | `/upload`                | 画像 → qmd 生成。                |
| 問題編集     | `/problem/<id>`          | qmd 編集＋プレビュー。               |
| 解答プレビュー  | `/problem/<id>/solution` | 問題＋解答の並列プレビュー。              |
| handout  | `/handout/<id>`          | 問題＋解答を HTML で整形。印刷向け。       |

---

# 3. 技術仕様（必要最小限だけ）

## 3.1 qmd レンダリング（共通ロジック）

クライアント側 JS `static/qmd-render.js` がすべての表示処理を統一：

* YAML ヘッダの除去
* よく使う TeX 記法のサニタイズ
* Markdown → HTML の簡易変換
* MathJax による数式表示
* 解答先頭の `## 解答` を除去
* 元 PDF・スキャンへのリンク行は**全画面非表示**

## 3.2 OCR / 解答生成モデル

* Vision: `gpt-4.1-mini`（環境変数で変更可）
* 解答生成: `gpt-5.1`（同上）

---

# 4. セットアップ

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

必要な環境変数：

```
OPENAI_API_KEY=sk-xxxx
OPENAI_VISION_MODEL=gpt-4.1-mini
OPENAI_SOLUTION_MODEL=gpt-5.1
FLASK_SECRET_KEY=任意
```

（PDF 出力を使いたい場合のみ Quarto/LaTeX をインストール）

---

# 5. 実行

```bash
flask --app app run --host 0.0.0.0 --port 5000
```

---

# 6. 補助ツール（任意で使う開発者向け機能）

| スクリプト               | 内容                                                         |
| ------------------- | ---------------------------------------------------------- |
| `archive_import.py` | TeX アーカイブ → qmd 一括生成。画像の `includegraphics` を Markdown に変換。 |
| `assign_fields.py`  | 問題文から「微分法」「確率」などの分野タグを自動推定して YAML 追記。                      |

---

# 7. 今後の改善余地（簡潔に要点だけ）

* 検索 UI の強化（ソート・条件組み合わせ）。
* 問題/解答の一括管理画面。
* handout 用 Quarto テンプレートの最適化。
* ログイン・履歴・お気に入り問題集などのユーザー機能。

