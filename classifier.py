from typing import List, Optional

from openai import OpenAI

from taxonomy import FIELDS


CLASSIFY_SYSTEM_PROMPT = """あなたは高校数学の問題を分類する数学の教員です。

与えられた問題文（日本語、qmd互換テキスト）に対して、以下の分野リストから
最も適切だと思われる分野タグを1〜3個選んでください。

分野リスト:
{field_list}

ルール:
- 問題文の内容から判断し、当てはまるものだけ選ぶこと。
- 迷う場合は主要な分野を優先して 1〜2 個に絞ること。
- 出力は YAML 形式で、以下の形だけを返してください:

---
fields: ["タグ1", "タグ2"]
---

それ以外の文章や説明は一切書かないでください。
"""


def _build_system_prompt() -> str:
    field_list = "\n".join(f"- {name}" for name in FIELDS)
    return CLASSIFY_SYSTEM_PROMPT.format(field_list=field_list)


def _strip_yaml_header(qmd: str) -> str:
    lines = qmd.splitlines()
    if not lines or lines[0].strip() != "---":
        return qmd
    i = 1
    while i < len(lines) and lines[i].strip() != "---":
        i += 1
    if i >= len(lines):
        return qmd
    return "\n".join(lines[i + 1 :])


def classify_problem_fields(problem_qmd: str, model: Optional[str] = None) -> List[str]:
    """問題 qmd から分野 tags (fields) を推定して返す。

    失敗した場合は空リストを返す。
    """

    body = _strip_yaml_header(problem_qmd or "").strip()
    if not body:
        return []

    client = OpenAI()
    fields_model = model or "gpt-4.1-mini"

    system_prompt = _build_system_prompt()

    resp = client.chat.completions.create(
        model=fields_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": "以下は高校数学の問題文です。指定の YAML 形式で分野タグを返してください。\n\n" + body,
            },
        ],
        max_completion_tokens=512,
    )

    content = resp.choices[0].message.content or ""

    # ごく簡単なパース（fields: ["..."] の部分だけ抜き出す）
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    result: List[str] = []
    for line in lines:
        if line.startswith("fields:"):
            # 例: fields: ["積分法", "数列"]
            left = line.split("[", 1)
            if len(left) != 2:
                break
            inside = left[1].rsplit("]", 1)[0]
            raw_items = [item.strip().strip("\"'") for item in inside.split(",")]
            result = [item for item in raw_items if item]
            break

    # 未知タグは落とし、マスタにあるものだけ残す
    normalized = [name for name in result if name in FIELDS]
    return normalized
