from pathlib import Path
import os
from typing import Optional
import base64

import env  # noqa: F401  # .env を自動読み込み
from openai import OpenAI
import yaml

from classifier import classify_problem_fields


SYSTEM_PROMPT = """You are an OCR assistant for mathematical exam problems.
You receive a photo of a math problem and must output only a Quarto-compatible Markdown (qmd) of the problem statement.

Requirements:
- Detect and transcribe all text and math formulas.
- Use inline math as $...$.
- Use display math as $$ ... $$ on separate lines.
- Do NOT use \[ ... \] or any LaTeX environments like \begin{align}.
- Preserve line breaks in a natural way, suitable for exam problems.
- Do NOT invent problem statements; strictly follow the image.
- Output MUST be a complete qmd document starting with a YAML header.

YAML header template (fill title with the problem_id you are given and keep problem_id field. If university or exam_year are given, they will be filled later by the application):
---
  title: "{problem_id}"
  problem_id: "{problem_id}"
  format:
    html:
      math: mathjax
---

After the YAML header, write the problem text as qmd.
Do not include explanations or answers, only the problem statement.
"""


def _build_system_prompt(problem_id: str) -> str:
    return SYSTEM_PROMPT.replace("{problem_id}", problem_id)


def image_to_qmd(
    image_path: Path,
    problem_id: str,
    model: Optional[str] = None,
    university: Optional[str] = None,
    exam_year: Optional[str] = None,
) -> str:
    """Call OpenAI Vision model to convert an image of a math problem into qmd text.

    university, exam_year は任意で、後から YAML ヘッダに追記するために使用する。
    """

    client = OpenAI()

    vision_model = model or os.environ.get("OPENAI_VISION_MODEL", "gpt-4.1-mini")

    with open(image_path, "rb") as f:
        image_bytes = f.read()

    # OpenAI API は JSON 経由で画像を受け取るため Base64 文字列にする
    image_b64 = base64.b64encode(image_bytes).decode("ascii")

    system_prompt = _build_system_prompt(problem_id)

    resp = client.chat.completions.create(
        model=vision_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "以下の画像から、指定のルールに従って qmd 形式で問題文だけを書き起こしてください。",
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                    },
                ],
            },
        ],
        max_completion_tokens=4096,
    )

    content = resp.choices[0].message.content
    if isinstance(content, list):
        # SDK によっては list で返る場合があるので連結
        raw_qmd = "".join(part.get("text", "") for part in content)  # type: ignore[arg-type]
    else:
        raw_qmd = content or ""

    # ここで university / exam_year / fields を YAML ヘッダに追記し、
    # 既存の problems ディレクトリと同じ書式に整える
    if not raw_qmd.strip():
        return raw_qmd

    lines = raw_qmd.splitlines()
    if lines and lines[0].strip() == "---":
        i = 1
        while i < len(lines) and lines[i].strip() != "---":
            i += 1
        header_lines = lines[1:i]
        body_lines = lines[i + 1 :] if i < len(lines) else []

        header_text = "\n".join(header_lines)
        try:
            meta = yaml.safe_load(header_text) or {}
        except Exception:
            meta = {}
        if not isinstance(meta, dict):
            meta = {}

        # problem_id / title は最低限そろえておく
        meta["problem_id"] = str(meta.get("problem_id") or problem_id)
        if not str(meta.get("title", "")).strip():
            meta["title"] = meta["problem_id"]

        # 大学名・年度があれば現在のフォーマットに合わせて付与
        if university:
            meta["university"] = university
        if exam_year:
            meta["exam_year"] = str(exam_year)

        # 分野タグを自動分類して fields に保存（リスト形式に統一）
        try:
            fields = classify_problem_fields(raw_qmd)
        except Exception:
            fields = []
        if fields:
            meta["fields"] = list(fields)

        # YAML を problems/ と同様のスタイルで書き出す（トップレベルキー + 配列）
        new_header = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True).strip()
        new_lines = ["---", *new_header.splitlines(), "---", *body_lines]
        return "\n".join(new_lines).strip() + "\n"

    return raw_qmd
