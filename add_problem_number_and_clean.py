import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROBLEMS_DIR = ROOT / "problems"

# 行頭の問題番号を検出する (例: "5", "５", "5 旧")
# ASCII digits 0-9 and full-width digits ０-９
number_line_re = re.compile(r"^\s*([0-9０-９]+)(?:\s+.*)?$")


def normalize_digits(s: str) -> str:
    # convert full-width digits to ascii
    fw = "０１２３４５６７８９"
    ascii_d = "0123456789"
    trans = str.maketrans({ord(fw[i]): ascii_d[i] for i in range(10)})
    return s.translate(trans)


def process_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines:
        return False

    # locate first YAML block
    try:
        first = lines.index("---")
        second = lines.index("---", first + 1)
    except ValueError:
        print(f"[SKIP] no YAML in {path}")
        return False

    yaml_lines = lines[first + 1 : second]
    body_lines = lines[second + 1 :]

    # find first non-empty body line (problem number)
    idx = 0
    while idx < len(body_lines) and body_lines[idx].strip() == "":
        idx += 1
    if idx >= len(body_lines):
        print(f"[SKIP] empty body in {path}")
        return False

    m = number_line_re.match(body_lines[idx])
    if not m:
        print(f"[SKIP] no leading number in {path}")
        return False

    raw_number = m.group(1)
    number_ascii = normalize_digits(raw_number)

    # prepare new YAML: add or replace problem_number (idempotent)
    has_problem_number = any(l.lstrip().startswith("problem_number:") for l in yaml_lines)
    new_yaml_lines: list[str] = []

    if has_problem_number:
        # 既にある problem_number を上書きするだけ
        for line in yaml_lines:
            if line.lstrip().startswith("problem_number:"):
                new_yaml_lines.append(f"problem_number: {number_ascii}")
            else:
                new_yaml_lines.append(line)
    else:
        inserted = False
        for line in yaml_lines:
            new_yaml_lines.append(line)
            if line.lstrip().startswith("problem_id:") and not inserted:
                # problem_id の直後に追加
                new_yaml_lines.append(f"problem_number: {number_ascii}")
                inserted = True

        if not inserted:
            # problem_id がない場合はYAML末尾に追加
            new_yaml_lines.append(f"problem_number: {number_ascii}")

    # drop the number line
    new_body = body_lines[:idx] + body_lines[idx + 1 :]

    # remove leading full-width space (U+3000) from next non-empty line
    j = idx
    while j < len(new_body) and new_body[j].strip() == "":
        j += 1
    if j < len(new_body) and new_body[j].startswith("　"):
        new_body[j] = new_body[j].lstrip("　")

    new_lines = ["---"] + new_yaml_lines + ["---"] + new_body
    new_text = "\n".join(new_lines) + "\n"
    path.write_text(new_text, encoding="utf-8")
    print(f"[OK] {path} -> problem_number={number_ascii}")
    return True


def main() -> None:
    changed = 0
    for qmd in PROBLEMS_DIR.rglob("*.qmd"):
        if process_file(qmd):
            changed += 1
    print(f"Total files updated: {changed}")


if __name__ == "__main__":
    main()
