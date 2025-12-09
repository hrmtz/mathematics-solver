from pathlib import Path
from typing import Optional
import os
import re

import env  # noqa: F401  # .env を自動読み込み
from openai import OpenAI


SOLUTION_SYSTEM_PROMPT = """あなたは高校数学〜大学入試レベルの模範解答を作成する数学講師です。

# 役割
- 与えられた問題文（Quarto互換の qmd）に対して、日本語で丁寧な模範解答を作成します。
- 誘導がある場合は必ず従って解答を構成します。
- 途中式を省略せず、論理の飛躍を避けて説明します。
- 証明問題では、日本語の文章を丁寧に書き、理由を明記します。

# 出力形式
- 出力は qmd 互換の Markdown とします。
- 数式のルール：
  - インライン数式は $...$ を用いる。
  - ディスプレイ数式は $$ ... $$ を用い、前後を空行で囲む。
  - \[ ... \] や \begin{align} などの環境は使用しない。
- 問題本文をそのまま繰り返さず、「解答」だけを記述します。

# 重要
- 解答が複数の小問に分かれる場合は、(1),(2),... のようなラベルを明示してください。
- 定義や定理を使うときは、何を用いたかを文章で簡潔に述べてください。
"""


def _strip_solution_heading(text: str) -> str:
    """先頭に付いた "## 解答" 見出しを取り除く。

    既存の解答ファイルやモデル出力の先頭に付くことがあるので、
    プレビューや handout では冗長な見出しを隠す目的で使う。
    """

    if not text:
        return text

    lines = text.splitlines()
    i = 0
    # 先頭の空行をスキップ
    while i < len(lines) and not lines[i].strip():
        i += 1

    if i < len(lines) and lines[i].lstrip().startswith("## 解答"):
        i += 1
        # 見出し直後の空行も飛ばす
        while i < len(lines) and not lines[i].strip():
            i += 1
        return "\n".join(lines[i:]).lstrip("\n")

    return text


def generate_solution_qmd(problem_qmd: str, problem_id: str, model: Optional[str] = None) -> str:
    """Generate a solution qmd from a problem qmd using OpenAI."""

    client = OpenAI()

    solution_model = model or os.environ.get("OPENAI_SOLUTION_MODEL", "gpt-5.1")

    messages = [
        {"role": "system", "content": SOLUTION_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "以下は大学入試数学の問題文です。"
                "これに対する模範解答を、指定された qmd 形式で作成してください。\n\n" + problem_qmd
            ),
        },
    ]

    resp = client.chat.completions.create(
        model=solution_model,
        messages=messages,
        max_completion_tokens=4096,
    )

    content = resp.choices[0].message.content
    if content is None:
        return "(解答生成に失敗しました。)"

    return _strip_solution_heading(content)


HANDOUT_YAML_HEADER = """---
lang: ja
format:
  html:
    theme: default
    toc: false
    number-sections: false
    css: ../static/handout-print.css
---

"""


def _sanitize_tex_for_handout(text: str) -> str:
    """MathJax / Quarto で問題になりやすい TeX を handout 用に軽くサニタイズする。

    現状は、OCR 由来で頻出する ``\hspace{1zw}`` などの ``zw`` 単位を
    MathJax が理解できる ``\quad`` に置き換えるだけ。
    """

    if not text:
        return text

    # \hspace{...zw} → \quad に変換
    t = re.sub(r"\\hspace\{[^}]*zw\}", r"\\quad ", text)

    # LaTeX の description 環境を、問題プレビューと同様のロジックで
    # シンプルな段落（HTML）に変換する
    lines = t.splitlines()
    out_lines = []
    for line in lines:
        stripped = line.strip()

        if stripped.startswith(r"\begin{description}"):
            continue
        if stripped.startswith(r"\end{description}"):
            continue

        m = re.match(r"^\\item\[(.*?)\](.*)$", stripped)
        if m:
            label = m.group(1).strip()
            body = m.group(2).strip()
            if label:
                # 問題プレビュー同様、ラベルを太字にした段落として出力
                out_lines.append(f"<p><strong>{label}</strong> {body}</p>")
            else:
                out_lines.append(f"<p>{body}</p>")
            continue

        out_lines.append(line)

    return "\n".join(out_lines)


def build_handout_qmd(problem_qmd_path: Path, solution_qmd_path: Path, problem_id: str) -> str:
    """Generate a combined handout qmd from problem and solution qmd files."""

    problem_qmd = problem_qmd_path.read_text(encoding="utf-8")
    solution_qmd = solution_qmd_path.read_text(encoding="utf-8")

    # 問題側の YAML ヘッダを剥がして本文だけ取り出す
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

    # ハンドアウトでは元PDFリンクやスキャン画像は不要なので削除する
    filtered_lines = []
    for line in body.splitlines():
        stripped = line.strip()
        # 末尾の区切り用の水平線（---）も削除しておく
        if stripped == "---":
            continue
        if stripped.startswith("元問題 PDF:") or stripped.startswith("元問題スキャン:"):
            continue
        filtered_lines.append(line)
    body = "\n".join(filtered_lines).strip()
    body = _sanitize_tex_for_handout(body)

    parts = [
        HANDOUT_YAML_HEADER.strip(),
        "",
        "<div class=\"main-wrap\">",
        "",
        "<section id=\"problem-section\">",
        "# 問題",
        "",
        body,
        "</section>",
        "",
        "<section id=\"solution-section\">",
        "# 解答",
        "",
        _sanitize_tex_for_handout(_strip_solution_heading(solution_qmd.strip())),
        "</section>",
        "",
        "</div>",
    ]
    return "\n".join(parts) + "\n"