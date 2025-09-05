# ---- Base ----
FROM python:3.11-slim

WORKDIR /app

# System deps (tiny set; keep image small)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl && rm -rf /var/lib/apt/lists/*

# ---- Python deps ----
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---- App ----
COPY . .

# Streamlit config: headless + bind to 0.0.0.0:8080 (what EB expects)
RUN mkdir -p /root/.streamlit && \
    /bin/sh -c 'cat > /root/.streamlit/config.toml <<EOF
[server]
headless = true
enableCORS = false
address = "0.0.0.0"
port = 8080
EOF'

EXPOSE 8080
CMD ["streamlit", "run", "app/ui.py", "--server.port", "8080", "--server.address", "0.0.0.0"]
