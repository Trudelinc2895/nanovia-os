# Security Policy — Nanovia

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.x (main) | ✅ |

## Reporting a Vulnerability

**DO NOT** open a public GitHub issue for security vulnerabilities.

**Contact:** security@nanovia.ca  
**Response time:** 24h acknowledgement, 72h initial assessment

Please include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (optional)

We commit to:
- Acknowledge within 24h
- Provide status updates every 72h
- Credit reporters in release notes (if desired)
- No legal action for good-faith research

## Security Measures

See [MASTER_TRACE.md](./MASTER_TRACE.md) for full security architecture.

Active protections:
- Argon2id password hashing (time=2, mem=64MB)
- JWT RS256 + refresh tokens
- Rate limiting (Redis-backed, per-IP per-plan)
- WAF: SQL injection, XSS, path traversal, scanner blocking
- 20-layer VPS hardening (CrowdSec, fail2ban, PSAD, auditd...)
- HTTPS enforced (HSTS max-age=31536000)
- CSRF protection on all state-changing endpoints
