#!/usr/bin/env python3
"""Write a landing index.html for the GitHub Pages site.

Usage: python scripts/build_index.py <out_dir>

<out_dir> should already contain gnr.html and cwf.html. The landing page
inspects each (best-effort) to pull out the event/metric counts embedded
in the ARCH payload, so the tile numbers stay accurate as new platforms
are added.
"""

import json
import re
import sys
from pathlib import Path


PLATFORMS = [
    {
        "file": "gnr.html",
        "short": "GNR",
        "name": "Granite Rapids",
        "tagline": "P-core server. Full 6-level TMA tree.",
    },
    {
        "file": "cwf.html",
        "short": "CWF",
        "name": "Clearwater Forest",
        "tagline": "E-core server. Category-grouped metrics (no TMA hierarchy).",
    },
]


def _extract_counts(html_path: Path) -> dict:
    """Best-effort parse of the ARCH payload embedded in a generated HTML.
    Returns {'events': int, 'metrics': int} — or empty if parsing fails."""
    try:
        text = html_path.read_text()
    except OSError:
        return {}
    m = re.search(r"const ARCH = (\{.*?\});</script>", text, re.DOTALL)
    if not m:
        return {}
    try:
        payload = json.loads(m.group(1))
    except json.JSONDecodeError:
        return {}
    return {
        "events": len(payload.get("events", {})),
        "metrics": len(payload.get("metrics", {})),
    }


INDEX_CSS = """
:root {
  --bg: #0f172a; --panel: #1e293b; --ink: #e2e8f0; --muted: #94a3b8;
  --accent: #38bdf8; --border: #334155;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--ink);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  line-height: 1.55;
  min-height: 100vh;
}
main { max-width: 900px; margin: 0 auto; padding: 3rem 1.5rem; }
h1 { font-size: 1.75rem; margin: 0 0 0.5rem; }
.subtitle { color: var(--muted); font-size: 1rem; max-width: 60ch; }
.repo-link { color: var(--accent); text-decoration: none; }
.repo-link:hover { text-decoration: underline; }
.tiles {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 1rem; margin: 2rem 0;
}
.tile {
  display: block; text-decoration: none; color: inherit;
  background: var(--panel); border: 1px solid var(--border); border-radius: 8px;
  padding: 1.25rem 1.4rem;
  transition: border-color 0.15s, transform 0.05s;
}
.tile:hover { border-color: var(--accent); transform: translateY(-1px); }
.tile h2 {
  margin: 0 0 0.25rem; font-size: 1.15rem; color: var(--accent);
  display: flex; align-items: baseline; gap: 0.6rem;
}
.tile h2 .short {
  font-family: ui-monospace, monospace; font-size: 0.75rem;
  color: var(--muted); font-weight: 500;
  background: rgba(148,163,184,0.15);
  padding: 0.05rem 0.5rem; border-radius: 10px;
}
.tile .tagline { color: var(--muted); font-size: 0.9rem; margin-bottom: 0.75rem; }
.tile .stats {
  display: flex; gap: 1.25rem; font-size: 0.82rem; color: var(--muted);
}
.tile .stats b { color: var(--ink); margin-right: 0.3rem; }
.about {
  margin-top: 2.5rem; padding-top: 1.5rem;
  border-top: 1px solid var(--border);
  font-size: 0.9rem; color: var(--muted);
}
.about b { color: var(--ink); }
.about ul { margin: 0.5rem 0; padding-left: 1.4rem; }
.about li { margin: 0.3rem 0; }
"""


def _tile_html(p: dict, counts: dict) -> str:
    parts = [f'<a class="tile" href="{p["file"]}">']
    parts.append(f'<h2>{p["name"]} <span class="short">{p["short"]}</span></h2>')
    parts.append(f'<div class="tagline">{p["tagline"]}</div>')
    stats_bits = []
    if counts.get("events") is not None:
        stats_bits.append(f'<div><b>{counts["events"]:,}</b>events</div>')
    if counts.get("metrics") is not None:
        stats_bits.append(f'<div><b>{counts["metrics"]}</b>metrics</div>')
    if stats_bits:
        parts.append('<div class="stats">' + "".join(stats_bits) + "</div>")
    parts.append("</a>")
    return "\n".join(parts)


def build(out_dir: Path) -> None:
    tiles = []
    for p in PLATFORMS:
        counts = _extract_counts(out_dir / p["file"])
        tiles.append(_tile_html(p, counts))

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>perfmon-skills — Architecture Event Map</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>{INDEX_CSS}</style>
</head>
<body>
<main>
  <h1>perfmon-skills — Architecture Event Map</h1>
  <p class="subtitle">
    Interactive uarch event browsers for Intel Xeon platforms. Every
    non-deprecated PMU event is classified into a four-level uarch hierarchy;
    every TMA metric is cross-linked to the events it consumes.
    Source and docs on <a class="repo-link" href="https://github.com/TianyouLi/perfmon-skills">GitHub</a>.
  </p>

  <div class="tiles">
    {chr(10).join(tiles)}
  </div>

  <div class="about">
    <b>Each page has two tabs:</b>
    <ul>
      <li><b>Events</b> — clickable SVG of the core pipeline and uncore/SoC. Every event
        lands in a labelled cell (Frontend / Backend / Memory / CHA / IMC / …).</li>
      <li><b>Metrics</b> — TMA hierarchy as a collapsible top-down tree (P-core parts),
        plus bottleneck aggregates and info metrics.</li>
    </ul>
    Click any event or metric on the left; the right column shows a description,
    acronym expansions, formula (for metrics), copy-paste perf snippets (for events),
    and cross-links to whichever tab is the counterpart.
  </div>
</main>
</body>
</html>
"""
    (out_dir / "index.html").write_text(html)
    print(f"Wrote {out_dir / 'index.html'}")


def main(argv):
    if len(argv) != 2:
        print("usage: build_index.py <out_dir>", file=sys.stderr)
        return 2
    out_dir = Path(argv[1])
    if not out_dir.is_dir():
        print(f"error: {out_dir} is not a directory", file=sys.stderr)
        return 1
    build(out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
