FROM python:3.11-slim

# WeasyPrint + Quarto + 日本語フォント
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       wget \
       ca-certificates \
       libffi8 \
       libpango-1.0-0 \
       libpangocairo-1.0-0 \
       libcairo2 \
       libjpeg62-turbo \
       libpng16-16 \
       fonts-noto-cjk \
    # Quarto 本体インストール
     && wget https://quarto.org/download/latest/quarto-linux-amd64.deb -O /tmp/quarto.deb \
     && dpkg -i /tmp/quarto.deb || apt-get install -y -f \
     && rm -f /tmp/quarto.deb \
     && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# requirements.txt は開発用だが、コンテナ内では明示的に依存を指定してインストールする
COPY requirements.txt .
RUN pip install --no-cache-dir \
    flask \
    openai \
    werkzeug \
    pyyaml \
    python-dotenv

COPY . .

ENV FLASK_APP=app.py \
    FLASK_RUN_HOST=0.0.0.0 \
    FLASK_RUN_PORT=5000

EXPOSE 5000

CMD ["flask", "run"]
