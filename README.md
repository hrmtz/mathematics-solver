# Mathematics Solver (Math OCR + Quarto Handout)

スマホで撮影した大学入試レベルの数学問題画像 (JPG/PNG) をアップロードし、
- OpenAI Vision による OCR → Quarto 互換の qmd 生成
- ブラウザ上で qmd をプレビュー・修正
- OpenAI による模範解答の自動生成
- 問題＋解答を HTML handout として出力（ブラウザ印刷前提）

を行う Flask ベースの小さな Web アプリです。

- バージョン: **0.2.0**（検索画面・ランダム演習・handout HTML 対応）
---

## 機能概要
1. **画像アップロード (Flask)**  
	- エンドポイント: `GET /upload` でアップロードフォーム表示、`POST /upload` で処理開始。
	- ルート `/` は問題検索画面 `/search` へリダイレクト。
	- スマホ/PC から `jpg/jpeg/png` をアップロード可能。
2. **OCR → 問題 qmd 生成（画像ベース）**  
	- `ocr_to_qmd.py` で OpenAI Vision API を呼び出し、アップロード画像から問題文を OCR。  
	- 出力形式: Quarto 互換 Markdown (`.qmd`)。  
	- 数式ルール:
		 - インライン数式: `$...$`
		 - ディスプレイ数式: `$$ ... $$`（`\[ ... \]` や `\begin{align}` は使わない）
	 - 自動付与される仮 YAML ヘッダ例（大学名・年度・分野は後でアプリ側で補完）:
	```yaml
	---
	title: "<problem_id>"
	problem_id: "<problem_id>"
	format:
	  html:
	    math: mathjax
	---
	```

	 - 生成された qmd は `problems/<problem_id>.qmd` に保存。
3. **HTML プレビュー & 編集**  
	- テンプレート: `templates/preview.html`。  
	- qmd テキストを textarea で編集可能。  
	- YAML ヘッダを除いた本文を MathJax で数式表示する簡易 HTML プレビュー付き。  
	- 修正後は `POST /meta/<problem_id>` で qmd 全体（YAML 含む）を保存。

4. **解答生成 (OpenAI)**  
	 - `solver.py` の `generate_solution_qmd()` が問題 qmd を入力として模範解答 qmd を生成。  
	 - 解答方針（システムプロンプト）：
		 - 高校数学〜大学入試レベルの模範解答。
	- 誘導があれば従う。
	- 途中式を丁寧に書く。
	- 証明は日本語で論理的に記述。
		 - 出力は qmd 形式・数式は `$...` / `$$ ... $$`。
	 - 生成された解答 qmd は `solutions/<problem_id>_solution.qmd` に保存。  
	- テンプレート: `templates/solution_preview.html` で、問題・解答の両方をテキスト＋MathJax プレビュー表示。
	- モデルが `## 解答` 見出しを付けても、保存時・プレビュー時に自動で除去。

5. **handout HTML 生成 (Quarto)**  
	 - `solver.py` の `build_handout_qmd()` で、問題 qmd と解答 qmd を結合した handout 用 qmd を生成。  
	 - handout 用 YAML ヘッダ（抜粋）:

		 ```yaml
		 ---
		 lang: ja
		 format:
		   html:
		     theme: default
		     toc: false
		     number-sections: false
		     css: ../static/handout-print.css
		 ---
		 ```

	 - `app.py` の `POST /handout/<problem_id>` から `quarto render --to html` を呼び出し、  
		 `output/<problem_id>_handout.qmd` → `output/<problem_id>_handout.html` を生成。  
	- 生成された HTML をブラウザで開き、そのまま印刷 / PDF 化して配布資料に利用。

6. **メタデータ管理 (YAML ヘッダ + 検索 UI)**  
	問題 qmd の YAML ヘッダに以下のようなメタデータを記述しておき、
	トップページ `/search` の検索 UI から大学・年度・分野などでフィルタして利用できます。
	```yaml
	---
	title: "東京大学 2024年 2024_4"
	problem_id: "01_tokyo-2024-2024_4"
	university: "東京大学"
	exam_year: "2024"
	source_tex: "archive/01_tokyo/2024/2024_4.tex"
	pdf_source: "archive/01_tokyo/2024/2024_4.pdf"
	page_image: "archive/01_tokyo/2024/2024_4.jpg"
	fields:
	  - 微分法
	  - 平面図形
	format:
	  html:
	    math: mathjax
	---
	```

7. **問題検索・ランダム演習 (`/search`)**  
	- トップページ `/` で問題検索画面 `/search` を表示。
	- 大学・年度（from/to）・分野でフィルタ可能（年度 from はデフォルトで 2015 年頃から）。
	- 問題本文の冒頭テキスト（LaTeX 除去済み）をスニペットとして一覧表示。
	- 「この条件からランダムに10問」ボタンで、絞り込み条件に合う問題からランダムに 10 問を抽出して演習用リストを表示。
	- 一覧には解答の有無も表示され、その場で「解答を見る」画面へ遷移可能。

