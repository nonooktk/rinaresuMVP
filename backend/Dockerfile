# りなれす バックエンド（FastAPI）用 Dockerfile。
#
# Azure Container Apps へのデプロイを前提とする。
# DB(SQLite)・写真・PDF は /app/data 配下に保存され、
# 本番では /app/data に Azure Files がマウントされる想定。
# （database.py / slip_pdf.py は BASE_DIR = /app を基準に data/ を解決する）
FROM python:3.12-slim

WORKDIR /app

# 依存関係を先にインストールしてレイヤキャッシュを効かせる
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# アプリ本体をコピー（app/ は /app/app に配置される。BASE_DIR は /app となり data は /app/data）
COPY app ./app

# 起動時に database.py / slip_pdf.py が /app/data 配下を mkdir するが、
# Azure Files マウント前でも動くよう事前に用意しておく
RUN mkdir -p /app/data

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
