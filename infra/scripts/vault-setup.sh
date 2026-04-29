#!/bin/bash
# ============================================================
# Nanovia OS — HashiCorp Vault secrets setup
# Run this with your Vault CLI configured (vault login first)
# ============================================================

# Login first:
# export VAULT_ADDR="https://your-vault-url"
# vault login

# Store all Nanovia secrets in one path
vault kv put secret/nanovia \
  JWT_SECRET="REPLACE_WITH_openssl_rand_hex_32" \
  SECRET_KEY="REPLACE_WITH_openssl_rand_hex_32" \
  DATABASE_URL="postgresql+psycopg://ktadmin:REPLACE@postgres:5432/ktmonetization" \
  REDIS_URL="redis://redis:6379/0" \
  OPENAI_API_KEY="sk-svcacct-REPLACE" \
  STRIPE_SECRET_KEY="sk_test_51TEr82ARjyNV3UuR_REPLACE" \
  STRIPE_PUBLISHABLE_KEY="pk_test_51TEr82ARjyNV3UuR_REPLACE" \
  STRIPE_WEBHOOK_SECRET="whsec_REPLACE" \
  RESEND_API_KEY="re_REPLACE"

echo "Secrets stored. Verify with:"
echo "vault kv get secret/nanovia"
