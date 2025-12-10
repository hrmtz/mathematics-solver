from flask import Flask, render_template, request, redirect, url_for, send_from_directory, flash
from werkzeug.utils import secure_filename
from pathlib import Path
import uuid
import os
import re
import random
import yaml

import env  # noqa: F401  # .env を自動読み込み
from ocr_to_qmd import image_to_qmd
from solver import generate_solution_qmd, build_handout_qmd, _sanitize_tex_for_handout
from taxonomy import FIELDS as FIELD_CATEGORIES

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_FOLDER = BASE_DIR / "uploads"
PROBLEM_FOLDER = BASE_DIR / "problems"
SOLUTION_FOLDER = BASE_DIR / "solutions"
OUTPUT_FOLDER = BASE_DIR / "output"
ARCHIVE_FOLDER = BASE_DIR / "archive"

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png"}

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key")

app.config["UPLOAD_FOLDER"] = str(UPLOAD_FOLDER)
app.config["PROBLEM_FOLDER"] = str(PROBLEM_FOLDER)
app.config["SOLUTION_FOLDER"] = str(SOLUTION_FOLDER)
app.config["OUTPUT_FOLDER"] = str(OUTPUT_FOLDER)
app.config["ARCHIVE_FOLDER"] = str(ARCHIVE_FOLDER)

for folder in [UPLOAD_FOLDER, PROBLEM_FOLDER, SOLUTION_FOLDER, OUTPUT_FOLDER]:
    folder.mkdir(parents=True, exist_ok=True)


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _load_problem_index():
    """problems/ 以下の qmd から検索用インデックスを構築する。"""

    items = []
    for path in sorted(PROBLEM_FOLDER.glob("*.qmd")):
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        if not lines or lines[0].strip() != "---":
            continue

        # YAML ヘッダ部分だけ取り出す
        end = None
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                end = i
                break
        if end is None:
            continue

        yaml_text = "\n".join(lines[1:end])
        try:
            meta = yaml.safe_load(yaml_text) or {}
        except Exception:
            continue

        problem_id = meta.get("problem_id") or path.stem
        title = meta.get("title") or problem_id
        university = meta.get("university") or ""
        year_raw = meta.get("exam_year")
        try:
            exam_year = int(year_raw)
        except Exception:
            exam_year = None
        fields = meta.get("fields") or []
        if isinstance(fields, str):
            fields = [fields]

        has_solution = (SOLUTION_FOLDER / f"{problem_id}_solution.qmd").exists()

        # 本文の最初の数文字を検索結果に出すためのスニペットを生成
        body_lines = lines[end + 1 :]
        # 先頭の空行をスキップ
        while body_lines and not body_lines[0].strip():
            body_lines.pop(0)
        body = "\n".join(body_lines).strip()
        # 改行・連続空白を 1 つのスペースにまとめる
        body_compact = " ".join(body.split())

        # LaTeX/MathJax 記法をざっくり削除してプレーンテキストにする
        def strip_math(s: str) -> str:
            if not s:
                return ""
            # display 数式 $$ ... $$ や \[ ... \]
            s = re.sub(r"\$\$.*?\$\$", " ", s)
            s = re.sub(r"\\\[.*?\\\]", " ", s)
            # inline 数式 $ ... $ や \( ... \)
            s = re.sub(r"\$.*?\$", " ", s)
            s = re.sub(r"\\\(.*?\\\)", " ", s)
            # \alpha や \frac などのコマンド名を削除
            s = re.sub(r"\\[A-Za-z]+", "", s)
            # 中括弧など構文用の記号を削る
            s = s.replace("{", "").replace("}", "")
            return s

        plain = strip_math(body_compact)
        plain_compact = " ".join(plain.split())
        # 問題文の冒頭 20 文字だけを検索結果に表示
        snippet = plain_compact[:20]

        items.append(
            {
                "problem_id": problem_id,
                "title": title,
                "university": university,
                "exam_year": exam_year,
                "fields": fields,
                "has_solution": has_solution,
                "snippet": snippet,
            }
        )

    return items


_problem_index_cache = None


def invalidate_problem_index_cache() -> None:
    """問題インデックスキャッシュを無効化する。"""

    global _problem_index_cache
    _problem_index_cache = None


def get_problem_index(force_reload: bool = False):
    """検索用インデックスを取得する（必要に応じて再構築）。"""

    global _problem_index_cache
    if force_reload or _problem_index_cache is None:
        _problem_index_cache = _load_problem_index()
    return _problem_index_cache


