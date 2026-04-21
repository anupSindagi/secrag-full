# Build the Docker image
docker build -t sec-ingester .

# For local development (macOS)
mkdir -p /Users/anupsindagi/Documents/Projects/secrag/chroma_db
docker run -d --env-file .env \
  -v /Users/anupsindagi/Documents/Projects/secrag/chroma_db:/app/chroma_db \
  --name sec-ingester \
  --restart unless-stopped \
  sec-ingester

# For remote machine - adjust path based on where you deploy the project

# Option 1: If project is at /opt/secrag or similar (recommended for production)
mkdir -p /opt/secrag/chroma_db
docker run -d --env-file .env \
  -v /opt/secrag/chroma_db:/app/chroma_db \
  --name sec-ingester \
  --restart unless-stopped \
  sec-ingester

# Option 2: If using root-level directory (requires sudo)
mkdir -p /secrag/chroma_db
docker run -d --env-file .env \
  -v /secrag/chroma_db:/app/chroma_db \
  --name sec-ingester \
  --restart unless-stopped \
  sec-ingester

# Option 3: If project is in user's home directory
mkdir -p ~/secrag/chroma_db
docker run -d --env-file .env \
  -v ~/secrag/chroma_db:/app/chroma_db \
  --name sec-ingester \
  --restart unless-stopped \
  sec-ingester