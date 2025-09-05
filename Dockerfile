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
    printf "[server]\nheadless = true\nenableCORS = false\naddress = \"0.0.0.0\"\nport = 8080\n" \
    > /root/.streamlit/config.toml

EXPOSE 8080
CMD ["streamlit", "run", "app/ui.py", "--server.port", "8080", "--server.address", "0.0.0.0"]