def _extract_meta_from_qmd_text(qmd_text: str) -> dict:
    """qmd テキストから YAML メタデータを辞書として取り出す。"""

    if not qmd_text:
        return {}

    lines = qmd_text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}

    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return {}

    yaml_text = "\n".join(lines[1:end])
    try:
        meta = yaml.safe_load(yaml_text) or {}
    except Exception:
        meta = {}
    return meta


def _build_citation_label(meta: dict) -> str:
    """YAML メタから `[大学, 年度]` 形式の出典文字列を生成する。"""

    if not meta:
        return ""

    university = meta.get("university") or ""
    exam_year = meta.get("exam_year") or ""

    parts = []
    if university:
        parts.append(str(university))
    if exam_year:
        parts.append(str(exam_year))

    if not parts:
        return ""
    return f"[{', '.join(parts)}]"


@app.route("/", methods=["GET"])
def index():
    # トップページでは問題検索をメインにする
    return redirect(url_for("search"))


@app.route("/upload", methods=["GET", "POST"])
def upload():
    """問題画像のアップロードフォーム表示とアップロード処理。"""

    # GET: アップロードフォームを表示
    if request.method == "GET":
        return render_template("upload.html")

    # POST: 実際のファイルアップロード処理
    if "file" not in request.files:
        flash("ファイルが選択されていません。")
        return redirect(url_for("upload"))

    file = request.files["file"]
    if file.filename == "":
        flash("ファイル名が空です。")
        return redirect(url_for("upload"))

    if not allowed_file(file.filename):
        flash("jpg/jpeg/png 形式のファイルのみアップロードできます。")
        return redirect(url_for("upload"))

    filename = secure_filename(file.filename)
    problem_id = uuid.uuid4().hex[:12]
    saved_name = f"{problem_id}_{filename}"
    upload_path = UPLOAD_FOLDER / saved_name
    file.save(upload_path)

    # フォームから大学名・年度を受け取り、YAML ヘッダに反映させる
    university = request.form.get("university") or None
    exam_year = request.form.get("exam_year") or None

    # OpenAI Vision で OCR → qmd
    qmd_text = image_to_qmd(
        image_path=upload_path,
        problem_id=problem_id,
        university=university,
        exam_year=exam_year,
    )

    problem_qmd_path = PROBLEM_FOLDER / f"{problem_id}.qmd"
    problem_qmd_path.write_text(qmd_text, encoding="utf-8")

    # 新しい問題を追加したのでインデックスを無効化
    invalidate_problem_index_cache()

    meta = _extract_meta_from_qmd_text(qmd_text)
    citation_label = _build_citation_label(meta)

    return render_template(
        "preview.html",
        problem_id=problem_id,
        qmd_text=qmd_text,
        citation_label=citation_label,
    )


@app.route("/meta/<problem_id>", methods=["POST"])
def update_meta(problem_id):
    # textarea から qmd 全体を受け取り、そのまま保存する
    qmd_text = request.form.get("qmd_text", "")
    if not qmd_text.strip():
        flash("内容が空です。")
        return redirect(url_for("index"))

    problem_qmd_path = PROBLEM_FOLDER / f"{problem_id}.qmd"
    problem_qmd_path.write_text(qmd_text, encoding="utf-8")

    # メタデータが変わると検索条件に影響するのでインデックスを無効化
    invalidate_problem_index_cache()

    meta = _extract_meta_from_qmd_text(qmd_text)
    citation_label = _build_citation_label(meta)

    flash("問題テキスト／メタデータを保存しました。次に解答生成を行ってください。")
    return render_template(
        "solution_preview.html",
        problem_id=problem_id,
        problem_qmd=qmd_text,
        solution_qmd="",
        citation_label=citation_label,
    )


@app.route("/solve/<problem_id>", methods=["POST"])
def solve(problem_id):
    problem_qmd_path = PROBLEM_FOLDER / f"{problem_id}.qmd"
    if not problem_qmd_path.exists():
        flash("問題ファイルが見つかりません。")
        return redirect(url_for("index"))

    problem_qmd = problem_qmd_path.read_text(encoding="utf-8")

    solution_qmd = generate_solution_qmd(problem_qmd=problem_qmd, problem_id=problem_id)

    solution_qmd_path = SOLUTION_FOLDER / f"{problem_id}_solution.qmd"
    solution_qmd_path.write_text(solution_qmd, encoding="utf-8")

    # 解答の有無フラグが変わるのでインデックスを無効化
    invalidate_problem_index_cache()

    meta = _extract_meta_from_qmd_text(problem_qmd)
    citation_label = _build_citation_label(meta)

    return render_template(
        "solution_preview.html",
        problem_id=problem_id,
        problem_qmd=problem_qmd,
        solution_qmd=solution_qmd,
        citation_label=citation_label,
    )


