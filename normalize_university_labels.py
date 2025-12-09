from __future__ import annotations

"""problems/ 以下の qmd の大学名をコード表記から漢字表記に正規化するスクリプト。

- archive_import.UNIVERSITY_LABELS を真実のソースとして利用
- YAML ヘッダ内の `university:` をコード (01_tokyo など)→漢字 (東京大学 など) に置換
- ついでに `title:` 先頭にコードが残っている場合も漢字に差し替える
- --dry-run オプションで書き込みなしの確認が可能
"""

from pathlib import Path
import argparse

from archive_import import UNIVERSITY_LABELS

BASE_DIR = Path(__file__).resolve().parent
PROBLEMS_DIR = BASE_DIR / "problems"


def normalize_one(path: Path, dry_run: bool = False) -> bool:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return False

    # YAML ヘッダの終端を探す
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return False

    yaml_lines = lines[1:end]
    body_lines = lines[end + 1 :]

    changed = False

    # 一部のファイルで `title::` / `university::` のようにコロンが重複しているものを正規化
    fixed_yaml_lines = []
    for line in yaml_lines:
        original = line
        stripped = line.lstrip()
        if stripped.startswith("title::"):
            # 最初の `::` を `:` に直す
            line = line.replace("title::", "title:", 1)
        if stripped.startswith("university::"):
            line = line.replace("university::", "university:", 1)
        if line is not original:
            changed = True
        fixed_yaml_lines.append(line)

    yaml_lines = fixed_yaml_lines

    # university: の値をコード → 漢字に置換
    for idx, line in enumerate(yaml_lines):
        stripped = line.strip()
        if not stripped.startswith("university:"):
            continue

        key, sep, val = line.partition(":")
        raw = val.strip().strip('"').strip("'")
        new_label = UNIVERSITY_LABELS.get(raw)
        if new_label and raw != new_label:
            yaml_lines[idx] = f"{key}:{sep} \"{new_label}\""
            changed = True

    # title: の先頭がコード表記なら漢字ラベルに差し替える
    for idx, line in enumerate(yaml_lines):
        stripped = line.strip()
        if not stripped.startswith("title:"):
            continue

        key, sep, val = line.partition(":")
        v = val.strip()
        if not (v.startswith('"') and v.endswith('"') and len(v) >= 2):
            break

        inner = v[1:-1]
        original = inner
        for code, label in UNIVERSITY_LABELS.items():
            if inner.startswith(code + " "):
                inner = label + inner[len(code) :]
                break
        if inner != original:
            yaml_lines[idx] = f"{key}:{sep} \"{inner}\""
            changed = True
        break

    if not changed:
        return False

    new_text = "\n".join(["---", *yaml_lines, "---", *body_lines]) + "\n"

    if dry_run:
        print(f"[dry-run] {path.name} would be updated")
    else:
        path.write_text(new_text, encoding="utf-8")
        print(f"[update] {path.name}")

    return True


def normalize_all(dry_run: bool = False) -> None:
    if not PROBLEMS_DIR.exists():
        print("problems/ ディレクトリが見つかりません。")
        return

    count_changed = 0
    for path in sorted(PROBLEMS_DIR.glob("*.qmd")):
        if normalize_one(path, dry_run=dry_run):
            count_changed += 1

    if dry_run:
        print(f"[dry-run] {count_changed} files would be updated.")
    else:
        print(f"[done] {count_changed} files updated.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize university labels in problems/*.qmd")
    parser.add_argument("--dry-run", action="store_true", help="変更内容のみ表示し、ファイルは更新しない")
    args = parser.parse_args()

    normalize_all(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
