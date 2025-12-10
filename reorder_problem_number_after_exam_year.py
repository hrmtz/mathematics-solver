from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROBLEMS_DIR = ROOT / "problems"


def process_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines:
        return False

    try:
        first = lines.index("---")
        second = lines.index("---", first + 1)
    except ValueError:
        return False

    yaml_lines = lines[first + 1 : second]

    # 探索: problem_number と exam_year
    problem_idx = None
    exam_idx = None
    for i, line in enumerate(yaml_lines):
        stripped = line.lstrip()
        if stripped.startswith("problem_number:") and problem_idx is None:
            problem_idx = i
        if stripped.startswith("exam_year:") and exam_idx is None:
            exam_idx = i

    # どちらかが無ければ何もしない
    if problem_idx is None or exam_idx is None:
        return False

    # すでに exam_year の直後なら何もしない
    if problem_idx == exam_idx + 1:
        return False

    # problem_number 行を取り出して exam_year の直後に挿入
    line_to_move = yaml_lines.pop(problem_idx)

    # pop 後にインデックスが変わるので exam_year を取り直す
    exam_idx = None
    for i, line in enumerate(yaml_lines):
        if line.lstrip().startswith("exam_year:"):
            exam_idx = i
            break
    if exam_idx is None:
        # 念のため: 見つからなければ末尾に追加
        yaml_lines.append(line_to_move)
    else:
        yaml_lines.insert(exam_idx + 1, line_to_move)

    new_lines = lines[: first + 1] + yaml_lines + lines[second:]
    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    print(f"[REORDER] {path}")
    return True


def main() -> None:
    changed = 0
    for qmd in PROBLEMS_DIR.rglob("*.qmd"):
        if process_file(qmd):
            changed += 1
    print(f"Total files reordered: {changed}")


if __name__ == "__main__":
    main()
