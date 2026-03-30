# 使用するベースイメージ
FROM python:3.11-slim

# OSの依存パッケージをインストール (GDAL, GEOSなどの地理空間ライブラリ)
RUN apt-get update && apt-get install -y \
    libgdal-dev \
    libgeos-dev \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# 作業ディレクトリの設定
WORKDIR /app

# 依存関係のコピーとインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ソースコードとデータのコピー
COPY . .

# 環境変数 (デフォルト)
ENV PORT=8012
ENV API_KEY="mysecret"

# サーバーの起動
CMD ["sh", "-c", "uvicorn main.py:app --host 0.0.0.0 --port $PORT"]
