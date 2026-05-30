#!/usr/bin/env bash
# infra/scripts/rotate-secrets.sh
# Generates new JWT_SECRET and SECRET_KEY values.
# Does NOT overwrite any file automatically — copy the values manually.
set -euo pipefail

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║         Nanovia OS — Secret Rotation                     ║"
echo "╠══════════════════════════════════════════════════════════╣"
echo "║  New values generated below.                             ║"
echo "║  Update your .env.prod manually — this script            ║"
echo "║  does NOT write to any file.                             ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

NEW_JWT_SECRET=$(openssl rand -hex 32)
NEW_SECRET_KEY=$(openssl rand -hex 32)

echo "JWT_SECRET=${NEW_JWT_SECRET}"
echo "SECRET_KEY=${NEW_SECRET_KEY}"
echo ""
echo "Steps:"
echo "  1. Copy the values above into infra/env/.env.prod"
echo "  2. Restart the API container:  docker compose restart api"
echo "  3. All existing JWT tokens will be invalidated — users must re-login."
echo ""
echo "WARNING: Never commit .env.prod to git."
