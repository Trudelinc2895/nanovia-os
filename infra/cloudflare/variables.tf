variable "cloudflare_api_token" {
  description = "Scoped Cloudflare API token."
  type        = string
  sensitive   = true
}

variable "cloudflare_zone_id" {
  description = "Cloudflare zone ID for nanovia.ca."
  type        = string
}

variable "root_domain" {
  description = "Primary public domain."
  type        = string
  default     = "nanovia.ca"
}

variable "origin_ipv4" {
  description = "Public IPv4 of the OVH VPS origin."
  type        = string
}

variable "proxied" {
  description = "Enable Cloudflare orange-cloud proxy."
  type        = bool
  default     = true
}

variable "enable_admin_record" {
  description = "Create admin.nanovia.ca."
  type        = bool
  default     = true
}

variable "enable_vps_record" {
  description = "Create vps.nanovia.ca."
  type        = bool
  default     = true
}

variable "turnstile_widget_name" {
  description = "Human-readable Turnstile widget name."
  type        = string
  default     = "Nanovia"
}
