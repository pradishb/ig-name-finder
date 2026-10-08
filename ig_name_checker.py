#!/usr/bin/env python3
"""
Instagram username variant checker.

Generates variants of a base name by stretching letters (no numbers), e.g.
  jade -> jaade, jaaade, jadde, jaaadddeee, ...
then checks which ones have no profile on Instagram. "available" here means
"no profile page": banned, deactivated and reserved names look the same, so
confirm in the Instagram app before counting on a name.

It loads each profile page (instagram.com/NAME/) with your login and looks for
a profile in it. Instagram only shows profiles to logged-in users, so pass your
own login cookie:
  python ig_name_checker.py jade --sessionid YOUR_SESSIONID
or set it once as an environment variable:
  Windows:  set IG_SESSIONID=YOUR_SESSIONID
  Mac/Linux: export IG_SESSIONID=YOUR_SESSIONID

How to get your sessionid (keep it private, it's like a password):
  1. Log in to instagram.com in Chrome/Edge.
  2. Press F12 -> Application tab -> Cookies -> https://www.instagram.com
  3. Copy the value of the cookie named "sessionid".

Other options:
  --vowels-only   only stretch vowels (jaade, jadee)
  --max-repeat 3  max times one letter repeats
  --max-extra 4   max extra letters added in total
  --dry-run       just list the variants
  --debug         print what Instagram sent back
  --delay 20      seconds between checks; going faster gets you rate limited

Finished names are remembered in checked.txt, so rerunning the same command
continues where it stopped.

Requires: pip install requests
"""

import argparse
import itertools
import os
import random
import re
import sys
import time

try:
    import requests
except ImportError:
    sys.exit("Missing dependency: run  pip install requests")

# The plain profile page. Instagram's JSON API (web_profile_info) answers 429 to
# scripts even when logged in, but the page itself loads fine with a login cookie.
PROFILE_URL = "https://www.instagram.com/{}/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    # Without these navigation headers Instagram serves the "no profile" page for every name
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Upgrade-Insecure-Requests": "1",
}
CONTROL_NAME = "instagram"  # always taken; if it ever looks free, results can't be trusted
CONTROL_EVERY = 10
PROFILE_MARKER = '"profile_id"'  # only in the page of a profile that exists
VALID = re.compile(r"^[a-z0-9._]{1,30}$")
VOWELS = set("aeiouy")


COOLDOWNS = [15 * 60, 30 * 60, 60 * 60]  # waits after each rate limit in a row, then give up


class NeedLogin(Exception):
    pass


class RateLimited(Exception):
    def __init__(self, retry_after=None):
        super().__init__("rate limited")
        self.retry_after = int(retry_after) if str(retry_after).isdigit() else 0


def generate_variants(base, max_repeat, max_extra, vowels_only):
    """Every way of repeating each letter 1..max_repeat times."""
    options = []
    for ch in base:
        stretchable = ch.isalpha() and (not vowels_only or ch in VOWELS)
        reps = range(1, max_repeat + 1) if stretchable else [1]
        options.append([ch * r for r in reps])

    seen, out = set(), []
    for combo in itertools.product(*options):
        name = "".join(combo)
        extra = len(name) - len(base)
        if name == base or name in seen or extra > max_extra or len(name) > 30:
            continue
        seen.add(name)
        out.append(name)
    out.sort(key=lambda n: (len(n), n))  # shortest first
    return out


def make_session(sessionid):
    s = requests.Session()
    s.headers.update(HEADERS)
    s.cookies.set("sessionid", sessionid, domain=".instagram.com")
    return s


def check(session, username, user_id, debug=False, retries=3):
    """Returns 'available', 'taken', or 'unknown (...)'."""
    status = "unknown"
    for attempt in range(retries):
        try:
            r = session.get(PROFILE_URL.format(username), timeout=20, allow_redirects=False)
        except requests.RequestException as e:
            status = f"unknown (network: {e.__class__.__name__})"
            time.sleep(5)
            continue

        if debug:
            print(f"   HTTP {r.status_code}, {len(r.text)} bytes, "
                  f"location={r.headers.get('Location', '')[:60]!r}")

        # Check this first: Instagram also sends the rate-limit message with a 401/403,
        # and retrying right away only makes the block last longer.
        if r.status_code == 429 or (r.status_code != 200 and "wait a few minutes" in r.text.lower()):
            raise RateLimited(r.headers.get("Retry-After"))
        if r.status_code == 404:
            return "available"
        if r.status_code == 200:
            if PROFILE_MARKER in r.text:
                return "taken"
            # Our own user id is in every page served to our login. Without it this is
            # the logged-out shell, which looks the same for taken and free names.
            if user_id in r.text:
                return "available"
            raise NeedLogin()
        # 401/403 or redirect to login = Instagram no longer accepts the sessionid
        if r.status_code in (401, 403) or (300 <= r.status_code < 400 and "login" in r.headers.get("Location", "")):
            raise NeedLogin()
        status = f"unknown (HTTP {r.status_code})"
        time.sleep(5)
    return status