@app.route("/problem/<problem_id>", methods=["GET"])
def open_problem(problem_id):
    """problems/<problem_id>.qmd を開いて既存のプレビュー画面に載せる。"""

    problem_qmd_path = PROBLEM_FOLDER / f"{problem_id}.qmd"
    if not problem_qmd_path.exists():
        flash(f"問題 {problem_id} が見つかりません。")
        return redirect(url_for("index"))

    qmd_text = problem_qmd_path.read_text(encoding="utf-8")

    meta = _extract_meta_from_qmd_text(qmd_text)
    citation_label = _build_citation_label(meta)

    return render_template(
        "preview.html",
        problem_id=problem_id,
        qmd_text=qmd_text,
        citation_label=citation_label,
    )


@app.route("/problem/<problem_id>/solution", methods=["GET"])
def open_problem_with_solution(problem_id):
    """問題と（あれば）既存の解答をまとめてプレビューする。"""

    problem_qmd_path = PROBLEM_FOLDER / f"{problem_id}.qmd"
    solution_qmd_path = SOLUTION_FOLDER / f"{problem_id}_solution.qmd"

    if not problem_qmd_path.exists():
        flash(f"問題 {problem_id} が見つかりません。")
        return redirect(url_for("search"))

    problem_qmd = problem_qmd_path.read_text(encoding="utf-8")
    solution_qmd = ""
    if solution_qmd_path.exists():
        solution_qmd = solution_qmd_path.read_text(encoding="utf-8")

    meta = _extract_meta_from_qmd_text(problem_qmd)
    citation_label = _build_citation_label(meta)

    return render_template(
        "solution_preview.html",
        problem_id=problem_id,
        problem_qmd=problem_qmd,
        solution_qmd=solution_qmd,
        citation_label=citation_label,
    )


@app.route("/search", methods=["GET"])
def search():
    """アーカイブ済み問題の簡易検索画面。"""

    reload_flag = request.args.get("reload", "")
    force_reload = reload_flag.lower() in {"1", "true", "yes", "reload"}

    all_items = get_problem_index(force_reload=force_reload)

    # solutions/ 配下の最新状態を見て has_solution フラグを更新する
    for item in all_items:
        pid = item.get("problem_id")
        if not pid:
            item["has_solution"] = False
            continue
        solution_path = SOLUTION_FOLDER / f"{pid}_solution.qmd"
        item["has_solution"] = solution_path.exists()

    # フィルタ UI 用の候補
    universities = sorted({item["university"] for item in all_items if item["university"]})
    years = [item["exam_year"] for item in all_items if item["exam_year"] is not None]
    year_min = min(years) if years else None
    year_max = max(years) if years else None
    year_options = []
    if year_min is not None and year_max is not None:
        # 新しい年度から古い年度へ降順で並べる
        year_options = list(range(year_max, year_min - 1, -1))

    selected_university = request.args.get("university", "")
    year_from_raw = request.args.get("year_from", "")
    year_to_raw = request.args.get("year_to", "")
    selected_field = request.args.get("field", "")
    mode = request.args.get("mode", "search")  # "search" or "random"

    def _parse_year(s: str):
        try:
            return int(s)
        except Exception:
            return None

    # 年度 from は、指定がなければデフォルトで 2015 年以降に絞る
    DEFAULT_YEAR_FROM = 2015
    if year_from_raw:
        year_from = _parse_year(year_from_raw)
    else:
        if year_min is not None:
            year_from = max(DEFAULT_YEAR_FROM, year_min)
            year_from_raw = str(year_from)
        else:
            year_from = None
    year_to = _parse_year(year_to_raw) if year_to_raw else None

    results = []
    for item in all_items:
        if selected_university and item["university"] != selected_university:
            continue
        if year_from is not None and (item["exam_year"] is None or item["exam_year"] < year_from):
            continue
        if year_to is not None and (item["exam_year"] is None or item["exam_year"] > year_to):
            continue
        if selected_field and selected_field not in item.get("fields", []):
            continue
        results.append(item)

    # 通常検索: 新しい問題が上に来るように降順で並べる
    if mode != "random":
        results.sort(key=lambda x: (x["university"], x["exam_year"] or 0, x["problem_id"]), reverse=True)
    else:
        # ランダムモード: フィルタ結果から最大 10 問を無作為抽出
        random.shuffle(results)
        results = results[:10]

    return render_template(
        "search.html",
        universities=universities,
        fields=FIELD_CATEGORIES,
        results=results,
        selected_university=selected_university,
        year_from=year_from_raw,
        year_to=year_to_raw,
        selected_field=selected_field,
        year_min=year_min,
        year_max=year_max,
        year_options=year_options,
    )


