from pathlib import Path
import os
from typing import Optional
import base64

from openai import OpenAI

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

    # ここで university / exam_year / fields を YAML ヘッダに追記する
    if not raw_qmd.strip():
        return raw_qmd

    lines = raw_qmd.splitlines()
    if lines and lines[0].strip() == "---":
        i = 1
        while i < len(lines) and lines[i].strip() != "---":
            i += 1
        header_lines = lines[1:i]
        body_lines = lines[i + 1 :] if i < len(lines) else []

        # 既存ヘッダがあれば上書き／追記する簡易処理
        def upsert_field(key: str, value: Optional[str]) -> None:
            nonlocal header_lines
            if not value:
                return
            key_prefix = f"  {key}:"
            for idx, line in enumerate(header_lines):
                if line.strip().startswith(f"{key}:") or line.startswith(key_prefix):
                    header_lines[idx] = f"  {key}: \"{value}\""
                    break
            else:
                header_lines.append(f"  {key}: \"{value}\"")

        upsert_field("university", university)
        upsert_field("exam_year", exam_year)

        # 分野タグを自動分類して fields に保存
        try:
            fields = classify_problem_fields(raw_qmd)
        except Exception:
            fields = []
        if fields:
            # 既存の fields があれば上書き
            field_line = "  fields: [" + ", ".join(f'"{f}"' for f in fields) + "]"
            replaced = False
            for idx, line in enumerate(header_lines):
                if line.strip().startswith("fields:") or line.startswith("  fields:"):
                    header_lines[idx] = field_line
                    replaced = True
                    break
            if not replaced:
                header_lines.append(field_line)

        new_lines = ["---", *header_lines, "---", *body_lines]
        return "\n".join(new_lines).strip() + "\n"

    return raw_qmd
