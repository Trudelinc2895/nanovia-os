locals {
  login_paths = [
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/contact",
    "/api/v1/billing/checkout-session",
    "/api/v1/billing/module-checkout-session",
    "/api/v1/billing/credits/purchase",
    "/api/v1/billing/addon/checkout",
    "/api/v1/billing/portal-session",
  ]
}

resource "cloudflare_record" "apex" {
  zone_id = var.cloudflare_zone_id
  name    = var.root_domain
  type    = "A"
  value   = var.origin_ipv4
  proxied = var.proxied
  ttl     = 1
}

resource "cloudflare_record" "www" {
  zone_id = var.cloudflare_zone_id
  name    = "www"
  type    = "CNAME"
  value   = var.root_domain
  proxied = var.proxied
  ttl     = 1
}

resource "cloudflare_record" "admin" {
  count   = var.enable_admin_record ? 1 : 0
  zone_id = var.cloudflare_zone_id
  name    = "admin"
  type    = "A"
  value   = var.origin_ipv4
  proxied = var.proxied
  ttl     = 1
}

resource "cloudflare_record" "vps" {
  count   = var.enable_vps_record ? 1 : 0
  zone_id = var.cloudflare_zone_id
  name    = "vps"
  type    = "A"
  value   = var.origin_ipv4
  proxied = false
  ttl     = 1
}

resource "cloudflare_ruleset" "custom_firewall" {
  zone_id     = var.cloudflare_zone_id
  name        = "nanovia-custom-firewall"
  description = "Nanovia custom WAF rules"
  kind        = "zone"
  phase       = "http_request_firewall_custom"

  rules {
    action      = "block"
    enabled     = true
    description = "Block common exploit probes"
    expression  = "(http.request.uri.path contains \"/wp-admin\") or (http.request.uri.path contains \"/xmlrpc.php\") or (http.request.uri.path contains \"/.env\")"
  }

  rules {
    action      = "managed_challenge"
    enabled     = true
    description = "Challenge auth, contact, and checkout surfaces"
    expression  = join(" or ", [for path in local.login_paths : "(http.request.uri.path eq \"${path}\" and http.request.method eq \"POST\")"])
  }
}

resource "cloudflare_ruleset" "rate_limits" {
  zone_id     = var.cloudflare_zone_id
  name        = "nanovia-rate-limits"
  description = "Nanovia baseline rate limits"
  kind        = "zone"
  phase       = "http_ratelimit"

  rules {
    action      = "block"
    enabled     = true
    description = "Rate limit auth and payment abuse"
    expression  = join(" or ", [for path in local.login_paths : "(http.request.uri.path eq \"${path}\" and http.request.method eq \"POST\")"])

    ratelimit {
      characteristics     = ["cf.colo.id", "ip.src"]
      period              = 60
      requests_per_period = 20
      mitigation_timeout  = 600
    }
  }
}
