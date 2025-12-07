from flask import Flask, render_template, request, redirect, url_for, send_from_directory, flash
from werkzeug.utils import secure_filename
from pathlib import Path
import uuid
import os

from ocr_to_qmd import image_to_qmd
from solver import generate_solution_qmd, build_handout_qmd

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_FOLDER = BASE_DIR / "uploads"
PROBLEM_FOLDER = BASE_DIR / "problems"
SOLUTION_FOLDER = BASE_DIR / "solutions"
OUTPUT_FOLDER = BASE_DIR / "output"

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png"}

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key")

app.config["UPLOAD_FOLDER"] = str(UPLOAD_FOLDER)
app.config["PROBLEM_FOLDER"] = str(PROBLEM_FOLDER)
app.config["SOLUTION_FOLDER"] = str(SOLUTION_FOLDER)
app.config["OUTPUT_FOLDER"] = str(OUTPUT_FOLDER)

for folder in [UPLOAD_FOLDER, PROBLEM_FOLDER, SOLUTION_FOLDER, OUTPUT_FOLDER]:
    folder.mkdir(parents=True, exist_ok=True)


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


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
    university = request.form.get("university", "").strip()
    exam_year = request.form.get("exam_year", "").strip()
    problem_id = uuid.uuid4().hex[:12]
    saved_name = f"{problem_id}_{filename}"
    upload_path = UPLOAD_FOLDER / saved_name
    file.save(upload_path)

    # OpenAI Vision で OCR → qmd
    qmd_text = image_to_qmd(
        image_path=upload_path,
        problem_id=problem_id,
        university=university or None,
        exam_year=exam_year or None,
    )

    problem_qmd_path = PROBLEM_FOLDER / f"{problem_id}.qmd"
    problem_qmd_path.write_text(qmd_text, encoding="utf-8")

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

    return render_template(
        "solution_preview.html",
        problem_id=problem_id,
        problem_qmd=problem_qmd,
        solution_qmd=solution_qmd,
    )


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

    # Quarto で handout.qmd から HTML を生成し、そのHTMLをブラウザで表示して印刷してもらう
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

    # 生成されたHTMLをそのまま返す（ブラウザの印刷機能でPDF化などを行う）
    return send_from_directory(
        directory=str(OUTPUT_FOLDER),
        path=html_path.name,
        as_attachment=False,
        download_name=html_path.name,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
