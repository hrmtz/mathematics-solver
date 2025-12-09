from __future__ import annotations

r"""Import TeX problems under archive/ into qmd files under problems/.

- archive/<university>/<year>/*.tex を走査
- problem_id = "<university>-<year>-<stem>"
- TeX 本文 (document 環境内) を抽出
- \includegraphics を実画像 (fig_*.jpg など) へマッピングし Markdown 画像に変換
- YAML にメタデータ (university, exam_year, source_tex, pdf_source, page_image) を付与
- 既存 qmd がある場合はスキップ
- --university / --year で絞り込み, --dry-run で出力のみ
"""

from dataclasses import dataclass
from pathlib import Path
import argparse
import re
from typing import Iterable, Optional

BASE_DIR = Path(__file__).resolve().parent
ARCHIVE_DIR = BASE_DIR / "archive"
PROBLEMS_DIR = BASE_DIR / "problems"


UNIVERSITY_LABELS = {
    "01_tokyo": "東京大学",
    "02_kyoto": "京都大学",
    "03_hokudai": "北海道大学",
    "04_tohoku": "東北大学",
    "05_nagoya": "名古屋大学",
    "06_osaka": "大阪大学",
    "07_kyushu": "九州大学",
    "08_titech": "東京科学大学",
}


@dataclass
class TeXProblem:
    university: str  # コード (例: "01_tokyo")
    year: str        # ディレクトリ名そのまま (例: "1961")
    tex_path: Path

    @property
    def stem(self) -> str:
        return self.tex_path.stem

    @property
    def problem_id(self) -> str:
        return f"{self.university}-{self.year}-{self.stem}"

    @property
    def university_label(self) -> str:
        return UNIVERSITY_LABELS.get(self.university, self.university)

    @property
    def pdf_path(self) -> Path:
        return self.tex_path.with_suffix(".pdf")

    @property
    def page_image_path(self) -> Path:
        return self.tex_path.with_suffix(".jpg")

    @property
    def qmd_path(self) -> Path:
        return PROBLEMS_DIR / f"{self.problem_id}.qmd"

    @property
    def rel_tex(self) -> str:
        return str(self.tex_path.relative_to(BASE_DIR).as_posix())

    @property
    def rel_pdf(self) -> str:
        if self.pdf_path.exists():
            return str(self.pdf_path.relative_to(BASE_DIR).as_posix())
        return ""

    @property
    def rel_page_image(self) -> str:
        if self.page_image_path.exists():
            return str(self.page_image_path.relative_to(BASE_DIR).as_posix())
        return ""


BEGIN_DOC = re.compile(r"\\begin\{document\}")
END_DOC = re.compile(r"\\end\{document\}")
COMMENT_LINE = re.compile(r"^\s*%")
INCLUDEGRAPHICS = re.compile(r"\\includegraphics(\[[^]]*\])?\s*\{([^}]+)\}")
HUGE_GROUP = re.compile(r"\{\\huge\s+([^}]*)\}")
FLUSHLEFT_ENV = re.compile(r"\\begin\{flushleft\}|\\end\{flushleft\}")
SETLENGTH_CMD = re.compile(r"\\setlength\{[^}]*\}\{[^}]*\}")


def iter_tex_problems(university: Optional[str], year: Optional[str]) -> Iterable[TeXProblem]:
    if not ARCHIVE_DIR.exists():
        return []

    for uni_dir in sorted(ARCHIVE_DIR.iterdir()):
        if not uni_dir.is_dir():
            continue
        uni_code = uni_dir.name
        if university and uni_code != university:
            continue

        for year_dir in sorted(uni_dir.iterdir()):
            if not year_dir.is_dir():
                continue
            year_code = year_dir.name
            if year and year_code != year:
                continue

            for tex_path in sorted(year_dir.glob("*.tex")):
                yield TeXProblem(university=uni_code, year=year_code, tex_path=tex_path)


def extract_document_body(tex_text: str) -> str:
    r"""\begin{document}〜\end{document} の中だけを取り出し、軽く整形する。"""
    begin_match = BEGIN_DOC.search(tex_text)
    end_match = END_DOC.search(tex_text)
    if begin_match and end_match and end_match.start() > begin_match.end():
        body = tex_text[begin_match.end() : end_match.start()]
    else:
        body = tex_text

    lines: list[str] = []
    for raw_line in body.splitlines():
        line = raw_line.rstrip("\n\r")
        if COMMENT_LINE.match(line):
            continue
        if "%" in line:
            line = line.split("%", 1)[0]
        # TeX の \ 改行を Markdown の段落改行 (空行) に寄せる
        line = line.replace(r"\\", "\n\n")
        # {\\huge 1} のような装飾を除去し、中身だけか空にする
        line = HUGE_GROUP.sub(r"\1", line)
        lines.append(line.rstrip())

    # 連続空行を最大 2 行に正規化
    normalized: list[str] = []
    empty_count = 0
    for line in lines:
        if line.strip() == "":
            empty_count += 1
            if empty_count <= 2:
                normalized.append("")
        else:
            empty_count = 0
            normalized.append(line)

    text = "\n".join(normalized).strip()

    # レイアウト専用の TeX コマンドは Markdown には不要なので削除
    text = FLUSHLEFT_ENV.sub("", text)
    text = SETLENGTH_CMD.sub("", text)
    if not text.endswith("\n"):
        text += "\n"
    return text


