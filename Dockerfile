# Playwrightの公式イメージを使用 (必要なLinux OSの依存パッケージがすべて含まれています)
FROM mcr.microsoft.com/playwright:v1.41.0-jammy

# Python3 と pip, venv をインストール
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

# ワークディレクトリを設定
WORKDIR /app

# リポジトリ内のすべてのファイルをコンテナの /app にコピー
# （これで「請求書作成」や「注文確認」などの別フォルダもすべてコンテナ内に入ります）
COPY . /app

# Node.js 側のセットアップ
WORKDIR /app/line-bot-secretary
RUN npm install

# Python 側のセットアップ (venv仮想環境を作成)
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Pythonのパッケージをインストール
RUN pip install --no-cache-dir playwright google-cloud-vision python-dotenv

# バージョンの一致を保証するため、Python側にも一応インストール実行
RUN playwright install chromium

# コンテナ起動時に、Node.js サーバーを立ち上げる
CMD ["node", "index.js"]
