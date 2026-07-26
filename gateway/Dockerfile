# Gateway: nginx como reverse proxy + OAuth2 Proxy como sidecar auth
# Se despliega como servicios separados en el docker-compose maestro

# Este Dockerfile es solo para nginx con su configuración
FROM nginx:alpine

COPY nginx.conf /etc/nginx/nginx.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