8. **TeX アーカイブ → qmd 一括生成 (`archive_import.py`)**  
	- 旧来の TeX 問題アーカイブ（`archive/<university>/<year>/*.tex`）から `problems/` 配下の qmd を一括生成するユーティリティ。  
	- TeX の `\begin{document}`〜`\end{document}` だけを抜き出して不要なレイアウト記述やコメントを削除。  
	- `\includegraphics{...}` を実際の画像ファイル（`fig_*.jpg` 等）にマッピングし、Markdown 画像 `![]()` に変換。  
	- YAML ヘッダに `university`, `exam_year`, `source_tex`, `pdf_source`, `page_image` などのメタデータを付与。  
	- 既に同じ `problem_id` の qmd が存在する場合はスキップする安全設計。  
	- コマンド例:
		- 全大学・全年度を対象（実際にはかなり時間がかかるので注意）:
			```bash
			python archive_import.py
			```
		- 東京大学 1961 年分だけ qmd を生成（書き込みあり）:
			```bash
			python archive_import.py --university 01_tokyo --year 1961
			```
		- 同じ範囲で dry-run（生成内容だけログに出してファイルは書かない）:
			```bash
			python archive_import.py --university 01_tokyo --year 1961 --dry-run
			```

9. **分野タグ自動付与 (`assign_fields.py`)**  
	- `problems/*.qmd` を走査し、OpenAI ベースの分類器で「微分法」「積分法」「ベクトル」「確率」などの分野タグを推定して YAML ヘッダに `fields:` として追記。  
	- すでに `fields:` を持つ問題や YAML ヘッダの無いファイルは自動的にスキップ。  
	- 付与する分野名の候補は `taxonomy.py` の `FIELDS` に定義された一覧を利用。  
	- コマンド例:
		- 全問題に対して分野タグを付与（書き込みあり）:
			```bash
			python assign_fields.py
			```
		- 単一問題だけ対象にし、結果だけ見たい場合:
			```bash
			python assign_fields.py --problem-id 01_tokyo-1961-1961_1 --dry-run
			```

---

## ディレクトリ構成

```text
project-root/
	app.py                # Flask アプリ本体
	ocr_to_qmd.py         # OpenAI Vision による OCR → qmd 生成
	solver.py             # 解答生成 & handout qmd 生成
	templates/
		upload.html         # 画像アップロードフォーム
		preview.html        # 問題 qmd 編集 & HTML プレビュー
		solution_preview.html  # 問題＋解答のテキスト & プレビュー
	uploads/              # アップロードされた画像
	problems/             # 問題 qmd
	solutions/            # 解答 qmd
	output/               # handout qmd / PDF
	static/               # （将来用の静的ファイル置き場）
	requirements.txt
	README.md
```

---

## 使用している OpenAI モデル

- **OCR (画像 → qmd)**: デフォルト `gpt-4.1-mini`  
	- 環境変数 `OPENAI_VISION_MODEL` で上書き可能（例: `gpt-4o-mini`）。
- **解答生成 (問題 qmd → 解答 qmd)**: デフォルト `gpt-5.1`  
	- 環境変数 `OPENAI_SOLUTION_MODEL` で上書き可能（例: `o4`）。

---

## 必要なパッケージ / ツール一覧

Python パッケージ（`requirements.txt`）:

- `flask` : Web アプリ本体
- `openai` : OpenAI API クライアント
- `werkzeug` : ファイルアップロードなどで利用（Flask 依存）

OS / ツール系パッケージ（Ubuntu 想定）:

- Quarto 本体
	- 例:
		```bash
		wget https://quarto.org/download/latest/quarto-linux-amd64.deb -O /tmp/quarto.deb
		sudo dpkg -i /tmp/quarto.deb || sudo apt-get -f install -y
		```
- LaTeX 環境（Quarto で PDF 出力する場合）
	- 例:
		```bash
		sudo apt-get update
		sudo apt-get install -y texlive-latex-extra
		```

将来の軽量化（HTML までで完結させるなど）により、LaTeX 依存を削減する可能性があります。

---

## セットアップ

```bash
cd /workspaces/mathematics-solver
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

環境変数:

- `OPENAI_API_KEY`: **必須**。OpenAI API キー。
- `OPENAI_VISION_MODEL`: (任意) Vision 用モデル名。デフォルト `gpt-4.1-mini`。
- `OPENAI_SOLUTION_MODEL`: (任意) 解答生成用モデル名。デフォルト `gpt-5.1`。
- `FLASK_SECRET_KEY`: (任意) Flask のセッション用シークレットキー。指定がなければ開発用デフォルト。

Quarto / LaTeX 環境も別途インストールしておく必要があります（PDF 出力に必須）。

```bash
quarto --version
```

---

## 実行方法

```bash
cd /workspaces/mathematics-solver
source .venv/bin/activate

export OPENAI_API_KEY="sk-..."   # 自分のキーに置き換え

flask --app app run --host 0.0.0.0 --port 5000
```

ブラウザで `http://localhost:5000` にアクセスして利用します。

---

## 今後の拡張アイデア

- 問題メタデータ（大学名・年度・分野など）でフィルタ・検索できる画面 (`/search` など)。
- 問題・解答・PDF の一覧画面と、個別ダウンロードリンク。
- Quarto テンプレートのカスタマイズ（出力フォーマット切り替え、単列レイアウト対応など）。
- ログイン機能やユーザーごとの問題管理。
# mathematics-solver