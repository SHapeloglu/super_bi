# SuperBI (FastAPI) arka uç imajı. Arayüz (frontend) bu imaja girmez; host nginx diskten sunar.
# Adımlar: Python imajı, bağımlılıklar, app klasörü, uvicorn ile başlatma (port 8000).
# DİKKAT: USER tanımlı değil; konteyner root olarak çalışır (düzeltilmedi, bilgi amaçlı).
FROM python:3.12-slim
WORKDIR /opt/superbi
# Önce bağımlılık dosyası kopyalanır: kod değişse bile pip katmanı önbellekten gelir.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Yalnız app klasörü kopyalanır. Veriler (data) imaja girmez; compose ile dışarıdan bağlanır.
COPY app ./app
EXPOSE 8000
# uvicorn tek işçi ile 0.0.0.0:8000 üzerinde çalışır (konteyner içinde). Dışa açılış docker-compose'ta yapılır.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
