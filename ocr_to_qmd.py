from pathlib import Path
import os
from typing import Optional
import base64

from openai import OpenAI


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

YAML header template (fill title with the problem_id you are given and keep problem_id field):
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


def image_to_qmd(image_path: Path, problem_id: str, model: Optional[str] = None) -> str:
    """Call OpenAI Vision model to convert an image of a math problem into qmd text."""

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
        return "".join(part.get("text", "") for part in content)  # type: ignore[arg-type]

    return content or ""
