#!/usr/bin/env bash
# infra/scripts/rotate-secrets.sh
# Generates new JWT_SECRET and SECRET_KEY values.
# Writes them to a restricted file instead of stdout.
set -euo pipefail

OUTPUT_PATH="${1:-/root/nanovia-rotated-secrets.env}"

NEW_JWT_SECRET=$(openssl rand -hex 32)
NEW_SECRET_KEY=$(openssl rand -hex 32)

umask 077
cat > "${OUTPUT_PATH}" <<EOF
JWT_SECRET=${NEW_JWT_SECRET}
SECRET_KEY=${NEW_SECRET_KEY}
EOF

chmod 600 "${OUTPUT_PATH}"

echo "Secret rotation bundle written to ${OUTPUT_PATH}"
echo "Next steps:"
echo "  1. Copy the values from ${OUTPUT_PATH} into infra/env/.env.prod"
echo "  2. Restart the API container: docker compose restart api"
echo "  3. Securely delete ${OUTPUT_PATH} after updating production."
