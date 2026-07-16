FROM python:3.11-slim

WORKDIR /app/stock

# gcc/g++ needed by lxml
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir \
    -r requirements.txt \
    "streamlit==1.50.0" \
    yfinance \
    pytz \
    numpy \
    finvizfinance \
    edgartools

# Application code (portal + all scripts it calls via subprocess or import)
COPY stock_portal.py \
     lib.py \
     constants.py \
     compute_growth_metrics.py \
     discover_new_companies.py \
     screener_downloader.py \
     fetch_market_data.py \
     us_stock_downloader.py \
     ./

# Streamlit config — theme only, no SSL (terminate TLS at your reverse proxy)
RUN mkdir -p /root/.streamlit
RUN printf '[theme]\nbase = "dark"\nbackgroundColor = "#0b0e1a"\nsecondaryBackgroundColor = "#111827"\ntextColor = "#f1f5f9"\nprimaryColor = "#818cf8"\nfont = "sans serif"\n' \
    > /root/.streamlit/config.toml

# Directories expected by the app
RUN mkdir -p /app/logs /app/data /app/stock/logs /app/stock/cache

EXPOSE 8501

CMD ["streamlit", "run", "stock_portal.py", \
     "--server.port=8501", \
     "--server.headless=true", \
     "--server.address=0.0.0.0"]
