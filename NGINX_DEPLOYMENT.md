# Nginx Deployment Guide for Aegra App

This guide explains the two main ways to deploy nginx with your Aegra app: **Host-based** and **Docker-based**.

## Understanding the Two Approaches

### Scenario 1: Nginx on Host Machine (Traditional Setup)

**Architecture:**
```
Internet → Host Machine (Port 80/443)
              ↓
         Nginx (installed on host OS)
              ↓
         localhost:8000 (Docker port mapping)
              ↓
         Docker Container: aegra:8000
```

**How it works:**
- Nginx is installed directly on your server's operating system (Ubuntu, CentOS, etc.)
- Docker containers expose their ports to the host machine (port mapping: `8000:8000`)
- Nginx connects to the container via `localhost:8000` (the host's localhost)
- This is the **most common production setup**

**Advantages:**
- ✅ Nginx runs as a system service (managed by systemd)
- ✅ Easy SSL certificate management (Let's Encrypt, certbot)
- ✅ Can serve multiple applications from one nginx instance
- ✅ Better for production environments
- ✅ Easier to manage nginx logs and configuration
- ✅ Can use host-based firewall rules

**Disadvantages:**
- ❌ Requires nginx installation on the host
- ❌ Need to manage nginx updates separately
- ❌ Slightly more complex initial setup

---

### Scenario 2: Nginx in Docker (Containerized Setup)

**Architecture:**
```
Internet → Docker Network (Port 80/443)
              ↓
         Nginx Container
              ↓
         Docker Network DNS: aegra:8000
              ↓
         Docker Container: aegra:8000
```

**How it works:**
- Both nginx and aegra-app run as Docker containers
- They communicate via Docker's internal network using service names
- Docker provides DNS resolution: `aegra` resolves to the aegra container's IP
- Nginx container exposes ports 80/443 to the host

**Advantages:**
- ✅ Everything containerized (consistent environment)
- ✅ Easy to version and replicate
- ✅ Can be managed via docker-compose
- ✅ Isolated from host system
- ✅ Easy to scale and update

**Disadvantages:**
- ❌ SSL certificate management is more complex
- ❌ Need to manage Docker networks
- ❌ Logs are inside containers (need volume mounts)
- ❌ More complex for multiple applications

---

## Detailed Setup Instructions

### Scenario 1: Nginx on Host Machine

#### Step 1: Install Nginx (if not already installed)

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install nginx -y
```

**CentOS/RHEL:**
```bash
sudo yum install nginx -y
# or for newer versions:
sudo dnf install nginx -y
```

#### Step 2: Modify the nginx.conf

Change the upstream server in `nginx.conf`:

```nginx
upstream aegra_backend {
    server localhost:8000;  # Changed from 'aegra:8000' to 'localhost:8000'
    keepalive 32;
}
```

**Why?** Because nginx on the host connects to Docker containers via the host's localhost, not Docker's internal DNS.

#### Step 3: Copy Configuration to Nginx Directory

```bash
# Copy the config file
sudo cp /path/to/secrag/nginx.conf /etc/nginx/sites-available/aegra

# Or if you're already in the secrag directory:
sudo cp nginx.conf /etc/nginx/sites-available/aegra
```

**Note:** Some systems use `/etc/nginx/conf.d/` instead of `sites-available`. Check your nginx setup:
- Debian/Ubuntu: Uses `sites-available` and `sites-enabled`
- CentOS/RHEL: Often uses `conf.d` directly

#### Step 4: Enable the Site

**For Debian/Ubuntu (sites-available/sites-enabled):**
```bash
# Create symlink to enable the site
sudo ln -s /etc/nginx/sites-available/aegra /etc/nginx/sites-enabled/aegra

# Remove default site if it exists (optional)
sudo rm /etc/nginx/sites-enabled/default
```

**For CentOS/RHEL (conf.d):**
```bash
# Just copy directly to conf.d (no symlink needed)
sudo cp nginx.conf /etc/nginx/conf.d/aegra.conf
```

#### Step 5: Test Configuration

```bash
# Test nginx configuration for syntax errors
sudo nginx -t
```

Expected output:
```
nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
nginx: configuration file /etc/nginx/nginx.conf test is successful
```

#### Step 6: Ensure Docker Container is Running

Make sure your aegra-app container is running and port 8000 is exposed:

```bash
# Check if container is running
docker ps | grep aegra

# If using docker-compose:
cd /path/to/secrag/aegra-app
docker-compose up -d

# Verify port is accessible
curl http://localhost:8000/health
# or
curl http://localhost:8000/docs
```

#### Step 7: Reload Nginx

```bash
# Reload nginx (graceful restart, no downtime)
sudo systemctl reload nginx

# Or restart if reload doesn't work
sudo systemctl restart nginx

# Check status
sudo systemctl status nginx
```

#### Step 8: Test the Setup

```bash
# Test from the server itself
curl http://localhost/

# Or from another machine (replace with your server IP)
curl http://YOUR_SERVER_IP/
```

#### Step 9: Configure Firewall (if needed)

```bash
# Ubuntu/Debian (ufw)
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw reload

# CentOS/RHEL (firewalld)
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload
```

---

### Scenario 2: Nginx in Docker

#### Step 1: Ensure Docker Network Setup

Your aegra-app docker-compose creates a default network. Check it:

```bash
cd /path/to/secrag/aegra-app
docker-compose up -d

# List networks
docker network ls

# Inspect the network (usually named 'aegra-app_default' or similar)
docker network inspect aegra-app_default
```

#### Step 2: Keep the Original Configuration

The nginx.conf should have:
```nginx
upstream aegra_backend {
    server aegra:8000;  # Keep this - uses Docker DNS
    keepalive 32;
}
```

#### Step 3: Option A - Add Nginx to docker-compose.yml

Add nginx service to your existing `docker-compose.yml`:

```yaml
services:
  # ... existing services (postgres, aegra, redis) ...

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
      # For SSL certificates (if needed):
      # - ./ssl:/etc/nginx/ssl:ro
    depends_on:
      - aegra
    networks:
      - default  # Uses the same network as aegra
```

**Note:** You'll need to copy `nginx.conf` to the `aegra-app` directory, or adjust the volume path.

#### Step 4: Option B - Run Nginx Container Separately

If you prefer to keep nginx separate:

```bash
# Create a custom network (if not using docker-compose network)
docker network create aegra-network

# Add aegra-app to this network
cd /path/to/secrag/aegra-app
docker-compose --project-name aegra up -d
docker network connect aegra-network aegra-app_aegra_1

# Run nginx container
docker run -d \
  --name nginx-proxy \
  --network aegra-network \
  -p 80:80 \
  -p 443:443 \
  -v /path/to/secrag/nginx.conf:/etc/nginx/conf.d/default.conf:ro \
  nginx:alpine
```

#### Step 5: Verify Network Connectivity

```bash
# Check if nginx can reach aegra container
docker exec nginx-proxy ping aegra

# Or test from nginx container
docker exec nginx-proxy curl http://aegra:8000/health
```

#### Step 6: Test the Setup

```bash
# From host machine
curl http://localhost/

# From another machine
curl http://YOUR_SERVER_IP/
```

---

## Key Differences Summary

| Aspect | Host Nginx | Docker Nginx |
|--------|-----------|--------------|
| **Upstream Address** | `localhost:8000` | `aegra:8000` |
| **Network** | Host network | Docker network |
| **DNS Resolution** | Host DNS | Docker internal DNS |
| **Configuration Location** | `/etc/nginx/sites-available/` | Volume mount in container |
| **SSL Management** | Easy (certbot) | More complex (volume mounts) |
| **Logs** | `/var/log/nginx/` | Container logs or volume mounts |
| **Service Management** | `systemctl` | `docker` commands |
| **Best For** | Production, multiple apps | Containerized environments |

---

## Troubleshooting

### Issue: "Connection refused" or "502 Bad Gateway"

**For Host Nginx:**
```bash
# Check if aegra container is running
docker ps | grep aegra

# Check if port 8000 is accessible
curl http://localhost:8000/health

# Check nginx error logs
sudo tail -f /var/log/nginx/aegra_error.log
```

**For Docker Nginx:**
```bash
# Check if both containers are on same network
docker network inspect aegra-app_default

# Test connectivity from nginx container
docker exec nginx-proxy ping aegra
docker exec nginx-proxy curl http://aegra:8000/health

# Check nginx container logs
docker logs nginx-proxy
```

### Issue: "Name resolution failed"

**For Docker Nginx:**
- Ensure both containers are on the same Docker network
- Check service name matches exactly (case-sensitive)
- Verify with: `docker network inspect <network_name>`

### Issue: Nginx config test fails

```bash
# Check syntax
sudo nginx -t

# For Docker nginx:
docker exec nginx-proxy nginx -t
```

---

## Recommendation

**For Production:** Use **Host-based Nginx** (Scenario 1)
- Easier SSL management
- Better integration with system services
- More control and easier debugging

**For Development/Testing:** Either approach works, but Docker nginx is more consistent with containerized setup.

---

## Next Steps

1. **SSL/HTTPS Setup:** Configure SSL certificates (Let's Encrypt recommended)
2. **Domain Configuration:** Update `server_name` in nginx.conf
3. **Security Headers:** Add security headers to nginx config
4. **Rate Limiting:** Configure rate limiting if needed
5. **Monitoring:** Set up log monitoring and alerts

