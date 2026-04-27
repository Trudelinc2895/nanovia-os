# Admin panel — minimal deploy stub. The main admin/operator UI currently
# lives in frontend/client/app/admin inside the main web app.
FROM node:20-alpine

RUN addgroup --system appuser && adduser --system --ingroup appuser appuser

WORKDIR /app

RUN echo '{"name":"kt-admin","version":"0.1.0","scripts":{"start":"node server.js"}}' > package.json

COPY infra/docker/admin_server.js ./server.js

RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 3020

CMD ["node", "server.js"]
