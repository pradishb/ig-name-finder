# ig-name-finder

Finds Instagram usernames that look like a name you want by stretching its letters, then checks which of them have no profile.

```
jade -> jaade, jadee, jjade, jaaade, jaadee, ...
```

## How it works

For each variant the script loads `instagram.com/NAME/` with your login cookie and looks for profile data in the page. Instagram only shows profiles to logged-in users, so a `sessionid` is required.

## Setup

Needs Python 3 and [uv](https://docs.astral.sh/uv/).

```
git clone https://github.com/pradishb/ig-name-finder.git
cd ig-name-finder
uv venv
uv pip install requests
```

## Getting your sessionid

1. Log in to instagram.com in Chrome or Edge.
2. Press F12, open the Application tab, then Cookies, then `https://www.instagram.com`.
3. Copy the value of the cookie named `sessionid`.

The sessionid works like a password. Keep it private, and prefer a throwaway account: bulk lookups can get the account you use flagged.

## Usage

```
uv run ig_name_checker.py jade --sessionid YOUR_SESSIONID
```

Or set it once and leave the flag off:

```
$env:IG_SESSIONID = "YOUR_SESSIONID"     # PowerShell
export IG_SESSIONID=YOUR_SESSIONID       # macOS / Linux
```

| Option | Default | What it does |
|---|---|---|
| `--vowels-only` | off | Only stretch vowels (`jaade`, `jadee`) |
| `--max-repeat N` | 3 | Most times one letter may repeat |
| `--max-extra N` | 4 | Most extra letters added in total |
| `--include-base` | off | Also check the base name itself |
| `--delay SECONDS` | 20 | Pause between checks |
| `--dry-run` | off | List the variants without checking them |
| `--debug` | off | Print the status of each response |
| `--out FILE` | `available.txt` | Where names with no profile are saved |
| `--checked FILE` | `checked.txt` | Finished names, so a rerun skips them |

Use `--dry-run` first to see how many names a setting produces.

## Output

```
[1/4] ❌ jade                           taken
[2/4] ✅ jaade                          available
[3/4] ✅ jadee                          available
[4/4] ❌ jaadee                         taken
```

Names with no profile are appended to `available.txt`. Every finished name goes into `checked.txt`, so running the same command again continues where it stopped.

## Limits

- **"available" means "no profile page".** Banned, deactivated and reserved names look exactly the same, and short names are often one of those. Confirm a name in the Instagram app before counting on it.
- **Rate limits.** If Instagram starts refusing requests the script waits 15, 30, then 60 minutes and then stops. Lowering `--delay` makes this more likely.
- **Self-check.** The script checks `@instagram` before starting and every 10 names. If that ever looks free, Instagram is not serving real profiles and the script stops instead of reporting wrong results.
- **It can break.** It depends on how Instagram's pages look today and is not an official API.
