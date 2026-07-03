#!/usr/bin/env python3
"""Generate a "coming soon" placeholder page for a platform whose event/metric
files aren't yet in the perfmon repository.

Usage: python scripts/build_stub.py <shortname> <out_path>

Reads perfmon/scripts/config/platform_config.json to pull the platform's
Name / Core / CoreType so the placeholder shows what we already know.
"""

import html
import json
import sys
from pathlib import Path


def _find_perfmon_config():
    """Locate platform_config.json — via PERFMON_DATA env var or ./perfmon."""
    import os
    root_candidates = []
    if os.environ.get("PERFMON_DATA"):
        root_candidates.append(Path(os.environ["PERFMON_DATA"]))
    root_candidates += [
        Path(__file__).resolve().parents[1] / "perfmon",
        Path.cwd() / "perfmon",
    ]
    for root in root_candidates:
        p = root / "scripts" / "config" / "platform_config.json"
        if p.exists():
            return p
    raise FileNotFoundError("platform_config.json not found under any known root")


def _load_platform(shortname: str) -> dict:
    p = _find_perfmon_config()
    with open(p) as f:
        entries = json.load(f)
    for e in entries:
        if e.get("ShortName") == shortname:
            return e
    raise KeyError(f"{shortname} not in platform_config.json")


PAGE_CSS = """
:root {
  --bg: #0f172a; --panel: #1e293b; --ink: #e2e8f0; --muted: #94a3b8;
  --accent: #38bdf8; --border: #334155; --mapped: #4ade80;
}
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; height: 100%; }
body {
  background: var(--bg); color: var(--ink);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  line-height: 1.55;
  display: flex; flex-direction: column; align-items: center;
  justify-content: flex-start; padding: 3rem 1.5rem;
}
main { max-width: 700px; width: 100%; }
h1 { margin: 0 0 0.5rem; font-size: 1.6rem; }
.meta { color: var(--muted); font-size: 0.9rem; margin-bottom: 0.5rem; }
.status {
  display: inline-block; margin: 0.5rem 0 1.5rem;
  padding: 0.25rem 0.65rem; border-radius: 12px;
  background: rgba(251, 191, 36, 0.15); color: #fbbf24;
  font-size: 0.75rem; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.08em;
}
.panel {
  background: var(--panel); border: 1px solid var(--border);
  border-radius: 8px; padding: 1.25rem 1.5rem;
  margin: 1rem 0;
}
.panel h2 {
  margin: 0 0 0.5rem; font-size: 1rem; color: var(--accent);
}
.panel dl { display: grid; grid-template-columns: 130px 1fr; gap: 0.35rem 1rem;
  margin: 0.5rem 0 0; font-size: 0.85rem; }
.panel dt { color: var(--muted); }
.panel dd { margin: 0; font-family: ui-monospace, monospace; }
.panel p { font-size: 0.85rem; color: var(--ink); margin: 0.35rem 0; }
.panel .muted { color: var(--muted); }
.back { color: var(--accent); text-decoration: none; font-size: 0.85rem; }
.back:hover { text-decoration: underline; }
"""


def build(shortname: str, out_path: Path) -> None:
    entry = _load_platform(shortname)
    name = entry.get("Name", shortname)
    core = entry.get("Core", "")
    core_type = entry.get("CoreType", "")
    is_hybrid = entry.get("IsHybrid", False)
    file_name = entry.get("FileName", "")

    core_info = " ".join(x for x in [core_type, core] if x).strip()

    payload = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{html.escape(name)} ({html.escape(shortname)}) — awaiting Intel data</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>{PAGE_CSS}</style>
</head>
<body>
<main>
  <a href="index.html" class="back">← back to platform list</a>
  <h1 style="margin-top:0.8rem;">{html.escape(name)} <span style="color:var(--muted);font-family:ui-monospace,monospace;font-size:0.9rem;">({html.escape(shortname)})</span></h1>
  <div class="meta">Codename registered by Intel in
    <code>platform_config.json</code>, event data not yet published upstream.
  </div>
  <span class="status">Awaiting upstream data</span>

  <div class="panel">
    <h2>What we know</h2>
    <dl>
      <dt>Short name</dt><dd>{html.escape(shortname)}</dd>
      <dt>Codename</dt><dd>{html.escape(name)}</dd>
      <dt>Core</dt><dd>{html.escape(core_info) if core_info else "<span class='muted'>—</span>"}</dd>
      {"<dt>Hybrid</dt><dd>Yes</dd>" if is_hybrid else ""}
      {f"<dt>File prefix</dt><dd>{html.escape(file_name)}</dd>" if file_name else ""}
    </dl>
  </div>

  <div class="panel">
    <h2>Why isn't the arch-map rendered yet?</h2>
    <p>Intel's <a class="back" href="https://github.com/intel/perfmon">perfmon</a> repository
    reserves this platform's shortname but does not yet contain event or
    metric JSON files for it. Once those files land upstream and this
    project's <code>perfmon</code> submodule is bumped, the arch-map for
    this platform will render automatically on the next Pages rebuild
    &mdash; assuming the classifier rules cover the core (see
    <code>src/perfmon_tools/core/arch_map.py</code> in the repo).</p>
    <p class="muted">Rebuild triggers: any push to <code>main</code>, or a manual
    dispatch of the "Deploy arch-map to GitHub Pages" workflow.</p>
  </div>

  <div class="panel">
    <h2>Coming from a supported platform?</h2>
    <p>Existing platforms:</p>
    <ul>
      <li><a class="back" href="gnr.html">Granite Rapids (GNR)</a> — P-core server, full TMA v5.1 tree.</li>
      <li><a class="back" href="cwf.html">Clearwater Forest (CWF)</a> — E-core server, TMA not yet published.</li>
    </ul>
  </div>
</main>
</body>
</html>
"""
    out_path.write_text(payload)
    print(f"Wrote {out_path} ({len(payload):,} bytes)")


def main(argv):
    if len(argv) != 3:
        print("usage: build_stub.py <shortname> <out_path>", file=sys.stderr)
        return 2
    build(argv[1], Path(argv[2]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
