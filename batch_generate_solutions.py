from __future__ import annotations

"""problems/ 以下の qmd から、過去 N 年分の未解答問題だけ解答を一括生成するスクリプト。

- problems/*.qmd を走査して YAML ヘッダを読む
- exam_year が指定範囲内のものを対象にする（デフォルト: 現在年から遡って10年分）
- solutions/<problem_id>_solution.qmd がまだ無いものだけ solver.generate_solution_qmd() を呼ぶ
- --dry-run で API 呼び出し・書き込み無しに対象だけ確認可能
- --from-year / --to-year / --university で絞り込みも可能
"""

from pathlib import Path
from datetime import datetime
from typing import Optional
import argparse
import yaml

import env  # noqa: F401  # .env を自動読み込み
from solver import generate_solution_qmd

BASE_DIR = Path(__file__).resolve().parent
PROBLEMS_DIR = BASE_DIR / "problems"
SOLUTIONS_DIR = BASE_DIR / "solutions"


def read_meta(path: Path) -> tuple[Optional[str], Optional[int], Optional[str]]:
    """qmd の YAML ヘッダから (problem_id, exam_year, university) を取得する。

    YAML が無い / 壊れている場合は (stem, None, None) を返す。
    """

    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return path.stem, None, None

    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return path.stem, None, None

    yaml_text = "\n".join(lines[1:end])
    try:
        meta = yaml.safe_load(yaml_text) or {}
    except Exception:
        return path.stem, None, None

    problem_id = meta.get("problem_id") or path.stem
    year_raw = meta.get("exam_year")
    try:
        exam_year = int(year_raw)
    except Exception:
        exam_year = None

    university = meta.get("university") or None

    return problem_id, exam_year, university


def should_target(
    exam_year: Optional[int],
    university: Optional[str],
    from_year: Optional[int],
    to_year: Optional[int],
    filter_university: Optional[str],
) -> bool:
    """指定のフィルタに基づき、この問題を対象にするか判定する。"""

    if exam_year is None:
        return False

    if from_year is not None and exam_year < from_year:
        return False
    if to_year is not None and exam_year > to_year:
        return False

    if filter_university:
        if not university or university != filter_university:
            return False

    return True


def batch_generate_solutions(
    from_year: Optional[int],
    to_year: Optional[int],
    university: Optional[str],
    dry_run: bool,
) -> None:
    if not PROBLEMS_DIR.exists():
        print("problems/ ディレクトリが見つかりません。")
        return

    SOLUTIONS_DIR.mkdir(parents=True, exist_ok=True)

    # デフォルトは「現在年から遡って10年分」
    if from_year is None and to_year is None:
        current_year = datetime.now().year
        from_year = current_year - 9
        to_year = current_year

    print("[info] target range:", end=" ")
    if from_year is not None:
        print(f"from {from_year}", end=" ")
    if to_year is not None:
        print(f"to {to_year}", end=" ")
    if university:
        print(f"university={university}", end=" ")
    print()

    count_total = 0
    count_skipped_has_solution = 0
    count_generated = 0

    for path in sorted(PROBLEMS_DIR.glob("*.qmd")):
        problem_id, exam_year, univ = read_meta(path)

        if not should_target(exam_year, univ, from_year, to_year, university):
            continue

        count_total += 1
        solution_path = SOLUTIONS_DIR / f"{problem_id}_solution.qmd"
        if solution_path.exists():
            count_skipped_has_solution += 1
            print(f"[skip] {problem_id}: solution already exists")
            continue

        print(f"[gen]  {problem_id} (year={exam_year}, univ={univ})")
        if dry_run:
            print("      -> dry-run, not calling OpenAI / not writing file")
            continue

        # 実際に解答を生成
        problem_qmd = path.read_text(encoding="utf-8")
        solution_qmd = generate_solution_qmd(problem_qmd=problem_qmd, problem_id=problem_id)
        solution_path.write_text(solution_qmd, encoding="utf-8")
        count_generated += 1

    print("[summary] total candidates:", count_total)
    print("[summary] already had solution:", count_skipped_has_solution)
    print("[summary] newly generated:", count_generated)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "problems/*.qmd のうち指定された年度範囲の未解答問題について、"
            "OpenAI を使って solutions/*.qmd を一括生成します。"
        )
    )
    parser.add_argument("--from-year", type=int, help="対象とする exam_year の下限（省略時は現在年から遡って10年）")
    parser.add_argument("--to-year", type=int, help="対象とする exam_year の上限")
    parser.add_argument("--university", type=str, help="特定の大学名だけを対象にする（例: 東京大学）")
    parser.add_argument("--dry-run", action="store_true", help="API を呼ばず書き込みもしない（対象だけ確認）")
    args = parser.parse_args()

    batch_generate_solutions(
        from_year=args.from_year,
        to_year=args.to_year,
        university=args.university,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
