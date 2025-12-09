from __future__ import annotations

"""Assign math fields to problem qmds under problems/ using OpenAI.

- problems/*.qmd を走査
- classifier.classify_problem_fields() で分野タグ候補を取得
- YAML ヘッダ内に fields: [...] を追記（既にある場合はスキップ）
- --problem-id で単一問題だけ対象に、--dry-run で書き込みなしプレビュー
"""

from pathlib import Path
from typing import Iterable, List, Optional
import argparse

from classifier import classify_problem_fields

BASE_DIR = Path(__file__).resolve().parent
PROBLEMS_DIR = BASE_DIR / "problems"


def iter_problem_qmds(problem_id: Optional[str] = None) -> Iterable[Path]:
    if problem_id:
        path = PROBLEMS_DIR / f"{problem_id}.qmd"
        if path.exists():
            yield path
        return

    if not PROBLEMS_DIR.exists():
        return

    for path in sorted(PROBLEMS_DIR.glob("*.qmd")):
        yield path


def add_fields_to_yaml(qmd_text: str, fields: List[str]) -> str:
    """YAML ヘッダに fields を追記して新しいテキストを返す。

    - すでに fields: がある場合は元のテキストをそのまま返す。
    - YAML ヘッダがなければ何もしない。
    """

    if not fields:
        return qmd_text

    lines = qmd_text.splitlines()
    if not lines or lines[0].strip() != "---":
        return qmd_text

    # 既に fields があれば上書きはしない
    for line in lines:
        if line.strip().startswith("fields:"):
            return qmd_text

    # YAML ヘッダ終端を探す
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return qmd_text

    header = lines[1:end]
    body = lines[end:]

    # format: セクションの直前に挿入するのが自然そうなので、そこを探す
    insert_at = len(header)
    for i, line in enumerate(header):
        if line.lstrip().startswith("format:"):
            insert_at = i
            break

    new_header: List[str] = []
    new_header.extend(header[:insert_at])
    new_header.append("fields:")
    for f in fields:
        new_header.append(f"  - {f}")
    new_header.extend(header[insert_at:])

    new_lines = ["---", *new_header, *body]
    return "\n".join(new_lines) + ("\n" if qmd_text.endswith("\n") else "")


def assign_fields(problem_id: Optional[str], dry_run: bool) -> None:
    for path in iter_problem_qmds(problem_id):
        text = path.read_text(encoding="utf-8")
        fields = classify_problem_fields(text)
        if not fields:
            print(f"[skip] {path.name}: no fields suggested")
            continue

        print(f"[classify] {path.name}: {fields}")
        new_text = add_fields_to_yaml(text, fields)
        if new_text == text:
            print(f"  -> unchanged (already has fields or no yaml)")
            continue

        if dry_run:
            print("  -> dry-run, not writing")
        else:
            path.write_text(new_text, encoding="utf-8")
            print("  -> updated")


def main() -> None:
    parser = argparse.ArgumentParser(description="Assign math fields to problem qmd files.")
    parser.add_argument("--problem-id", help="対象とする problem_id（省略時は全問題）")
    parser.add_argument("--dry-run", action="store_true", help="書き込まず結果だけ表示")
    args = parser.parse_args()

    assign_fields(problem_id=args.problem_id, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
