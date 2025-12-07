# Mathematics Solver (Math OCR + Quarto Handout)

スマホで撮影した大学入試レベルの数学問題画像 (JPG/PNG) をアップロードし、
- OpenAI Vision による OCR → Quarto 互換の qmd 生成
- ブラウザ上で qmd をプレビュー・修正（MathJax で数式プレビュー）
- OpenAI による模範解答の自動生成
- 問題＋解答から **印刷用 HTML ハンドアウト (問題1段＋解答2段組)** を生成し、ブラウザの印刷機能で A4 印刷 / PDF 保存

を行う Flask ベースの小さな Web アプリです。

- バージョン: **0.2.0**（ハンドアウト HTML / A4 印刷フローまで実装）
---

## 機能概要
1. **画像アップロード (Flask)**  
	- エンドポイント: `GET /` でアップロードフォーム表示、`POST /upload` で処理開始。
	- スマホ/PC から `jpg/jpeg/png` をアップロード可能。
2. **OCR → 問題 qmd 生成**  
	- `ocr_to_qmd.py` で OpenAI Vision API を呼び出し、画像から問題文を OCR。  
	- 出力形式: Quarto 互換 Markdown (`.qmd`)。  
	- 数式ルール:
		 - インライン数式: `$...$`
		 - ディスプレイ数式: `$$ ... $$`（`\[ ... \]` や `\begin{align}` は使わない）
	 - 自動付与される仮 YAML ヘッダ例:
	```yaml
	---
	title: "<problem_id>"
		 problem_id: "<problem_id>"
		 format:
			 html:
				 math: mathjax
		 ---

### Docker での実行

ローカルにPython環境を用意せず、コンテナで実行することもできます。

```bash
cd /workspaces/mathematics-solver

# イメージをビルド
docker build -t mathematics-solver .

# 実行（必要に応じてOPENAI_API_KEYなどを渡す）
docker run --rm -p 5000:5000 \
	-e OPENAI_API_KEY="sk-..." \
	mathematics-solver
```

ブラウザで `http://localhost:5000` にアクセスすると、コンテナ内で動作するアプリに接続できます。

	 - 生成された qmd は `problems/<problem_id>.qmd` に保存。
3. **HTML プレビュー & 編集**  
	- テンプレート: `templates/preview.html`。  
	- qmd テキストを textarea で編集可能。  
	- YAML ヘッダを除いた本文を MathJax で数式表示する簡易 HTML プレビュー付き。  
	- 修正後は `POST /meta/<problem_id>` で qmd 全体（YAML 含む）を保存。

4. **解答生成 (OpenAI)**  
	 - `solver.py` の `generate_solution_qmd()` が問題 qmd を入力として模範解答 qmd を生成。  
	 - 解答方針（システムプロンプト）:
		 - 高校数学〜大学入試レベルの模範解答。
	- 誘導があれば従う。
	- 途中式を丁寧に書く。
	- 証明は日本語で論理的に記述。
		 - 出力は qmd 形式・数式は `$...` / `$$ ... $$`。
		 - 冒頭に `## 解答` 見出しを付ける。
	 - 生成された解答 qmd は `solutions/<problem_id>_solution.qmd` に保存。  
	- テンプレート: `templates/solution_preview.html` で、問題・解答の両方をテキスト＋MathJax プレビュー表示。

5. **ハンドアウト HTML 生成（ブラウザ印刷前提）**  
	 - `solver.py` の `build_handout_qmd()` で、問題 qmd と解答 qmd を結合したハンドアウト qmd を生成。  
	 - ハンドアウト qmd の YAML では `format.html.css: ../static/handout-print.css` を指定し、`static/handout-print.css` の印刷用スタイルを読み込みます。  
	 - 生成される HTML の構造は概ね次のようになります:
		 - `<div class="main-wrap">` … 全体コンテナ（A4 幅に収まるよう制御）
		 - `<section id="problem-section">` … 問題部分（1 カラム）
		 - `<section id="solution-section">` … 解答部分（2 カラム）
	 - `static/handout-print.css` では、A4 サイズ・余白・フォント・段組（問題 1 段、解答 2 段）などを指定しています。  
	 - `app.py` の `POST /handout/<problem_id>` から `quarto render` を呼び出し、  
		 `output/<problem_id>_handout.qmd` → `output/<problem_id>_handout.html` を生成。  
	 - 生成された HTML をブラウザで開き、印刷ダイアログで A4 用紙を選択して印刷 / PDF 保存します。

6. **メタデータ管理 (YAML ヘッダ)**  
	問題 qmd の YAML ヘッダに以下のようなメタデータを記述しておき、
	将来的な検索や分類に利用できるようにします（アプリ内の検索 UI は今後実装予定）。
	```yaml
	---
	title: "osaka-2024-math-q4"
	problem_id: "osaka-2024-math-q4"
	university: "大阪大学"
	exam_year: 2024
	exam_type: "前期"
	subject: "数学"
	field: "積分法"
	section: "第4問"
	 tags: ["置換積分", "最大値最小値", "三角関数"]
	 format:
		 html:
			 math: mathjax
	 ---

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

- Quarto 本体（qmd → HTML 変換に利用）
	- 例:
		```bash
		wget https://quarto.org/download/latest/quarto-linux-amd64.deb -O /tmp/quarto.deb
		sudo dpkg -i /tmp/quarto.deb || sudo apt-get -f install -y
		```

この構成では、LaTeX やサーバーサイドPDF生成ツールは不要で、
コンテナを比較的軽量に保ちつつ、ブラウザ側で印刷・PDF保存が可能です。

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