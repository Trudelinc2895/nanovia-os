"""
OVH DNS Auto-Configuration for Nanovia.

Usage:
  set OVH_APP_KEY=...
  set OVH_APP_SECRET=...
  set OVH_CONSUMER_KEY=...
  set PUBLIC_IP=...
  python scripts/setup_ovh_dns.py --zone nanovia.ca
"""

from __future__ import annotations

import argparse
import os
import sys


def _build_records(vps_ip: str) -> list[dict[str, str]]:
    return [
        {"fieldType": "A", "subDomain": "", "target": vps_ip},
        {"fieldType": "A", "subDomain": "www", "target": vps_ip},
        {"fieldType": "A", "subDomain": "api", "target": vps_ip},
        {"fieldType": "A", "subDomain": "admin", "target": vps_ip},
        {"fieldType": "A", "subDomain": "monitor", "target": vps_ip},
        {"fieldType": "TXT", "subDomain": "", "target": f"v=spf1 ip4:{vps_ip} -all"},
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Configure OVH DNS for Nanovia.")
    parser.add_argument("--zone", default=os.getenv("APP_DOMAIN", "nanovia.ca"))
    parser.add_argument("--vps-ip", default=os.getenv("PUBLIC_IP", ""))
    parser.add_argument("--ttl", type=int, default=int(os.getenv("DNS_TTL", "300")))
    args = parser.parse_args()

    app_key = os.getenv("OVH_APP_KEY", "")
    app_secret = os.getenv("OVH_APP_SECRET", "")
    consumer_key = os.getenv("OVH_CONSUMER_KEY", "")

    if not app_key or not app_secret or not consumer_key:
        print("❌ Set OVH_APP_KEY, OVH_APP_SECRET and OVH_CONSUMER_KEY first.")
        print("   → https://ca.api.ovh.com/createToken/")
        return 1
    if not args.vps_ip:
        print("❌ Set PUBLIC_IP or pass --vps-ip before running this script.")
        return 1

    try:
        import ovh
    except ImportError:
        print("Installing ovh library...")
        import subprocess

        subprocess.check_call([sys.executable, "-m", "pip", "install", "ovh", "-q"])
        import ovh

    client = ovh.Client(
        endpoint="ovh-ca",
        application_key=app_key,
        application_secret=app_secret,
        consumer_key=consumer_key,
    )
    records = _build_records(args.vps_ip)

    print(f"[~] Fetching existing records for {args.zone}...")
    existing_ids = client.get(f"/domain/zone/{args.zone}/record")
    existing = [client.get(f"/domain/zone/{args.zone}/record/{rid}") for rid in existing_ids]

    added = 0
    skipped = 0

    for rec in records:
        already = any(
            e.get("fieldType") == rec["fieldType"]
            and e.get("subDomain") == rec["subDomain"]
            and e.get("target") == rec["target"]
            for e in existing
        )
        label = f"{rec['subDomain']}.{args.zone}" if rec["subDomain"] else args.zone
        if already:
            print(f"  ↷ SKIP  {rec['fieldType']:5s} {label} (already exists)")
            skipped += 1
            continue

        conflicts = [
            e["id"]
            for e in existing
            if e.get("fieldType") == rec["fieldType"] and e.get("subDomain") == rec["subDomain"]
        ]
        for cid in conflicts:
            client.delete(f"/domain/zone/{args.zone}/record/{cid}")
            print(f"  ✗ DELETED old record id={cid}")

        client.post(
            f"/domain/zone/{args.zone}/record",
            fieldType=rec["fieldType"],
            subDomain=rec["subDomain"],
            target=rec["target"],
            ttl=args.ttl,
        )
        print(f"  ✅ ADDED  {rec['fieldType']:5s} {label} → {rec['target']}")
        added += 1

    print("\n[~] Refreshing DNS zone...")
    client.post(f"/domain/zone/{args.zone}/refresh")
    print("[✅] Zone refreshed.")
    print(f"\n{'=' * 50}")
    print(f"Done. Added: {added}  Skipped: {skipped}")
    print("\nDNS propagation takes 1–15 min.")
    print(f"Test with: Resolve-DnsName {args.zone} -Type A")
    print(f"Or visit:  https://{args.zone}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
