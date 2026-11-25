#!/usr/bin/env python3
"""
Self-hosted Pixel Studio GitHub Profile SVG generator.
Uses only the Python 3 standard library.
Fetches live GitHub stats/repos/commits and Phnom Penh weather via Open-Meteo,
then renders SVG cards into ./assets/.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import html
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

USERNAME = os.environ.get("GITHUB_USERNAME", "thegeostar")
DISPLAY_NAME = os.environ.get("PROFILE_NAME", "Eng Dararoth")
BIO_OVERRIDE = os.environ.get(
    "PROFILE_BIO", "Python developer. Working on ml-math right now."
)
LOCATION = os.environ.get("PROFILE_LOCATION", "Phnom Penh, Cambodia")
LATITUDE = float(os.environ.get("WEATHER_LAT", "11.5564"))
LONGITUDE = float(os.environ.get("WEATHER_LON", "104.9282"))
TIMEZONE_OFFSET_HOURS = int(os.environ.get("TZ_OFFSET_HOURS", "7"))
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()

ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT / "assets"

LANG_COLORS = {
    "Python": "#3572A5",
    "JavaScript": "#f1e05a",
    "TypeScript": "#3178c6",
    "HTML": "#e34c26",
    "CSS": "#563d7c",
    "SCSS": "#c6538c",
    "Rust": "#dea584",
    "Go": "#00ADD8",
    "C": "#555555",
    "C++": "#f34b7d",
    "Java": "#b07219",
    "Shell": "#89e051",
    "Jupyter Notebook": "#DA5B0B",
}

PROJECT_PALETTES = [
    ("#ff4d4f", "#c92a2a", "#3d1417"),  # Red
    ("#4dabf7", "#1c7ed6", "#13293d"),  # Blue
    ("#ffd43b", "#e6a800", "#3a2e0d"),  # Yellow
    ("#f06595", "#c2255c", "#3b1427"),  # Pink
]


def http_json(url: str, headers: dict[str, str] | None = None, data: bytes | None = None):
    req_headers = {"User-Agent": f"{USERNAME}-profile-generator"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, data=data, headers=req_headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_bytes(url: str) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": f"{USERNAME}-profile-generator"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read()
    except Exception:
        return None


def fetch_github_rest() -> dict:
    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

    user = http_json(f"https://api.github.com/users/{USERNAME}", headers)
    repos = http_json(
        f"https://api.github.com/users/{USERNAME}/repos?sort=updated&per_page=10",
        headers,
    )
    events = []
    try:
        events = http_json(
            f"https://api.github.com/users/{USERNAME}/events/public?per_page=30",
            headers,
        )
    except Exception:
        events = []

    commits: list[str] = []
    for ev in events:
        if ev.get("type") == "PushEvent":
            repo_short = ev.get("repo", {}).get("name", "").split("/")[-1]
            for c in ev.get("payload", {}).get("commits", []):
                msg = (c.get("message") or "").splitlines()[0].strip()
                if msg:
                    commits.append(f"{repo_short}: {msg}")

    if not commits:
        for repo in repos[:4]:
            rname = repo["name"]
            try:
                rcommits = http_json(
                    f"https://api.github.com/repos/{USERNAME}/{rname}/commits?per_page=3",
                    headers,
                )
                for rc in rcommits:
                    msg = (rc.get("commit", {}).get("message") or "").splitlines()[0].strip()
                    if msg:
                        commits.append(f"{rname}: {msg}")
            except Exception:
                pass

    if not commits:
        commits = [
            "ml-math: add matrix visualization",
            "oceaneye: update python pipeline",
            "the-book: refine layout modules",
            "e-commerce: style storefront cards",
        ]

    return {"user": user, "repos": repos, "commits": commits[:8]}


def fetch_github_graphql() -> dict | None:
    if not GITHUB_TOKEN:
        return None
    query = """
    query($login: String!) {
      user(login: $login) {
        contributionsCollection {
          totalCommitContributions
          totalPullRequestContributions
          contributionCalendar {
            totalContributions
            weeks {
              contributionDays {
                date
                contributionCount
              }
            }
          }
        }
      }
    }
    """
    payload = json.dumps({"query": query, "variables": {"login": USERNAME}}).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Content-Type": "application/json",
    }
    try:
        res = http_json("https://api.github.com/graphql", headers=headers, data=payload)
        return res.get("data", {}).get("user", {}).get("contributionsCollection")
    except Exception:
        return None


def compute_streaks(days: list[dict]) -> tuple[int, int]:
    best = 0
    cur = 0
    for d in days:
        if d.get("contributionCount", 0) > 0:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    # Current streak: count backwards from today (or yesterday if today is 0)
    current = 0
    idx = len(days) - 1
    if idx >= 0 and days[idx].get("contributionCount", 0) == 0:
        idx -= 1
    while idx >= 0 and days[idx].get("contributionCount", 0) > 0:
        current += 1
        idx -= 1
    return current, best


def fetch_weather() -> dict:
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={LATITUDE}&longitude={LONGITUDE}"
        f"&current=temperature_2m,weather_code,is_day"
        f"&timezone=Asia%2FBangkok"
    )
    try:
        data = http_json(url)
        cur = data.get("current", {})
        return {
            "temp": round(float(cur.get("temperature_2m", 30))),
            "code": int(cur.get("weather_code", 1)),
            "is_day": bool(cur.get("is_day", 1)),
        }
    except Exception:
        now_local = dt.datetime.now(dt.timezone(dt.timedelta(hours=TIMEZONE_OFFSET_HOURS)))
        return {"temp": 30, "code": 1, "is_day": 6 <= now_local.hour < 18}


def weather_label(code: int) -> str:
    if code == 0:
        return "Clear"
    if code in (1, 2, 3):
        return "Partly Cloudy"
    if code in (45, 48):
        return "Foggy"
    if code in (51, 53, 55, 61, 63, 65, 80, 81, 82):
        return "Rain"
    if code in (95, 96, 99):
        return "Thunderstorm"
    return "Cloudy"


def escape(text: str) -> str:
    return html.escape(text, quote=True)


def truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def render_hero_studio(commits: list[str], languages: list[str], weather: dict) -> str:
    now_local = dt.datetime.now(dt.timezone(dt.timedelta(hours=TIMEZONE_OFFSET_HOURS)))
    hour_angle = ((now_local.hour % 12) + now_local.minute / 60.0) * 30.0
    minute_angle = now_local.minute * 6.0

    is_day = weather["is_day"]
    wcode = weather["code"]
    is_rain = wcode in (51, 53, 55, 61, 63, 65, 80, 81, 82, 95, 96, 99)
    is_cloudy = wcode in (1, 2, 3, 45, 48) or is_rain

    sky_top = "#5899d6" if is_day else "#101935"
    sky_bot = "#9cc7ec" if is_day else "#1d2d57"
    if is_rain and is_day:
        sky_top = "#495c70"
        sky_bot = "#72879c"

    # Window contents
    window_elements = [
        f'<rect x="52" y="54" width="166" height="122" fill="url(#skyGrad)"/>',
    ]
    if is_day and not is_rain:
        window_elements.append('<rect x="174" y="68" width="24" height="24" fill="#ffd43b"/>')
        window_elements.append('<rect x="178" y="72" width="16" height="16" fill="#fff3bf"/>')
    elif not is_day:
        window_elements.append('<rect x="178" y="68" width="18" height="18" fill="#f8f9fa"/>')
        window_elements.append('<rect x="184" y="68" width="12" height="12" fill="#101935"/>')
        for sx, sy in [(72, 70), (96, 84), (132, 66), (154, 90), (84, 110), (144, 118)]:
            window_elements.append(f'<rect x="{sx}" y="{sy}" width="4" height="4" fill="#fff3bf" opacity="0.85"/>')

    if is_cloudy:
        cloud_color = "#e9ecef" if is_day and not is_rain else "#adb5bd"
        window_elements.append(
            f'<g class="cloud-drift" fill="{cloud_color}">'
            '<rect x="66" y="88" width="44" height="14"/>'
            '<rect x="74" y="80" width="26" height="10"/>'
            '<rect x="130" y="108" width="52" height="14"/>'
            '<rect x="140" y="100" width="30" height="10"/>'
            "</g>"
        )
    if is_rain:
        for rx, ry in [(74, 110), (96, 124), (120, 114), (146, 128), (168, 116), (192, 126)]:
            window_elements.append(
                f'<rect class="rain-drop" x="{rx}" y="{ry}" width="3" height="12" fill="#a5d8ff" opacity="0.8"/>'
            )

    # Bookshelf books (one book per language)
    langs = languages or ["Python", "HTML", "JavaScript", "SCSS"]
    books_svg = []
    bx = 636
    heights = [38, 34, 40, 32, 36, 38]
    for i, lang in enumerate(langs[:6]):
        color = LANG_COLORS.get(lang, "#74c0fc")
        bh = heights[i % len(heights)]
        by = 166 - bh
        books_svg.append(
            f'<rect x="{bx}" y="{by}" width="16" height="{bh}" fill="{color}"/>'
            f'<rect x="{bx + 3}" y="{by + 6}" width="10" height="3" fill="#ffffff" opacity="0.35"/>'
        )
        bx += 20

    # Monitor scrolling commits
    commit_lines = commits + commits  # duplicate for seamless scroll
    monitor_text = []
    y_pos = 14
    for line in commit_lines[:12]:
        safe_line = escape(truncate(line, 34))
        monitor_text.append(
            f'<text x="8" y="{y_pos}" fill="#7ee787" font-size="9.5" '
            f'font-family="ui-monospace, SFMono-Regular, Menlo, monospace">&gt; {safe_line}</text>'
        )
        y_pos += 14

    sign_text = escape(DISPLAY_NAME.upper())
    temp_str = f"{weather['temp']}°C · {weather_label(wcode)}"

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="840" height="340" viewBox="0 0 840 340" role="img" aria-label="Pixel Studio desk banner for {escape(DISPLAY_NAME)}">
  <defs>
    <linearGradient id="skyGrad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="{sky_top}"/>
      <stop offset="100%" stop-color="{sky_bot}"/>
    </linearGradient>
    <linearGradient id="wallGrad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#1a2234"/>
      <stop offset="100%" stop-color="#141b29"/>
    </linearGradient>
    <clipPath id="monitorClip">
      <rect x="314" y="122" width="212" height="96" rx="2"/>
    </clipPath>
    <clipPath id="windowClip">
      <rect x="52" y="54" width="166" height="122"/>
    </clipPath>
  </defs>
  <style>
    .commit-scroll {{
      animation: scrollUp 14s linear infinite;
    }}
    @keyframes scrollUp {{
      0% {{ transform: translateY(0px); }}
      100% {{ transform: translateY(-84px); }}
    }}
    .cloud-drift {{
      animation: drift 16s ease-in-out infinite alternate;
    }}
    @keyframes drift {{
      0% {{ transform: translateX(-6px); }}
      100% {{ transform: translateX(8px); }}
    }}
    .rain-drop {{
      animation: rainFall 1.1s linear infinite;
    }}
    @keyframes rainFall {{
      0% {{ transform: translateY(-10px); opacity: 0.9; }}
      100% {{ transform: translateY(30px); opacity: 0.1; }}
    }}
    .cat-breathe {{
      animation: breathe 3.2s ease-in-out infinite;
      transform-origin: 676px 286px;
    }}
    @keyframes breathe {{
      0%, 100% {{ transform: scaleY(1); }}
      50% {{ transform: scaleY(1.06); }}
    }}
    .steam {{
      animation: steamRise 2.6s ease-in-out infinite;
    }}
    @keyframes steamRise {{
      0% {{ transform: translateY(4px); opacity: 0.0; }}
      50% {{ opacity: 0.55; }}
      100% {{ transform: translateY(-10px); opacity: 0.0; }}
    }}
  </style>

  <!-- Room backdrop -->
  <rect width="840" height="340" rx="12" fill="url(#wallGrad)"/>
  <!-- Floor -->
  <rect x="0" y="274" width="840" height="66" fill="#2c221b"/>
  <rect x="0" y="274" width="840" height="6" fill="#3d2f24"/>
  <!-- Baseboard -->
  <rect x="0" y="266" width="840" height="8" fill="#1e273a"/>

  <!-- Window -->
  <g clip-path="url(#windowClip)">
    {"".join(window_elements)}
  </g>
  <!-- Window frame & mullions -->
  <rect x="46" y="48" width="178" height="134" fill="none" stroke="#2d3952" stroke-width="12"/>
  <rect x="132" y="54" width="8" height="122" fill="#2d3952"/>
  <rect x="52" y="112" width="166" height="8" fill="#2d3952"/>
  <rect x="40" y="182" width="190" height="10" fill="#3a4966"/>
  <text x="135" y="206" text-anchor="middle" fill="#8b949e" font-size="10" font-family="ui-monospace, SFMono-Regular, Menlo, monospace">{escape(temp_str)}</text>

  <!-- Nameplate sign -->
  <rect x="276" y="42" width="288" height="44" rx="4" fill="#0d1117" stroke="#3b4c6b" stroke-width="3"/>
  <rect x="282" y="48" width="276" height="32" rx="2" fill="#161f30"/>
  <text x="420" y="70" text-anchor="middle" fill="#e6edf3" font-size="20" font-weight="700" letter-spacing="4" font-family="ui-monospace, SFMono-Regular, Menlo, monospace">{sign_text}</text>

  <!-- Wall clock -->
  <circle cx="710" cy="70" r="24" fill="#f1f3f5" stroke="#3b4c6b" stroke-width="5"/>
  <line x1="710" y1="70" x2="710" y2="56" stroke="#1f2937" stroke-width="3" stroke-linecap="round" transform="rotate({hour_angle:.1f} 710 70)"/>
  <line x1="710" y1="70" x2="710" y2="52" stroke="#374151" stroke-width="2" stroke-linecap="round" transform="rotate({minute_angle:.1f} 710 70)"/>
  <circle cx="710" cy="70" r="3" fill="#e03131"/>

  <!-- Bookshelf -->
  <rect x="616" y="166" width="168" height="10" fill="#5c4033"/>
  <rect x="626" y="176" width="10" height="14" fill="#422d23"/>
  <rect x="764" y="176" width="10" height="14" fill="#422d23"/>
  {"".join(books_svg)}

  <!-- Lower shelf -->
  <rect x="616" y="218" width="168" height="10" fill="#5c4033"/>
  <rect x="626" y="228" width="10" height="12" fill="#422d23"/>
  <rect x="764" y="228" width="10" height="12" fill="#422d23"/>

  <!-- Desk -->
  <rect x="256" y="238" width="328" height="16" fill="#6e472b"/>
  <rect x="256" y="254" width="328" height="6" fill="#52331d"/>
  <!-- Desk legs -->
  <rect x="270" y="260" width="16" height="54" fill="#52331d"/>
  <rect x="554" y="260" width="16" height="54" fill="#52331d"/>

  <!-- Desk lamp -->
  <rect x="278" y="232" width="26" height="6" fill="#3d495c"/>
  <rect x="288" y="176" width="6" height="56" fill="#4d5c75"/>
  <rect x="278" y="166" width="34" height="14" fill="#f59f00"/>
  <polygon points="278,180 312,180 330,238 264,238" fill="#ffd43b" opacity="0.10"/>

  <!-- Monitor -->
  <rect x="304" y="112" width="232" height="114" rx="6" fill="#2b3445" stroke="#45536b" stroke-width="3"/>
  <rect x="314" y="122" width="212" height="96" rx="2" fill="#0d1117"/>
  <!-- Monitor stand -->
  <rect x="404" y="226" width="32" height="12" fill="#2b3445"/>
  <rect x="386" y="234" width="68" height="6" fill="#3d495c"/>
  <!-- Scrolling commits inside monitor -->
  <g clip-path="url(#monitorClip)">
    <g transform="translate(314, 122)">
      <g class="commit-scroll">
        {"".join(monitor_text)}
      </g>
    </g>
  </g>

  <!-- Coffee mug + steam -->
  <rect x="548" y="218" width="18" height="20" rx="2" fill="#f1f3f5"/>
  <rect x="566" y="222" width="6" height="10" fill="none" stroke="#f1f3f5" stroke-width="3"/>
  <g class="steam" fill="#ced4da">
    <rect x="552" y="206" width="3" height="8"/>
    <rect x="559" y="202" width="3" height="10"/>
  </g>

  <!-- Chair (behind desk front) -->
  <rect x="400" y="260" width="40" height="8" fill="#2b3445"/>
  <rect x="416" y="268" width="8" height="36" fill="#3d495c"/>
  <rect x="396" y="302" width="48" height="6" fill="#2b3445"/>

  <!-- Potted plant -->
  <rect x="122" y="250" width="36" height="28" fill="#b85d3b"/>
  <rect x="118" y="244" width="44" height="8" fill="#cf6e48"/>
  <rect x="136" y="216" width="8" height="28" fill="#2f9e44"/>
  <rect x="120" y="224" width="16" height="10" fill="#40c057"/>
  <rect x="144" y="218" width="18" height="10" fill="#40c057"/>
  <rect x="126" y="206" width="20" height="10" fill="#51cf66"/>

  <!-- Sleeping pixel cat -->
  <g class="cat-breathe">
    <rect x="652" y="274" width="42" height="18" rx="4" fill="#e69b4c"/>
    <rect x="688" y="268" width="20" height="20" rx="3" fill="#e69b4c"/>
    <!-- Ears -->
    <rect x="690" y="262" width="6" height="6" fill="#e69b4c"/>
    <rect x="700" y="262" width="6" height="6" fill="#e69b4c"/>
    <!-- Closed eyes -->
    <rect x="693" y="276" width="4" height="2" fill="#2c221b"/>
    <rect x="701" y="276" width="4" height="2" fill="#2c221b"/>
    <!-- Stripes & tail -->
    <rect x="662" y="274" width="5" height="8" fill="#c77b2e"/>
    <rect x="674" y="274" width="5" height="8" fill="#c77b2e"/>
    <rect x="636" y="284" width="18" height="6" rx="2" fill="#e69b4c"/>
  </g>
</svg>
'''


def render_about_card(user: dict, total_stars: int, avatar_b64: str | None) -> str:
    name = escape(user.get("name") or DISPLAY_NAME)
    bio = escape(user.get("bio") or BIO_OVERRIDE)
    location = escape(user.get("location") or LOCATION)
    followers = int(user.get("followers") or 0)
    repos = int(user.get("public_repos") or 0)

    avatar_markup = ""
    if avatar_b64:
        avatar_markup = (
            '<rect x="712" y="24" width="96" height="96" rx="10" fill="#21262d" stroke="#30363d" stroke-width="2"/>'
            '<clipPath id="avatarClip"><rect x="716" y="28" width="88" height="88" rx="8"/></clipPath>'
            f'<image href="data:image/png;base64,{avatar_b64}" x="716" y="28" width="88" height="88" clip-path="url(#avatarClip)"/>'
        )

    meta = f"{location}  ·  {followers} followers  ·  {repos} repositories  ·  {total_stars} ★ stars"

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="840" height="148" viewBox="0 0 840 148" role="img" aria-label="About {name}">
  <rect x="0.5" y="0.5" width="839" height="147" rx="10" fill="#161b22" stroke="#30363d"/>
  <text x="28" y="36" fill="#3fb950" font-size="13" font-weight="700" letter-spacing="1.5" font-family="ui-monospace, SFMono-Regular, Menlo, monospace">&gt; ABOUT</text>
  <text x="28" y="68" fill="#e6edf3" font-size="22" font-weight="700" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif">{name}</text>
  <text x="28" y="96" fill="#c9d1d9" font-size="14" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif">{bio}</text>
  <text x="28" y="124" fill="#8b949e" font-size="12.5" font-family="ui-monospace, SFMono-Regular, Menlo, monospace">{escape(meta)}</text>
  {avatar_markup}
</svg>
'''


def render_stats_bar(commits: int, prs: int, stars: int, best_streak: int) -> str:
    items = [
        (str(commits), "COMMITS"),
        (str(prs), "PULL REQS"),
        (str(stars), "STARS"),
        (str(best_streak), "BEST STREAK"),
    ]
    cols = []
    col_w = 840 // 4
    for idx, (val, label) in enumerate(items):
        x = idx * col_w + 28
        divider = (
            f'<line x1="{idx * col_w}" y1="18" x2="{idx * col_w}" y2="70" stroke="#30363d" stroke-width="1"/>'
            if idx > 0
            else ""
        )
        cols.append(
            f"{divider}"
            f'<text x="{x}" y="42" fill="#e6edf3" font-size="24" font-weight="700" font-family="ui-monospace, SFMono-Regular, Menlo, monospace">{escape(val)}</text>'
            f'<text x="{x}" y="64" fill="#8b949e" font-size="11" letter-spacing="1.2" font-family="ui-monospace, SFMono-Regular, Menlo, monospace">{escape(label)}</text>'
        )

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="840" height="88" viewBox="0 0 840 88" role="img" aria-label="GitHub Stats">
  <rect x="0.5" y="0.5" width="839" height="87" rx="10" fill="#161b22" stroke="#30363d"/>
  {"".join(cols)}
</svg>
'''


def pixel_sprite_svg(seed_text: str, primary: str, secondary: str, bg: str) -> str:
    digest = hashlib.sha256(seed_text.encode("utf-8")).digest()
    cells = [f'<rect x="18" y="22" width="60" height="60" rx="8" fill="{bg}" stroke="{secondary}" stroke-width="1.5"/>']
    # 5x5 symmetric pixel identicon
    cell_size = 8
    origin_x = 28
    origin_y = 32
    bit_idx = 0
    for row in range(5):
        for col in range(3):
            byte_val = digest[bit_idx % len(digest)]
            bit_idx += 1
            if byte_val % 2 == 0:
                color = primary if (byte_val % 4 == 0) else secondary
                x1 = origin_x + col * cell_size
                y1 = origin_y + row * cell_size
                cells.append(f'<rect x="{x1}" y="{y1}" width="{cell_size}" height="{cell_size}" fill="{color}"/>')
                mirror_col = 4 - col
                if mirror_col != col:
                    x2 = origin_x + mirror_col * cell_size
                    cells.append(f'<rect x="{x2}" y="{y1}" width="{cell_size}" height="{cell_size}" fill="{color}"/>')
    return "".join(cells)


def render_project_card(repo: dict, palette_idx: int) -> str:
    primary, secondary, bg = PROJECT_PALETTES[palette_idx % len(PROJECT_PALETTES)]
    name = escape(repo.get("name", "project"))
    desc = escape(truncate(repo.get("description") or "A project in progress.", 42))
    lang = repo.get("language") or "Code"
    lang_color = LANG_COLORS.get(lang, "#8b949e")
    stars = int(repo.get("stargazers_count") or 0)
    forks = int(repo.get("forks_count") or 0)

    sprite = pixel_sprite_svg(name, primary, secondary, bg)

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="412" height="114" viewBox="0 0 412 114" role="img" aria-label="Project {name}">
  <rect x="0.5" y="0.5" width="411" height="113" rx="10" fill="#161b22" stroke="#30363d"/>
  {sprite}
  <text x="94" y="38" fill="#e6edf3" font-size="16" font-weight="700" font-family="ui-monospace, SFMono-Regular, Menlo, monospace">{name}</text>
  <text x="94" y="60" fill="#8b949e" font-size="12.5" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif">{desc}</text>
  <text x="94" y="92" fill="#8b949e" font-size="12" font-family="ui-monospace, SFMono-Regular, Menlo, monospace">★ {stars}   ⑂ {forks}</text>
  <circle cx="304" cy="88" r="5" fill="{lang_color}"/>
  <text x="315" y="92" fill="#c9d1d9" font-size="12" font-family="ui-monospace, SFMono-Regular, Menlo, monospace">{escape(lang)}</text>
</svg>
'''


def render_activity_card(
    days: list[dict], current_streak: int, best_streak: int, year_total: int
) -> str:
    # Show last 26 weeks (182 days) in a 26x7 grid
    grid_days = days[-182:] if days else []
    while len(grid_days) < 182:
        grid_days.insert(0, {"contributionCount": 0})

    level_colors = ["#1b222c", "#0e4429", "#006d32", "#26a641", "#39d353"]
    rects = []
    start_x = 28
    start_y = 54
    cell = 13
    gap = 4

    for idx, d in enumerate(grid_days):
        count = int(d.get("contributionCount", 0))
        if count <= 0:
            lvl = 0
        elif count <= 2:
            lvl = 1
        elif count <= 5:
            lvl = 2
        elif count <= 9:
            lvl = 3
        else:
            lvl = 4
        week = idx // 7
        dow = idx % 7
        x = start_x + week * (cell + gap)
        y = start_y + dow * (cell + gap)
        rects.append(
            f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2.5" fill="{level_colors[lvl]}"/>'
        )

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="840" height="196" viewBox="0 0 840 196" role="img" aria-label="GitHub Activity">
  <rect x="0.5" y="0.5" width="839" height="195" rx="10" fill="#161b22" stroke="#30363d"/>
  <text x="28" y="34" fill="#3fb950" font-size="13" font-weight="700" letter-spacing="1.5" font-family="ui-monospace, SFMono-Regular, Menlo, monospace">&gt; ACTIVITY</text>
  {"".join(rects)}
  <line x1="504" y1="48" x2="504" y2="170" stroke="#30363d" stroke-width="1"/>
  <text x="532" y="68" fill="#8b949e" font-size="10.5" letter-spacing="1.2" font-family="ui-monospace, SFMono-Regular, Menlo, monospace">CURRENT STREAK</text>
  <text x="532" y="88" fill="#e6edf3" font-size="18" font-weight="700" font-family="ui-monospace, SFMono-Regular, Menlo, monospace">{current_streak} days</text>
  <text x="532" y="114" fill="#8b949e" font-size="10.5" letter-spacing="1.2" font-family="ui-monospace, SFMono-Regular, Menlo, monospace">BEST STREAK</text>
  <text x="532" y="134" fill="#e6edf3" font-size="18" font-weight="700" font-family="ui-monospace, SFMono-Regular, Menlo, monospace">{best_streak} days</text>
  <text x="532" y="160" fill="#8b949e" font-size="10.5" letter-spacing="1.2" font-family="ui-monospace, SFMono-Regular, Menlo, monospace">THIS YEAR</text>
  <text x="532" y="180" fill="#e6edf3" font-size="18" font-weight="700" font-family="ui-monospace, SFMono-Regular, Menlo, monospace">{year_total}</text>
</svg>
'''


def main() -> None:
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    rest = fetch_github_rest()
    user = rest["user"]
    repos = rest["repos"]
    commits = rest["commits"]
    weather = fetch_weather()

    # Order preferred featured repos if present
    preferred = ["ml-math", "oceaneye", "the-book", "e-commerce"]
    repo_map = {r["name"]: r for r in repos if isinstance(r, dict)}
    featured = [repo_map[n] for n in preferred if n in repo_map]
    for r in repos:
        if len(featured) >= 4:
            break
        if isinstance(r, dict) and r["name"] not in {f["name"] for f in featured}:
            featured.append(r)

    total_stars = sum(int(r.get("stargazers_count") or 0) for r in repos if isinstance(r, dict))
    languages = []
    for r in repos:
        lang = r.get("language") if isinstance(r, dict) else None
        if lang and lang not in languages:
            languages.append(lang)

    gql = fetch_github_graphql()
    if gql:
        cal = gql.get("contributionCalendar", {})
        all_days = [
            d
            for w in cal.get("weeks", [])
            for d in w.get("contributionDays", [])
        ]
        current_streak, best_streak = compute_streaks(all_days)
        total_commits = int(gql.get("totalCommitContributions") or 0)
        total_prs = int(gql.get("totalPullRequestContributions") or 0)
        year_total = int(cal.get("totalContributions") or 0)
    else:
        # Fallback when running locally without GITHUB_TOKEN
        all_days = []
        for i in range(182):
            seed = (i * 37 + 13) % 19
            cnt = 0 if seed < 12 else (seed - 11)
            all_days.append({"contributionCount": cnt})
        current_streak, best_streak = 0, 5
        total_commits = 23
        total_prs = 0
        year_total = 92

    avatar_bytes = http_bytes(user.get("avatar_url", ""))
    avatar_b64 = base64.b64encode(avatar_bytes).decode("ascii") if avatar_bytes else None

    (ASSETS_DIR / "hero-studio.svg").write_text(
        render_hero_studio(commits, languages, weather), encoding="utf-8"
    )
    (ASSETS_DIR / "about-card.svg").write_text(
        render_about_card(user, total_stars, avatar_b64), encoding="utf-8"
    )
    (ASSETS_DIR / "stats-bar.svg").write_text(
        render_stats_bar(total_commits, total_prs, total_stars, best_streak),
        encoding="utf-8",
    )
    for idx, repo in enumerate(featured[:4], start=1):
        (ASSETS_DIR / f"project-{idx}.svg").write_text(
            render_project_card(repo, idx - 1), encoding="utf-8"
        )
    (ASSETS_DIR / "activity-card.svg").write_text(
        render_activity_card(all_days, current_streak, best_streak, year_total),
        encoding="utf-8",
    )

    print(f"Generated SVGs in {ASSETS_DIR}")


if __name__ == "__main__":
    main()
