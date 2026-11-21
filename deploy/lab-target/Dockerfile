# syntax=docker/dockerfile:1.7
FROM nginx:1.27-alpine

RUN apk add --no-cache openssl \
    && mkdir -p /etc/nginx/certs /usr/share/nginx/html/admin /usr/share/nginx/html/login \
    && openssl req -x509 -nodes -newkey rsa:2048 -days 825 \
         -keyout /etc/nginx/certs/lab.key \
         -out /etc/nginx/certs/lab.crt \
         -subj "/CN=lab-target.surfacex.local" \
         -addext "subjectAltName=DNS:lab-target.surfacex.local,DNS:lab-target" \
    && rm -rf /usr/share/nginx/html/*

COPY html/ /usr/share/nginx/html/
COPY nginx/default.conf /etc/nginx/conf.d/default.conf

EXPOSE 80 443 8080

HEALTHCHECK --interval=10s --timeout=3s --retries=10 --start-period=5s \
  CMD wget -qO- http://127.0.0.1:80/ >/dev/null || exit 1
