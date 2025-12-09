from flask import Flask, render_template, request, redirect, url_for, send_from_directory, flash
from werkzeug.utils import secure_filename
from pathlib import Path
import uuid
import os
import yaml

from ocr_to_qmd import image_to_qmd
from solver import generate_solution_qmd, build_handout_qmd
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

        items.append(
            {
                "problem_id": problem_id,
                "title": title,
                "university": university,
                "exam_year": exam_year,
                "fields": fields,
                "has_solution": has_solution,
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


@app.route("/", methods=["GET"])
def index():
    return render_template("upload.html")


@app.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        flash("ファイルが選択されていません。")
        return redirect(url_for("index"))

    file = request.files["file"]
    if file.filename == "":
        flash("ファイル名が空です。")
        return redirect(url_for("index"))

    if not allowed_file(file.filename):
        flash("jpg/jpeg/png 形式のファイルのみアップロードできます。")
        return redirect(url_for("index"))

    filename = secure_filename(file.filename)
    problem_id = uuid.uuid4().hex[:12]
    saved_name = f"{problem_id}_{filename}"
    upload_path = UPLOAD_FOLDER / saved_name
    file.save(upload_path)

    # OpenAI Vision で OCR → qmd
    qmd_text = image_to_qmd(image_path=upload_path, problem_id=problem_id)

    problem_qmd_path = PROBLEM_FOLDER / f"{problem_id}.qmd"
    problem_qmd_path.write_text(qmd_text, encoding="utf-8")

    # 新しい問題を追加したのでインデックスを無効化
    invalidate_problem_index_cache()

    return render_template(
        "preview.html",
        problem_id=problem_id,
        qmd_text=qmd_text,
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

    flash("問題テキスト／メタデータを保存しました。次に解答生成を行ってください。")
    return render_template(
        "solution_preview.html",
        problem_id=problem_id,
        problem_qmd=qmd_text,
        solution_qmd="",
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

    return render_template(
        "solution_preview.html",
        problem_id=problem_id,
        problem_qmd=problem_qmd,
        solution_qmd=solution_qmd,
    )


@app.route("/problem/<problem_id>", methods=["GET"])
def open_problem(problem_id):
    """problems/<problem_id>.qmd を開いて既存のプレビュー画面に載せる。"""

    problem_qmd_path = PROBLEM_FOLDER / f"{problem_id}.qmd"
    if not problem_qmd_path.exists():
        flash(f"問題 {problem_id} が見つかりません。")
        return redirect(url_for("index"))

    qmd_text = problem_qmd_path.read_text(encoding="utf-8")
    return render_template(
        "preview.html",
        problem_id=problem_id,
        qmd_text=qmd_text,
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

    return render_template(
        "solution_preview.html",
        problem_id=problem_id,
        problem_qmd=problem_qmd,
        solution_qmd=solution_qmd,
    )


@app.route("/search", methods=["GET"])
def search():
    """アーカイブ済み問題の簡易検索画面。"""

    reload_flag = request.args.get("reload", "")
    force_reload = reload_flag.lower() in {"1", "true", "yes", "reload"}

    all_items = get_problem_index(force_reload=force_reload)

    # フィルタ UI 用の候補
    universities = sorted({item["university"] for item in all_items if item["university"]})
    years = [item["exam_year"] for item in all_items if item["exam_year"] is not None]
    year_min = min(years) if years else None
    year_max = max(years) if years else None

    selected_university = request.args.get("university", "")
    year_from_raw = request.args.get("year_from", "")
    year_to_raw = request.args.get("year_to", "")
    selected_field = request.args.get("field", "")

    def _parse_year(s: str):
        try:
            return int(s)
        except Exception:
            return None

    year_from = _parse_year(year_from_raw) if year_from_raw else None
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

    results.sort(key=lambda x: (x["university"], x["exam_year"] or 0, x["problem_id"]))

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
    )


@app.route("/archive/<path:filename>")
def serve_archive(filename: str):
    """archive/ 配下の PDF や画像ファイルを配信する。"""

    return send_from_directory(app.config["ARCHIVE_FOLDER"], filename)


@app.route("/handout/<problem_id>", methods=["POST"])
def handout(problem_id):
    problem_qmd_path = PROBLEM_FOLDER / f"{problem_id}.qmd"
    solution_qmd_path = SOLUTION_FOLDER / f"{problem_id}_solution.qmd"

    if not problem_qmd_path.exists() or not solution_qmd_path.exists():
        flash("問題または解答が見つかりません。")
        return redirect(url_for("index"))

    handout_qmd_path = OUTPUT_FOLDER / f"{problem_id}_handout.qmd"

    handout_qmd = build_handout_qmd(
        problem_qmd_path=problem_qmd_path,
        solution_qmd_path=solution_qmd_path,
        problem_id=problem_id,
    )
    handout_qmd_path.write_text(handout_qmd, encoding="utf-8")

    # Quarto で HTML まで生成
    from subprocess import run, CalledProcessError

    html_name = f"{problem_id}_handout.html"
    html_path = OUTPUT_FOLDER / html_name

    try:
        run(
            ["quarto", "render", str(handout_qmd_path), "--to", "html"],
            cwd=str(OUTPUT_FOLDER),
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        flash("Quarto コマンドが見つかりません。Quarto をインストールしてください。")
        return redirect(url_for("index"))
    except CalledProcessError as e:
        flash("Quarto による HTML 生成でエラーが発生しました。")
        print("Quarto error:", e.stderr)
        return redirect(url_for("index"))

    if not html_path.exists():
        flash("HTML ファイルが生成されませんでした。")
        return redirect(url_for("index"))
    # 生成した HTML をそのままブラウザに表示する
    return send_from_directory(
        directory=str(OUTPUT_FOLDER),
        path=html_path.name,
        as_attachment=False,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
