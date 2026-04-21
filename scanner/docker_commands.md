docker build -t sec-scanner .
docker run -d --name sec-scanner --env-file .env --restart unless-stopped sec-scanner