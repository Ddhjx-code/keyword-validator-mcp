#!/usr/bin/env python3
"""GA4 traffic report for these sites, excluding Direct traffic.

Direct traffic on these properties is overwhelmingly bots (8% engagement vs
59% for organic search, 1:1 session/user ratio, ~0s session duration), so the
raw totals are misleading. This reports the numbers with Direct stripped out.

Usage:
    python3 ga_traffic.py                 # last 7 days, all configured properties
    python3 ga_traffic.py --days 28
    python3 ga_traffic.py --start 2026-09-01 --end 2026-09-18
    python3 ga_traffic.py --properties 549933418
    python3 ga_traffic.py --keep-direct   # include Direct rows too
"""

from __future__ import annotations

import warnings

# requests checks its urllib3/chardet versions at import time and warns; the
# filter must therefore be installed before requests is imported below.
warnings.filterwarnings("ignore", message=".*doesn't match a supported version.*")

import argparse
import collections
import datetime as dt
import json
import os
import sys
import time

import jwt
import requests

TOKEN_URI = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/analytics.readonly"
API = "https://analyticsdata.googleapis.com/v1beta"

DEFAULT_KEY = "~/.config/gcp/ga-service-account.json"

DEFAULT_PROPERTIES = {
    "549933418": "expedition33.wiki + pbzero.wiki",
    "553562584": "morsecodenow.com",
}

DIRECT_SOURCES = {"(direct)"}
DIRECT_MEDIUMS = {"(none)"}
UNSET = "(not set)"


