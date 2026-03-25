# Admin panel — stub minimaliste (sera remplacé par Next.js admin complet)
FROM node:20-alpine

WORKDIR /app

RUN echo '{"name":"kt-admin","version":"0.1.0","scripts":{"start":"node server.js"}}' > package.json

COPY infra/docker/admin_server.js ./server.js

EXPOSE 3020

CMD ["node", "server.js"]
