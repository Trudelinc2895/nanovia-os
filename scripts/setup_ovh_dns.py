"""
OVH DNS Auto-Configuration for tkverse.ca
==========================================
STEP 1: Create API credentials at:
  https://ca.api.ovh.com/createToken/

  Use these settings:
    - Application name: kt-monetization-dns
    - Application description: KT Monetization OS DNS setup
    - Validity: Unlimited
    - Rights:
        GET    /domain/zone/tkverse.ca/*
        POST   /domain/zone/tkverse.ca/*
        DELETE /domain/zone/tkverse.ca/*
        POST   /domain/zone/tkverse.ca/refresh

  You'll get: APP_KEY, APP_SECRET, CONSUMER_KEY

STEP 2: Fill in the values below and run:
  python scripts/setup_ovh_dns.py
"""

import sys

# ── Fill these in ──────────────────────────────────────────────────
APP_KEY      = "YOUR_APP_KEY"
APP_SECRET   = "YOUR_APP_SECRET"
CONSUMER_KEY = "YOUR_CONSUMER_KEY"
# ──────────────────────────────────────────────────────────────────

ZONE   = "tkverse.ca"
VPS_IP = "167.114.155.166"
TTL    = 300

RECORDS = [
    {"fieldType": "A", "subDomain": "",        "target": VPS_IP},  # root @
    {"fieldType": "A", "subDomain": "www",     "target": VPS_IP},
    {"fieldType": "A", "subDomain": "api",     "target": VPS_IP},
    {"fieldType": "A", "subDomain": "admin",   "target": VPS_IP},
    {"fieldType": "A", "subDomain": "monitor", "target": VPS_IP},
    {"fieldType": "TXT","subDomain": "",       "target": f"v=spf1 ip4:{VPS_IP} -all"},
]

if __name__ == "__main__":
    if "YOUR_APP_KEY" in APP_KEY:
        print("❌ Fill in APP_KEY, APP_SECRET, CONSUMER_KEY first.")
        print("   → https://ca.api.ovh.com/createToken/")
        sys.exit(1)

    try:
        import ovh
    except ImportError:
        print("Installing ovh library...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "ovh", "-q"])
        import ovh

    client = ovh.Client(
        endpoint="ovh-ca",
        application_key=APP_KEY,
        application_secret=APP_SECRET,
        consumer_key=CONSUMER_KEY,
    )

    # Fetch existing records to avoid duplicates
    print(f"[~] Fetching existing records for {ZONE}...")
    existing_ids = client.get(f"/domain/zone/{ZONE}/record")
    existing = []
    for rid in existing_ids:
        r = client.get(f"/domain/zone/{ZONE}/record/{rid}")
        existing.append(r)

    added = 0
    skipped = 0

    for rec in RECORDS:
        # Check if already exists
        already = any(
            e.get("fieldType") == rec["fieldType"]
            and e.get("subDomain") == rec["subDomain"]
            and e.get("target") == rec["target"]
            for e in existing
        )
        if already:
            label = f"{rec['subDomain'] or '@'}.{ZONE}" if rec['subDomain'] else ZONE
            print(f"  ↷ SKIP  {rec['fieldType']:5s} {label} (already exists)")
            skipped += 1
            continue

        # Delete old conflicting records of same type+subdomain
        conflicts = [
            e["id"] for e in existing
            if e.get("fieldType") == rec["fieldType"]
            and e.get("subDomain") == rec["subDomain"]
        ]
        for cid in conflicts:
            client.delete(f"/domain/zone/{ZONE}/record/{cid}")
            print(f"  ✗ DELETED old record id={cid}")

        result = client.post(
            f"/domain/zone/{ZONE}/record",
            fieldType=rec["fieldType"],
            subDomain=rec["subDomain"],
            target=rec["target"],
            ttl=TTL,
        )
        label = f"{rec['subDomain']}.{ZONE}" if rec["subDomain"] else ZONE
        print(f"  ✅ ADDED  {rec['fieldType']:5s} {label} → {rec['target']}")
        added += 1

    # Refresh zone
    print(f"\n[~] Refreshing DNS zone...")
    client.post(f"/domain/zone/{ZONE}/refresh")
    print(f"[✅] Zone refreshed.")

    print(f"\n{'='*50}")
    print(f"Done. Added: {added}  Skipped: {skipped}")
    print(f"\nDNS propagation takes 1–15 min.")
    print(f"Test with: Resolve-DnsName tkverse.ca -Type A")
    print(f"Or visit:  http://tkverse.ca")