def get_access_token(key_path: str) -> str:
    sa = json.load(open(os.path.expanduser(key_path), encoding="utf-8"))
    now = int(time.time())
    assertion = jwt.encode(
        {
            "iss": sa["client_email"],
            "scope": SCOPE,
            "aud": sa.get("token_uri", TOKEN_URI),
            "iat": now,
            "exp": now + 3600,
        },
        sa["private_key"],
        algorithm="RS256",
    )
    resp = requests.post(
        sa.get("token_uri", TOKEN_URI),
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": assertion,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def run_report(token: str, property_id: str, body: dict) -> list[dict]:
    resp = requests.post(
        f"{API}/properties/{property_id}:runReport",
        headers={"Authorization": f"Bearer {token}"},
        json=body,
        timeout=60,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")
    rows = []
    for row in resp.json().get("rows", []):
        rows.append(
            {
                "dims": [v["value"] for v in row["dimensionValues"]],
                "mets": [v["value"] for v in row["metricValues"]],
            }
        )
    return rows


def is_direct(source: str, medium: str) -> bool:
    return source in DIRECT_SOURCES or medium in DIRECT_MEDIUMS


def report(token: str, pid: str, label: str, start: str, end: str, keep_direct: bool) -> None:
    print(f"\n{'=' * 76}")
    print(f"{label}   (property {pid})")
    print(f"{start} .. {end}")
    print("=" * 76)

    rows = run_report(
        token,
        pid,
        {
            "dateRanges": [{"startDate": start, "endDate": end}],
            "dimensions": [
                {"name": "hostName"},
                {"name": "sessionSource"},
                {"name": "sessionMedium"},
            ],
            "metrics": [
                {"name": "sessions"},
                {"name": "totalUsers"},
                {"name": "screenPageViews"},
                {"name": "engagedSessions"},
            ],
            "orderBys": [{"metric": {"metricName": "sessions"}, "desc": True}],
            "limit": 250,
        },
    )

    if not rows:
        print("  (no data in range)")
        return

    def tally(rs):
        acc = collections.Counter()
        for r in rs:
            acc["sessions"] += int(r["mets"][0])
            acc["users"] += int(r["mets"][1])
            acc["views"] += int(r["mets"][2])
            acc["engaged"] += int(r["mets"][3])
        return acc

    def bucket(r) -> str:
        source, medium = r["dims"][1], r["dims"][2]
        if is_direct(source, medium):
            return "direct"
        if source == UNSET or medium == UNSET:
            return "unset"
        return "attributed"

    attributed = [r for r in rows if bucket(r) == "attributed"]
    unset = [r for r in rows if bucket(r) == "unset"]
    direct = [r for r in rows if bucket(r) == "direct"]

    tot, at, un = tally(rows), tally(attributed), tally(unset)
    de = tally(direct)

    def pct_of_total(c: collections.Counter) -> float:
        return (c["sessions"] / tot["sessions"] * 100) if tot["sessions"] else 0.0

    print(f"  TOTAL       sessions={tot['sessions']:<6} users={tot['users']:<6} views={tot['views']}")
    print(
        f"  DIRECT      sessions={de['sessions']:<6} users={de['users']:<6} views={de['views']}"
        f"   ({pct_of_total(de):.1f}%)  <- excluded"
    )
    print(
        f"  UNSET       sessions={un['sessions']:<6} users={un['users']:<6} views={un['views']}"
        f"   ({pct_of_total(un):.1f}%)  <- attribution failed, not direct"
    )
    print(
        f"  ATTRIBUTED  sessions={at['sessions']:<6} users={at['users']:<6} views={at['views']}"
        f"   ({pct_of_total(at):.1f}%)  <- real, attributable traffic"
    )

    non_direct = attributed + unset

    print("\n  -- by host --")
    hosts = sorted(
        {r["dims"][0] for r in rows},
        key=lambda h: -sum(int(r["mets"][0]) for r in rows if r["dims"][0] == h),
    )
    for host in hosts:
        h_all = tally([r for r in rows if r["dims"][0] == host])
        h_nd = tally([r for r in non_direct if r["dims"][0] == host])
        print(
            f"    {host:<26} total={h_all['sessions']:<6} non-direct={h_nd['sessions']:<6} "
            f"users={h_nd['users']:<5} views={h_nd['views']}"
        )

    print("\n  -- attributed breakdown (source / medium) --")
    grouped: dict[tuple[str, str], collections.Counter] = collections.defaultdict(collections.Counter)
    for r in attributed:
        grouped[(r["dims"][1], r["dims"][2])].update(
            sessions=int(r["mets"][0]),
            users=int(r["mets"][1]),
            views=int(r["mets"][2]),
            engaged=int(r["mets"][3]),
        )
    if not grouped:
        print("    (none)")
    for (source, medium), c in sorted(grouped.items(), key=lambda kv: -kv[1]["sessions"]):
        print(
            f"    {source:<24} {medium:<14} sessions={c['sessions']:<5} "
            f"users={c['users']:<5} views={c['views']:<5} engaged={c['engaged']}"
        )

    print("\n  -- engagement by channel (bot check) --")
    ch = run_report(
        token,
        pid,
        {
            "dateRanges": [{"startDate": start, "endDate": end}],
            "dimensions": [{"name": "sessionDefaultChannelGroup"}],
            "metrics": [{"name": "sessions"}, {"name": "engagedSessions"}],
        },
    )
    for r in sorted(ch, key=lambda r: -int(r["mets"][0])):
        s, e = int(r["mets"][0]), int(r["mets"][1])
        rate = (e / s * 100) if s else 0.0
        print(f"    {r['dims'][0]:<26} sessions={s:<6} engaged={e:<6} ({rate:5.1f}%)")

    if keep_direct:
        print("\n  -- DIRECT rows (normally excluded) --")
        dg: dict[tuple[str, str], int] = collections.defaultdict(int)
        for r in direct:
            dg[(r["dims"][0], r["dims"][1])] += int(r["mets"][0])
        for (host, source), s in sorted(dg.items(), key=lambda kv: -kv[1]):
            print(f"    {host:<26} {source:<16} sessions={s}")


def main() -> int:
    ap = argparse.ArgumentParser(description="GA4 report excluding Direct traffic")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--start")
    ap.add_argument("--end")
    ap.add_argument("--properties", nargs="*", default=list(DEFAULT_PROPERTIES))
    ap.add_argument("--key", default=os.environ.get("GOOGLE_SERVICE_ACCOUNT_KEY", DEFAULT_KEY))
    ap.add_argument("--keep-direct", action="store_true", help="also print the excluded Direct rows")
    args = ap.parse_args()

    if args.start and args.end:
        start, end = args.start, args.end
    else:
        end = dt.date.today().isoformat()
        start = (dt.date.today() - dt.timedelta(days=args.days)).isoformat()

    key_path = os.path.expanduser(args.key)
    if not os.path.exists(key_path):
        print(f"service account key not found: {key_path}", file=sys.stderr)
        return 1

    try:
        token = get_access_token(key_path)
    except Exception as exc:
        print(f"auth failed: {exc}", file=sys.stderr)
        return 1

    for pid in args.properties:
        label = DEFAULT_PROPERTIES.get(pid, f"property {pid}")
        try:
            report(token, pid, label, start, end, args.keep_direct)
        except Exception as exc:
            print(f"\n{label} (property {pid})\n  ERROR: {exc}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