@app.route("/archive/<path:filename>")
def serve_archive(filename: str):
    """archive/ 配下の PDF や画像ファイルを配信する。"""

    return send_from_directory(app.config["ARCHIVE_FOLDER"], filename)


@app.route("/handout/<problem_id>", methods=["POST"])
def handout(problem_id):
    """問題・解答ハンドアウトをプレビューと同じロジックで表示する。"""

    problem_qmd_path = PROBLEM_FOLDER / f"{problem_id}.qmd"
    solution_qmd_path = SOLUTION_FOLDER / f"{problem_id}_solution.qmd"

    if not problem_qmd_path.exists() or not solution_qmd_path.exists():
        flash("問題または解答が見つかりません。")
        return redirect(url_for("index"))

    problem_qmd = problem_qmd_path.read_text(encoding="utf-8")
    solution_qmd = solution_qmd_path.read_text(encoding="utf-8")

    meta = _extract_meta_from_qmd_text(problem_qmd)
    citation_label = _build_citation_label(meta)

    # Quarto ではなく、プレビューと同じ JS ベースの描画で表示する
    return render_template(
        "handout_view.html",
        problem_id=problem_id,
        problem_qmd=problem_qmd,
        solution_qmd=solution_qmd,
        citation_label=citation_label,
    )


def _extract_problem_body_for_test(problem_qmd: str) -> str:
    """テスト用プリント向けに、問題 qmd から本文だけを取り出して軽く整形する。"""

    lines = problem_qmd.splitlines()
    body_lines = []
    if lines and lines[0].strip() == "---":
        i = 1
        while i < len(lines) and lines[i].strip() != "---":
            i += 1
        if i < len(lines):
            body_lines = lines[i + 1 :]
        else:
            body_lines = lines
    else:
        body_lines = lines

    body = "\n".join(body_lines).strip()

    # ハンドアウトと同様に、元PDFリンクやスキャン画像などは削除する
    filtered_lines = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped == "---":
            continue
        if stripped.startswith("元問題 PDF:") or stripped.startswith("元問題スキャン:"):
            continue
        filtered_lines.append(line)

    body = "\n".join(filtered_lines).strip()
    return _sanitize_tex_for_handout(body)


@app.route("/test/create", methods=["POST"])
def create_test():
    """検索結果から選択した複数の問題を 1 つのテスト画面にまとめる。

    プレビューと同じ JS ベースの変換ロジックで描画する。
    """

    problem_ids = request.form.getlist("problem_ids")
    if not problem_ids:
        flash("テスト用に出題する問題を 1 問以上選択してください。")
        return redirect(url_for("search"))

    problems_ctx = []
    for idx, pid in enumerate(problem_ids, start=1):
        qmd_path = PROBLEM_FOLDER / f"{pid}.qmd"
        if not qmd_path.exists():
            continue

        text = qmd_path.read_text(encoding="utf-8")
        lines = text.splitlines()
        meta = {}
        if lines and lines[0].strip() == "---":
            end = None
            for i in range(1, len(lines)):
                if lines[i].strip() == "---":
                    end = i
                    break
            if end is not None:
                yaml_text = "\n".join(lines[1:end])
                try:
                    meta = yaml.safe_load(yaml_text) or {}
                except Exception:
                    meta = {}

        university = meta.get("university") or ""
        exam_year = meta.get("exam_year") or ""
        problem_number = meta.get("problem_number") or ""

        citation_parts = []
        if university:
            citation_parts.append(str(university))
        if exam_year:
            citation_parts.append(str(exam_year))
        citation_label = f"[{', '.join(citation_parts)}]" if citation_parts else ""

        header_parts = []
        if exam_year:
            header_parts.append(str(exam_year))
        if university:
            header_parts.append(str(university))
        if problem_number:
            header_parts.append(f"第{problem_number}問")
        header_label = " ".join(header_parts) if header_parts else pid

        # QMD 全体を渡し、クライアント側でプレビューと同じ変換を行う
        problems_ctx.append(
            {
                "idx": idx,
                "problem_id": pid,
                "header_label": header_label,
                "qmd_text": text,
                "citation_label": citation_label,
            }
        )

    if not problems_ctx:
        flash("選択された問題ファイルが見つかりませんでした。")
        return redirect(url_for("search"))

    return render_template("test_view.html", problems=problems_ctx)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
