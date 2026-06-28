# Build a standard Docker image so Railway uses the Dockerfile builder and skips
# the mise/Railpack Python installer, which was failing the build on GitHub
# artifact attestation verification for the prebuilt CPython.
FROM python:3.11-slim

WORKDIR /app

# Install deps first for layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Public demo runs in mock mode: no real 1Password vault, no live LLM, no secrets
# baked in. To go live, set MOCK_OP=0 plus the secret env vars (OP_SERVICE_ACCOUNT_TOKEN,
# TRUSTLANE_SECRET_REF, ANTHROPIC_API_KEY, LIVE_LLM=1) in the Railway dashboard.
ENV MOCK_OP=1

# server.py binds to $PORT (Railway injects it), defaulting to 8077 locally.
CMD ["python", "server.py"]