def replace_includegraphics(problem: TeXProblem, body: str) -> str:
    """includegraphics を実画像またはプレースホルダに置換する。"""

    def _repl(match: re.Match[str]) -> str:
        arg = match.group(2).strip()
        img_name = Path(arg).name
        # 拡張子がなければ .jpg とみなす
        if not Path(img_name).suffix:
            img_name = img_name + ".jpg"

        img_abs = problem.tex_path.parent / img_name
        if img_abs.exists():
            rel = Path("archive") / problem.university / problem.year / img_name
            # qmd は problems/ に置くので、そこからの相対パスは ../archive/... になる
            rel_from_qmd = Path("..") / rel
            return f"\n\n![]({rel_from_qmd.as_posix()})\n\n"
        # 画像が見つからない場合はプレースホルダ
        return f"\n\n![図: {arg} ※対応する画像ファイルが見つかりません]\n\n"

    return INCLUDEGRAPHICS.sub(_repl, body)


def build_qmd(problem: TeXProblem, body: str) -> str:
    uni_label = problem.university_label
    year = problem.year
    stem = problem.stem

    yaml_lines = [
        "---",
        f"title: \"{uni_label} {year}年 {stem}\"",
        f"problem_id: \"{problem.problem_id}\"",
        f"university: \"{uni_label}\"",
        f"exam_year: \"{year}\"",
        f"source_tex: \"{problem.rel_tex}\"",
        f"pdf_source: \"{problem.rel_pdf}\"",
        f"page_image: \"{problem.rel_page_image}\"",
        "format:",
        "  html:",
        "    math: mathjax",
        "---",
        "",
    ]

    # problems/ から見た PDF / ページ画像への相対パスを作る
    pdf_link = ""
    img_link = ""
    if problem.rel_pdf:
        pdf_link = (Path("..") / Path(problem.rel_pdf)).as_posix()
    if problem.rel_page_image:
        img_link = (Path("..") / Path(problem.rel_page_image)).as_posix()

    tail_lines = ["", "---", ""]
    if pdf_link:
        tail_lines.append(f"元問題 PDF: [こちらを開く]({pdf_link})")
    # スキャン画像はプレビューでは不要なのでフッターには出さない
    tail_lines.append("")

    return "\n".join(yaml_lines) + body.rstrip() + "\n" + "\n".join(tail_lines)


def import_archive(university: Optional[str], year: Optional[str], dry_run: bool) -> None:
    PROBLEMS_DIR.mkdir(parents=True, exist_ok=True)

    def _read_tex(path: Path) -> str:
        """TeX ファイルを適切なエンコードで読み込む (UTF-8 / Shift-JIS 試行)。"""

        data = path.read_bytes()
        for enc in ("utf-8", "cp932", "shift_jis"):
            try:
                return data.decode(enc)
            except UnicodeDecodeError:
                continue
        # 最後の fallback: 壊れた文字は捨てるが、とにかく読み込む
        return data.decode("utf-8", errors="ignore")

    for problem in iter_tex_problems(university=university, year=year):
        out_path = problem.qmd_path
        if out_path.exists():
            print(f"[skip] {problem.problem_id} -> {out_path} (already exists)")
            continue

        tex_text = _read_tex(problem.tex_path)
        body = extract_document_body(tex_text)
        body = replace_includegraphics(problem, body)
        qmd_text = build_qmd(problem, body)

        print(f"[generate] {problem.problem_id} -> {out_path}")
        if not dry_run:
            out_path.write_text(qmd_text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Import archive TeX files into qmd problems.")
    parser.add_argument("--university", help="archive 配下の大学コード (例: 01_tokyo)")
    parser.add_argument("--year", help="年度ディレクトリ名 (例: 1961)")
    parser.add_argument("--dry-run", action="store_true", help="生成内容のみ表示し、ファイルは出力しない")
    args = parser.parse_args()

    import_archive(university=args.university, year=args.year, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
