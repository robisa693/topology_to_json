version: "3.9"

services:

  # ── FastAPI application ──────────────────────────────────────────────────────
  app:
    build: .
    container_name: topology-app
    restart: unless-stopped
    expose:
      - "8080"
    networks:
      - internal
    # The app is NOT exposed directly to the internet.
    # All traffic flows through nginx below.

  # ── nginx reverse proxy with TLS ────────────────────────────────────────────
  nginx:
    image: nginx:1.27-alpine
    container_name: topology-nginx
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/certs:/etc/nginx/certs:ro   # your TLS cert + key go here
    depends_on:
      - app
    networks:
      - internal

networks:
  internal:
    driver: bridge