def check_patiently(session, username, user_id, debug=False):
    """check(), but sits out rate limits. Returns None if Instagram never lets up."""
    for wait in COOLDOWNS + [None]:
        try:
            return check(session, username, user_id, debug)
        except RateLimited as e:
            if wait is None:
                return None
            wait = max(wait, e.retry_after)
            print(f"   rate limited, cooling down {wait // 60} min "
                  "(Ctrl+C to stop, progress is saved)...", flush=True)
            time.sleep(wait)


def load_checked(path):
    """Names already settled as available/taken in an earlier run."""
    try:
        with open(path, encoding="utf-8") as f:
            return {line.split("\t")[0] for line in f if line.strip()}
    except FileNotFoundError:
        return set()


def main():
    p = argparse.ArgumentParser(description="Check stretched Instagram username variants.")
    p.add_argument("name", help="base username, e.g. jade")
    p.add_argument("--max-repeat", type=int, default=3)
    p.add_argument("--max-extra", type=int, default=4)
    p.add_argument("--vowels-only", action="store_true")
    p.add_argument("--delay", type=float, default=20.0,
                   help="seconds between checks (default 20)")
    p.add_argument("--checked", default="checked.txt",
                   help="file remembering finished names so reruns skip them")
    p.add_argument("--include-base", action="store_true", help="also check the base name itself")
    p.add_argument("--sessionid", default=os.environ.get("IG_SESSIONID"),
                   help="your instagram.com 'sessionid' cookie (or set IG_SESSIONID)")
    p.add_argument("--debug", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--out", default="available.txt")
    a = p.parse_args()
    sys.stdout.reconfigure(errors="replace")  # the ✅/❌ marks can't be encoded when piped on Windows

    base = a.name.lower().strip().lstrip("@")
    if not VALID.match(base):
        sys.exit("Instagram usernames can only use a-z, 0-9, '.' and '_' (max 30 chars).")

    names = generate_variants(base, a.max_repeat, a.max_extra, a.vowels_only)
    if a.include_base:
        names.insert(0, base)

    print(f"{len(names)} variants for '{base}'")
    if a.dry_run:
        print("\n".join(names))
        return

    done = load_checked(a.checked)
    if done.intersection(names):
        names = [n for n in names if n not in done]
        print(f"Skipping names already in {a.checked}, {len(names)} left")

    if not a.sessionid:
        sys.exit(
            "Instagram only shows profiles to logged-in users. Run it with your sessionid cookie:\n"
            "  python ig_name_checker.py jade --sessionid YOUR_SESSIONID\n"
            "Get it from instagram.com: F12 -> Application -> Cookies -> www.instagram.com -> 'sessionid'."
        )
    # The sessionid starts with the account's numeric id: "<id>%3A..." (or "<id>:...")
    user_id = re.split(r"%3A|:", a.sessionid, maxsplit=1, flags=re.I)[0]
    session = make_session(a.sessionid)

    available = []
    try:
        for i, n in enumerate(names, 1):
            if (i - 1) % CONTROL_EVERY == 0:
                control = check_patiently(session, CONTROL_NAME, user_id, a.debug)
                if control is not None and control != "taken":
                    print(f"\nSelf-check failed: @{CONTROL_NAME} came back as '{control}', so Instagram "
                          "is not showing real profiles right now. Stopping; try again later.")
                    break
                time.sleep(a.delay + random.uniform(0, 2))
            else:
                control = "taken"
            result = control and check_patiently(session, n, user_id, a.debug)
            if result is None:
                print("\nStill rate limited after long waits, stopping. "
                      "Run the same command later to pick up where it left off.")
                break
            mark = "✅" if result == "available" else ("❌" if result == "taken" else "⚠️")
            print(f"[{i}/{len(names)}] {mark} {n:<30} {result}", flush=True)
            if result in ("available", "taken"):
                with open(a.checked, "a", encoding="utf-8") as f:
                    f.write(f"{n}\t{result}\n")
            if result == "available":
                available.append(n)
                with open(a.out, "a", encoding="utf-8") as f:
                    f.write(n + "\n")
            time.sleep(a.delay + random.uniform(0, 2))
    except NeedLogin:
        sys.exit(
            "\nInstagram is not treating this sessionid as logged in (expired or logged out).\n"
            "Copy a fresh one from instagram.com: F12 -> Application -> Cookies -> "
            "www.instagram.com -> 'sessionid'. Progress so far is saved."
        )
    except KeyboardInterrupt:
        print("\nStopped.")

    print(f"\nNo profile found, possibly free ({len(available)}):")
    print("\n".join(available) or "  none found")
    if available:
        print(f"Saved to {a.out}")
        print("Note: banned, deactivated and reserved names also have no profile page,\n"
              "so confirm a name in the Instagram app before counting on it.")


if __name__ == "__main__":
    main()
