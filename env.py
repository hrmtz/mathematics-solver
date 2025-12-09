from __future__ import annotations

"""Project-wide environment loader.

このモジュールをインポートすると、カレントディレクトリ（または親ディレクトリ）にある
`.env` ファイルを自動で読み込みます。

コード側では単に `import env` するだけで OK です。
"""

from pathlib import Path

from dotenv import load_dotenv, find_dotenv

# プロジェクトルート直下の .env を優先的に探す
_root = Path(__file__).resolve().parent
_dotenv_path = find_dotenv(usecwd=True) or str(_root / ".env")

if _dotenv_path:
    load_dotenv(_dotenv_path, override=False)
