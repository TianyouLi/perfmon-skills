"""Render an ArchMap as a self-contained interactive HTML page.

Layout (2 columns):
  LEFT  (sticky): SVG uarch diagram. Every cell and subcomponent is a
                  clickable box (data-cell / data-sub attribute).
  RIGHT: top    = event list for the currently selected component.
         bottom = full description of the currently selected event.

Event catalog is embedded as JSON so the whole page is self-contained. Small
inline JS handles selection state; no external dependencies.
"""

import html
import json
from typing import Optional

from ..core.arch_map import ArchMap, Cell, SubComponent
from ..core.catalog import PlatformCatalog
from ..core.formula import expand_formula
from ..core.glossary import find_acronyms, get_pseudo_event, note_for_path
from ..core.tma_tree import TmaTree
from .perf_examples import build_examples


PAGE_CSS = """
:root {
  --bg: #0f172a;
  --panel: #1e293b;
  --ink: #e2e8f0;
  --muted: #94a3b8;
  --accent: #38bdf8;
  --mapped: #4ade80;
  --unmapped: #f87171;
  --border: #334155;
  --box: #1e293b;
  --box-hover: #334155;
  --subbox: #273449;
  --subbox-hover: #334f6b;
  --selected: rgba(56, 189, 248, 0.35);
}
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; height: 100%; }
body {
  background: var(--bg); color: var(--ink);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  line-height: 1.45;
  display: flex; flex-direction: column;
}
header { padding: 1rem 1.5rem; border-bottom: 1px solid var(--border); flex: 0 0 auto; }
header .head-row { display: flex; align-items: center; gap: 1.5rem; }
header .head-info { flex: 1 1 auto; min-width: 0; }
header h1 { margin: 0 0 0.25rem; font-size: 1.25rem; }
header .subtitle { color: var(--muted); font-size: 0.85rem; }
header .stats { display: flex; gap: 1.5rem; margin-top: 0.5rem; font-size: 0.8rem; }
header .stat { color: var(--muted); }
header .stat b { color: var(--ink); margin-right: 0.3rem; }
header .stat.mapped b { color: var(--mapped); }
header .stat.unmapped b { color: var(--unmapped); }
header .stats-label {
  font-size: 0.7rem; color: var(--muted);
  text-transform: uppercase; letter-spacing: 0.08em;
  margin-right: 0.2rem; align-self: center;
}

.search-box {
  position: relative; flex: 0 0 340px; align-self: flex-start;
}
.search-box input {
  width: 100%; padding: 0.5rem 0.75rem;
  background: #0b1220; color: var(--ink);
  border: 1px solid var(--border); border-radius: 4px;
  font-size: 0.85rem; font-family: ui-monospace, "SF Mono", Monaco, monospace;
}
.search-box input:focus { outline: none; border-color: var(--accent); }
.search-suggestions {
  position: absolute; top: 100%; left: 0; right: 0;
  margin-top: 4px; z-index: 20;
  background: var(--panel); border: 1px solid var(--border); border-radius: 4px;
  max-height: 320px; overflow-y: auto;
  box-shadow: 0 8px 24px rgba(0,0,0,0.4);
  display: none;
}
.search-suggestions.open { display: block; }
.search-suggestions .item {
  padding: 0.35rem 0.6rem; cursor: pointer;
  font-family: ui-monospace, "SF Mono", Monaco, monospace;
  font-size: 0.78rem; line-height: 1.35;
  border-bottom: 1px solid var(--border);
}
.search-suggestions .item:last-child { border-bottom: none; }
.search-suggestions .item:hover,
.search-suggestions .item.active { background: var(--box-hover); }
.search-suggestions .item .path {
  color: var(--muted); font-size: 0.68rem; display: block;
}
.search-suggestions .item mark {
  background: rgba(56, 189, 248, 0.35); color: var(--ink); padding: 0;
}
.search-empty { padding: 0.5rem 0.6rem; color: var(--muted); font-size: 0.75rem; }

.layout {
  flex: 1 1 auto;
  display: grid;
  grid-template-columns: 1fr 480px;
  gap: 0;
  min-height: 0;
}
.left-col {
  overflow: auto;
  padding: 1rem;
  border-right: 1px solid var(--border);
  background: #0b1220;
}
.diagram-block {
  background: var(--panel); border: 1px solid var(--border); border-radius: 6px;
  padding: 0.75rem; margin-bottom: 1rem;
}
.diagram-block h2 {
  margin: 0 0 0.5rem; font-size: 0.8rem;
  color: var(--muted); text-transform: uppercase; letter-spacing: 0.1em;
  display: flex; gap: 0.4rem; align-items: center;
}
.diagram-block h2 .badge {
  background: var(--accent); color: #0f172a;
  padding: 0.05rem 0.4rem; border-radius: 8px;
  font-size: 0.7rem; font-weight: 700;
  text-transform: none; letter-spacing: normal;
}
svg { display: block; margin: 0 auto; }

.right-col {
  display: grid;
  grid-template-rows: 1fr 1fr;
  gap: 0;
  min-height: 0;
}
.right-pane {
  overflow: auto;
  padding: 1rem 1.25rem;
}
.right-pane.top { border-bottom: 1px solid var(--border); }
.right-pane h2 {
  margin: 0 0 0.5rem; font-size: 0.9rem; color: var(--accent);
  display: flex; align-items: center; gap: 0.5rem;
}
.right-pane h2 .badge {
  background: var(--accent); color: #0f172a;
  padding: 0.1rem 0.5rem; border-radius: 10px;
  font-size: 0.75rem; font-weight: 700;
}
.right-pane .path { font-size: 0.75rem; color: var(--muted); margin-bottom: 0.5rem; }
.right-pane .empty { color: var(--muted); font-style: italic; font-size: 0.9rem; }

.sub-summary {
  margin: 0.5rem 0;
  padding: 0.4rem 0.6rem;
  background: rgba(56, 189, 248, 0.05);
  border-left: 3px solid var(--accent);
  border-radius: 4px;
}
.sub-summary h3 {
  margin: 0 0 0.25rem; font-size: 0.85rem; color: var(--accent);
  font-weight: 600; display: flex; gap: 0.5rem; align-items: center;
}
.sub-summary h3 .sub-badge {
  background: var(--accent); color: #0f172a;
  padding: 0.05rem 0.35rem; border-radius: 8px;
  font-size: 0.65rem; font-weight: 700;
}

ul.event-list { list-style: none; padding: 0; margin: 0; }
ul.event-list li {
  padding: 0.2rem 0.5rem;
  font-family: ui-monospace, "SF Mono", Monaco, monospace;
  font-size: 0.78rem;
  cursor: pointer;
  border-radius: 3px;
  transition: background 0.05s;
}
ul.event-list li:hover { background: var(--box-hover); }
ul.event-list li.selected { background: var(--selected); color: white; }

.event-detail dl {
  margin: 0; display: grid; grid-template-columns: 130px 1fr;
  gap: 0.35rem 1rem; font-size: 0.82rem;
}
.event-detail dt { color: var(--muted); font-weight: 500; }
.event-detail dd {
  margin: 0; font-family: ui-monospace, "SF Mono", Monaco, monospace;
  word-break: break-word;
}
.event-detail dd.desc {
  font-family: inherit; color: var(--ink); line-height: 1.55;
}
.event-detail .name {
  font-family: ui-monospace, "SF Mono", Monaco, monospace;
  font-size: 0.95rem; color: var(--accent); margin: 0 0 0.5rem;
}
.pseudo-badge {
  display: inline-block; margin-left: 0.5rem;
  background: rgba(148, 163, 184, 0.15); color: var(--muted);
  border: 1px solid var(--border); border-radius: 10px;
  padding: 0.05rem 0.5rem;
  font-family: inherit; font-size: 0.65rem; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.08em;
  vertical-align: middle;
}
.click-hint {
  font-size: 0.65rem; color: var(--muted); font-weight: 400;
  text-transform: none; letter-spacing: normal;
  margin-left: 0.5rem; font-style: italic;
}
.diff-summary {
  margin: 0.5rem 0 0.6rem;
  background: rgba(56, 189, 248, 0.04);
  border: 1px solid var(--border); border-radius: 5px;
  padding: 0.5rem 0.7rem 0.5rem 0.55rem;
}
.diff-summary-hdr {
  font-size: 0.68rem; color: var(--muted);
  text-transform: uppercase; letter-spacing: 0.08em;
  margin-bottom: 0.35rem;
}
.diff-summary ul { list-style: none; margin: 0; padding: 0; }
.diff-summary li {
  font-size: 0.78rem; color: var(--ink); line-height: 1.45;
  padding: 0.2rem 0.35rem 0.2rem 0.55rem;
  border-left: 3px solid var(--accent);
  margin: 0.2rem 0;
  border-radius: 2px;
}
.diff-summary li b { font-weight: 600; }
.diff-summary li code {
  font-family: ui-monospace, "SF Mono", Monaco, monospace;
  font-size: 0.72rem;
  background: rgba(148,163,184,0.12);
  padding: 0.05rem 0.3rem; border-radius: 3px;
}
.primary-badge {
  display: inline-block; margin-left: 0.3rem;
  background: var(--accent); color: #0f172a;
  padding: 0.02rem 0.35rem; border-radius: 8px;
  font-family: inherit; font-size: 0.6rem; font-weight: 700;
  text-transform: uppercase; letter-spacing: 0.06em;
  vertical-align: middle;
}
.metric-detail .feeder.primary { border-color: var(--accent); }

/* TMA tree — JS-rendered */
.tma-toolbar {
  display: flex; gap: 0.5rem; align-items: center;
  padding: 0.4rem 0.6rem;
  border-bottom: 1px solid var(--border);
  margin-bottom: 0.4rem;
}
.tma-btn {
  background: var(--subbox); color: var(--ink);
  border: 1px solid var(--border); border-radius: 4px;
  padding: 0.25rem 0.65rem;
  font-size: 0.75rem; font-family: inherit; cursor: pointer;
}
.tma-btn:hover { border-color: var(--accent); background: var(--subbox-hover); }
.tma-hint {
  font-size: 0.7rem; color: var(--muted); font-style: italic;
  margin-left: auto;
}
.tma-node rect { fill: var(--box); stroke: var(--border); stroke-width: 1; }
.tma-node:hover > rect { fill: var(--box-hover); stroke: var(--accent); cursor: pointer; }
.tma-node.selected > rect { fill: rgba(56,189,248,0.25); stroke: var(--accent); stroke-width: 2; }
.tma-node text.title { fill: var(--ink); font-size: 11px; font-weight: 500; pointer-events: none; }
.tma-node text.lvl { fill: var(--accent); font-size: 9px; font-weight: 600; pointer-events: none; }
.tma-node.has-thr > rect { stroke: var(--accent); }
.tma-connector { stroke: var(--border); stroke-width: 1; fill: none; }
.tma-empty { fill: var(--muted); font-size: 13px; font-style: italic; }
.tma-empty-sub { fill: var(--muted); font-size: 11px; opacity: 0.75; }
.tma-root-sep { stroke: var(--border); stroke-width: 1; stroke-dasharray: 4 3; }

/* Toggle glyph on internal nodes */
.tma-toggle {
  cursor: pointer;
}
.tma-toggle circle {
  fill: #0b1220; stroke: var(--muted); stroke-width: 1;
}
.tma-toggle:hover circle { stroke: var(--accent); }
.tma-toggle text {
  fill: var(--muted); font-size: 12px; font-weight: 700;
  text-anchor: middle; dominant-baseline: middle;
  pointer-events: none; font-family: ui-monospace, monospace;
}
.tma-toggle:hover text { fill: var(--accent); }
.tma-node.collapsed .tma-toggle text { fill: var(--accent); }

.detail-section {
  margin-top: 0.9rem;
  padding-top: 0.6rem;
  border-top: 1px solid var(--border);
}
.detail-section h4 {
  margin: 0 0 0.35rem; font-size: 0.75rem;
  color: var(--muted); text-transform: uppercase; letter-spacing: 0.08em;
  font-weight: 600;
}
.detail-section .note {
  color: var(--ink); font-size: 0.82rem; line-height: 1.5;
  background: rgba(56, 189, 248, 0.06); border-left: 3px solid var(--accent);
  padding: 0.5rem 0.75rem; border-radius: 4px;
}
.acronyms { display: grid; gap: 0.35rem; }
.acronym {
  font-size: 0.78rem; line-height: 1.4;
}
.acronym .tok {
  font-family: ui-monospace, "SF Mono", Monaco, monospace;
  color: var(--accent); font-weight: 600;
}
.acronym .exp { color: var(--ink); }
.acronym .gloss { color: var(--muted); display: block; padding-left: 1rem; }

.perf-block {
  margin: 0.4rem 0; position: relative;
}
.perf-block .lbl {
  font-size: 0.7rem; color: var(--muted);
  text-transform: uppercase; letter-spacing: 0.08em;
  margin-bottom: 0.15rem;
}
.perf-block pre {
  margin: 0; padding: 0.55rem 2.4rem 0.55rem 0.7rem;
  background: #0b1220; border: 1px solid var(--border); border-radius: 4px;
  font-family: ui-monospace, "SF Mono", Monaco, monospace;
  font-size: 0.75rem; color: #e2e8f0;
  overflow-x: auto; white-space: pre;
}
.perf-block button.copy {
  position: absolute; top: 4px; right: 4px;
  background: var(--panel); color: var(--muted);
  border: 1px solid var(--border); border-radius: 3px;
  padding: 0.1rem 0.5rem; font-size: 0.68rem;
  cursor: pointer;
}
.perf-block button.copy:hover { background: var(--box-hover); color: var(--ink); }
.perf-notes { font-size: 0.75rem; color: var(--muted); margin-top: 0.35rem; }
.perf-notes li { margin: 0.15rem 0; }

/* Tabs */
.tabs {
  display: flex; gap: 0; margin-top: 0.75rem;
  border-bottom: 1px solid var(--border);
}
.tab {
  padding: 0.4rem 0.9rem;
  color: var(--muted); font-size: 0.85rem; font-weight: 600;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
}
.tab:hover { color: var(--ink); }
.tab.active { color: var(--accent); border-bottom-color: var(--accent); }
.tab .badge {
  background: var(--border); color: var(--muted);
  border-radius: 8px; padding: 0.05rem 0.4rem;
  font-size: 0.7rem; margin-left: 0.35rem;
}
.tab.active .badge { background: var(--accent); color: #0f172a; }

.compare-toggle-wrap { margin-left: auto; display: flex; align-items: center; }
.compare-toggle {
  display: flex; align-items: center; gap: 0.4rem;
  padding: 0.35rem 0.7rem; font-size: 0.78rem;
  color: var(--muted); cursor: pointer;
}
.compare-toggle input { accent-color: var(--accent); cursor: pointer; }
.compare-toggle:hover { color: var(--ink); }
.compare-toggle #compare-baseline { color: var(--ink); font-weight: 600; }
.compare-toggle .help-tip { margin-left: 0.15rem; }

.compare-strip {
  background: rgba(56, 189, 248, 0.06);
  border-bottom: 1px solid var(--border);
  padding: 0.5rem 1.5rem;
  font-size: 0.8rem;
}
.cs-header { display: flex; align-items: baseline; gap: 1rem; }
.cs-header b { color: var(--accent); }
.cs-counts { color: var(--muted); font-size: 0.75rem; }
.cs-counts .cs-new { color: var(--mapped); }
.cs-counts .cs-changed { color: #fbbf24; }
.cs-counts .cs-removed { color: var(--unmapped); }
.cs-cells {
  display: flex; flex-wrap: wrap; gap: 0.5rem;
  margin-top: 0.35rem;
}
.cs-cell {
  background: var(--panel); border: 1px solid var(--border); border-radius: 4px;
  padding: 0.2rem 0.5rem;
  font-size: 0.7rem; color: var(--muted);
}
.cs-cell b { color: var(--ink); font-weight: 600; }
.cs-cell .cs-n { color: var(--mapped); }
.cs-cell .cs-c { color: #fbbf24; }
.cs-cell .cs-r { color: var(--unmapped); }

/* Status dots — used in the tooltip legend and event lists */
.dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin: 0 1px; vertical-align: middle; }
.dot-new { background: var(--mapped); }
.dot-changed { background: #fbbf24; }
.dot-removed { background: var(--unmapped); }

/* Diff-mode badges (added when body has class="cmp-on") */
body.cmp-on ul.event-list li[data-status="new"] { border-left: 3px solid var(--mapped); padding-left: 0.35rem; }
body.cmp-on ul.event-list li[data-status="changed"] { border-left: 3px solid #fbbf24; padding-left: 0.35rem; }
body.cmp-on ul.metric-list li[data-status="new"] { border-left: 3px solid var(--mapped); padding-left: 0.35rem; }
body.cmp-on ul.metric-list li[data-status="changed"] { border-left: 3px solid #fbbf24; padding-left: 0.35rem; }

body.cmp-on [data-metric][data-status="new"] > rect.cell-frame { stroke: var(--mapped); }
body.cmp-on [data-metric][data-status="changed"] > rect.cell-frame { stroke: #fbbf24; }

/* Subtle accent-coloured outline on boxes that have diff activity */
body.cmp-on [data-path].cmp-box-outline > rect.cell-frame { stroke: var(--accent); }

.status-badge {
  display: inline-block; margin-left: 0.35rem;
  padding: 0.02rem 0.35rem; border-radius: 8px;
  font-size: 0.6rem; font-weight: 700;
  text-transform: uppercase; letter-spacing: 0.06em;
  vertical-align: middle;
}
.status-badge.new { background: var(--mapped); color: #0f172a; }
.status-badge.changed { background: #fbbf24; color: #0f172a; }
.status-badge.removed { background: var(--unmapped); color: #0f172a; }

/* "Removed since baseline" section in each tab's sidebar */
.removed-list li { color: var(--muted); text-decoration: line-through; }

/* Field-level diff detail views */
.diff-table {
  width: 100%; margin: 0.5rem 0 0.35rem;
  border-collapse: collapse; font-size: 0.78rem;
}
.diff-table th, .diff-table td {
  padding: 0.3rem 0.55rem; text-align: left;
  border-bottom: 1px solid var(--border);
}
.diff-table th {
  color: var(--muted); font-weight: 500; font-size: 0.7rem;
  text-transform: uppercase; letter-spacing: 0.06em;
}
.diff-table td.diff-old {
  color: var(--muted);
  font-family: ui-monospace, "SF Mono", Monaco, monospace;
  text-decoration: line-through;
}
.diff-table td.diff-new-cell {
  color: var(--mapped);
  font-family: ui-monospace, "SF Mono", Monaco, monospace;
}
.diff-label {
  font-size: 0.7rem; color: var(--muted);
  text-transform: uppercase; letter-spacing: 0.06em;
  margin: 0.5rem 0 0.15rem;
}
.diff-old-block {
  border-left: 3px solid var(--unmapped);
  opacity: 0.85;
}
.diff-new-block { border-left: 3px solid var(--mapped); }
.feeder.diff-new-chip { border-color: var(--mapped); color: var(--mapped); }
.feeder.diff-rem-chip { border-color: var(--unmapped); color: var(--unmapped); text-decoration: line-through; }

.view { display: none; }
.view.active { display: block; }

/* Metric detail styling */
.metric-detail .name {
  font-family: ui-monospace, "SF Mono", Monaco, monospace;
  font-size: 0.95rem; color: var(--accent); margin: 0 0 0.35rem;
}
.metric-detail .meta {
  font-size: 0.75rem; color: var(--muted); margin-bottom: 0.5rem;
}
.metric-detail .formula {
  background: #0b1220; border: 1px solid var(--border); border-radius: 4px;
  padding: 0.55rem 0.7rem;
  font-family: ui-monospace, "SF Mono", Monaco, monospace;
  font-size: 0.75rem; white-space: pre-wrap; word-break: break-word;
  color: #e2e8f0; overflow-x: auto;
}
.metric-detail .threshold {
  background: rgba(248, 113, 113, 0.08); border-left: 3px solid var(--unmapped);
  padding: 0.35rem 0.7rem; border-radius: 4px;
  font-size: 0.78rem; color: var(--ink);
  margin: 0.4rem 0;
}
.metric-detail .feeders {
  display: flex; flex-wrap: wrap; gap: 0.3rem;
}
.metric-detail .feeder {
  font-family: ui-monospace, "SF Mono", Monaco, monospace;
  font-size: 0.72rem;
  background: var(--subbox); border: 1px solid var(--border);
  padding: 0.15rem 0.5rem; border-radius: 12px;
  cursor: pointer;
}
.metric-detail .feeder:hover {
  background: var(--subbox-hover); border-color: var(--accent);
}

/* Metrics tree left-column shell */
.tma-block { max-width: none; }
.tma-block .tree-scroll { max-height: 620px; overflow: auto; }
.subblock {
  margin-top: 0.75rem;
  background: var(--panel); border: 1px solid var(--border); border-radius: 6px;
}
.subblock > summary {
  padding: 0.55rem 0.85rem; cursor: pointer; font-weight: 600;
  font-size: 0.9rem; color: var(--ink);
  display: flex; gap: 0.4rem; align-items: center;
}
.subblock > summary:hover { background: var(--box-hover); }
.subblock[open] > summary { border-bottom: 1px solid var(--border); }
.subblock .badge {
  background: var(--accent); color: #0f172a;
  padding: 0.05rem 0.4rem; border-radius: 8px;
  font-size: 0.7rem; font-weight: 700;
}
.subblock ul.metric-list { list-style: none; margin: 0; padding: 0.35rem 0.85rem 0.7rem; }
.subblock ul.metric-list li {
  font-family: ui-monospace, "SF Mono", Monaco, monospace;
  font-size: 0.75rem;
  padding: 0.15rem 0.4rem;
  cursor: pointer; border-radius: 3px;
}
.subblock ul.metric-list li:hover { background: var(--box-hover); }
.subblock ul.metric-list li.selected { background: var(--selected); }
.subblock .group-title {
  font-size: 0.75rem; color: var(--muted);
  padding: 0.25rem 0.85rem 0.1rem;
  text-transform: uppercase; letter-spacing: 0.08em;
}

/* (?) help tooltip — pure CSS */
.help-tip {
  display: inline-flex; align-items: center; justify-content: center;
  width: 15px; height: 15px; margin-left: 0.4rem;
  background: var(--subbox); color: var(--muted);
  border: 1px solid var(--border); border-radius: 50%;
  font-size: 10px; font-weight: 600; font-family: inherit;
  cursor: help;
  position: relative;
  user-select: none;
}
.help-tip:hover { background: var(--accent); color: #0f172a; border-color: var(--accent); }
.help-tip .tip {
  position: absolute; top: 22px; left: 0;
  min-width: 260px; max-width: 380px;
  background: #0b1220;
  color: var(--ink);
  border: 1px solid var(--accent);
  border-radius: 6px;
  padding: 0.55rem 0.75rem;
  font-size: 0.75rem; font-weight: 400; line-height: 1.5;
  text-transform: none; letter-spacing: normal;
  z-index: 100;
  box-shadow: 0 8px 24px rgba(0,0,0,0.4);
  opacity: 0; visibility: hidden;
  transition: opacity 0.15s;
  pointer-events: none;
  white-space: normal; text-align: left;
}
.help-tip:hover .tip, .help-tip:focus .tip { opacity: 1; visibility: visible; }
.help-tip .tip b { color: var(--accent); }
/* Used-by-metrics section in event detail */
.usedby {
  display: flex; flex-wrap: wrap; gap: 0.3rem;
}
.usedby .m-chip {
  font-family: ui-monospace, "SF Mono", Monaco, monospace;
  font-size: 0.72rem;
  background: var(--subbox); border: 1px solid var(--border);
  padding: 0.15rem 0.5rem; border-radius: 12px;
  cursor: pointer;
}
.usedby .m-chip:hover { background: var(--subbox-hover); border-color: var(--accent); }

/* SVG box styles */
.cell rect.cell-frame { fill: var(--box); stroke: var(--border); stroke-width: 1.5; transition: stroke 0.1s, fill 0.1s; }
.cell:hover > rect.cell-frame { stroke: var(--accent); cursor: pointer; }
.cell.selected > rect.cell-frame { stroke: var(--accent); stroke-width: 2.5; fill: rgba(56, 189, 248, 0.08); }
.cell.empty > rect.cell-frame { fill: #0f172a; stroke-dasharray: 3 3; }
.cell.empty > text.node-title { fill: var(--muted); }
.cell.empty > text.node-count { fill: var(--muted); }

.sub > rect.cell-frame { fill: var(--subbox); stroke: var(--border); stroke-width: 1; transition: fill 0.05s, stroke 0.05s; }
.sub:hover > rect.cell-frame { fill: var(--subbox-hover); stroke: var(--accent); cursor: pointer; }
.sub.selected > rect.cell-frame { fill: var(--selected); stroke: var(--accent); stroke-width: 2; }

.sub[data-depth="3"] > rect.cell-frame { fill: #2d3d55; }
.sub[data-depth="4"] > rect.cell-frame { fill: #33475e; }

text.node-title { fill: var(--ink); font-weight: 600; pointer-events: none; }
text.node-count { fill: var(--accent); font-weight: 600; pointer-events: none; }
/* When compare mode is on, the "N events" corner label is replaced by
   a "+N ~M -K" diff label (injected by JS as text.node-diff). Hiding
   the count in advance avoids a flash of the wrong value. */
body.cmp-on text.node-count { display: none; }
/* Hide the plain "Lx ⚑" TMA label whenever there is a sibling diff label
   (injected by applyTmaDiffLabels). Nodes with no diff activity keep the
   plain label. */
/* Hide the plain "Lx ⚑" label whenever a sibling diff label is present.
   The diff label ALSO carries class "lvl" so we must exclude it explicitly. */
body.cmp-on .tma-node:has(> text.node-diff) > text.lvl:not(.node-diff) { display: none; }
text.node-diff { fill: var(--muted); font-weight: 700; pointer-events: none; }
text.node-diff .diff-new { fill: var(--mapped); }
text.node-diff .diff-chg { fill: #fbbf24; }
text.node-diff .diff-rem { fill: var(--unmapped); }

.group-label { fill: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: 0.1em; }
.flow-label { fill: var(--muted); font-size: 10px; font-style: italic; }
.flow line, .flow path { stroke: var(--muted); stroke-width: 1.5; fill: none; }
.flow.control line, .flow.control path { stroke-dasharray: 4 3; }
"""


PAGE_JS = """
(function(){
  // Per-tab left-column selection state, independent so switching tabs
  // preserves what was highlighted there. detail.kind ('event'|'metric')
  // determines what the bottom detail pane shows regardless of active tab.
  var state = {
    tab: 'events',
    events: {path: null, eventName: null},   // events-tab selection
    metrics: {metric: null},                  // metrics-tab selection
    detail: {kind: null, name: null},         // bottom pane subject
  };

  function q(sel, root){ return (root||document).querySelector(sel); }
  function qa(sel, root){ return Array.prototype.slice.call((root||document).querySelectorAll(sel)); }

  // Find a uarch tree node by path array [cellId, subId, ...].
  function findNode(pathArr){
    if(!pathArr || !pathArr.length) return null;
    var node = ARCH.cells[pathArr[0]];
    if(!node) return null;
    for(var i = 1; i < pathArr.length; i++){
      var kids = node.subs || [];
      var found = null;
      for(var j = 0; j < kids.length; j++){
        if(kids[j].id === pathArr[i]){ found = kids[j]; break; }
      }
      if(!found) return null;
      node = found;
    }
    return node;
  }

  function collectEvents(node){
    if(node.events && node.events.length) return node.events.slice();
    var out = [];
    (node.subs || []).forEach(function(k){ out = out.concat(collectEvents(k)); });
    return out;
  }

  // -------- Tab switching --------
  function setTab(name){
    var changed = state.tab !== name;
    state.tab = name;
    qa('.tab').forEach(function(el){ el.classList.toggle('active', el.getAttribute('data-tab') === name); });
    qa('.view').forEach(function(el){ el.classList.toggle('active', el.id === 'view-' + name); });
    if(changed){
      // Repaint the top-right pane so it reflects the new tab's selection.
      renderList();
    }
  }

  function wireTabs(){
    qa('.tab').forEach(function(el){
      el.addEventListener('click', function(){ setTab(el.getAttribute('data-tab')); });
    });
  }

  // -------- Compare-against-baseline --------
  // ARCH.diff (may be null) supplies per-name status maps + removed sets +
  // per-cell rollups. When compareOn is true, we tag list items and SVG
  // nodes with data-status="new" | "changed" so CSS colours them.
  var compareOn = false;

  function diffStatusForEvent(name){
    if(!ARCH.diff) return null;
    return ARCH.diff.events_status[name] || null;
  }
  function diffStatusForMetric(name){
    if(!ARCH.diff) return null;
    return ARCH.diff.metrics_status[name] || null;
  }

  function statusBadgeHtml(status){
    if(!compareOn || !status || status === 'same') return '';
    if(status === 'new') return ' <span class="status-badge new">new</span>';
    if(status === 'changed') return ' <span class="status-badge changed">changed</span>';
    return '';
  }

  function statusAttr(status){
    // Only decorate 'new' and 'changed' — leave unchanged items alone so
    // the diff highlights don't drown out the normal display.
    if(!compareOn || !status || status === 'same') return '';
    return ' data-status="'+status+'"';
  }

  function initCompareToggle(){
    var wrap = q('#compare-toggle-label');
    if(!ARCH.diff){ wrap.style.display = 'none'; return; }
    q('#compare-baseline').textContent = ARCH.diff.baseline_name || ARCH.diff.baseline;
    wrap.style.display = 'inline-flex';
    var input = q('#compare-toggle');
    // Sync JS state with the checkbox's initial (checked) attribute so the
    // diff decorations render on first paint without a user interaction.
    compareOn = input.checked;
    document.body.classList.toggle('cmp-on', compareOn);
    q('#compare-strip').style.display = compareOn ? 'block' : 'none';
    if(compareOn) renderCompareStrip();
    input.addEventListener('change', function(e){
      compareOn = e.target.checked;
      document.body.classList.toggle('cmp-on', compareOn);
      q('#compare-strip').style.display = compareOn ? 'block' : 'none';
      if(compareOn){ renderCompareStrip(); applyStatusToDom(); }
      else { qa('text.node-diff').forEach(function(el){ el.remove(); });
             qa('.cmp-box-outline').forEach(function(el){ el.classList.remove('cmp-box-outline'); }); }
      // Repaint lists + removed sections so state matches the toggle.
      renderList();
      renderMetricsSidebar();
      renderTmaTree();
      applyTmaDiffLabels();
      renderRemovedSections();
    });
  }

  function renderCompareStrip(){
    if(!ARCH.diff) return;
    var d = ARCH.diff;
    var e = d.counts.events, m = d.counts.metrics;
    q('#cs-baseline').textContent = d.baseline_name || d.baseline;

    // We only show *real* differences. Renames and denser-variant churn
    // are filtered out (see UNIT_RENAMES + bucketing in Python).
    var newTip = '';
    if(e.new_renamed > 0){
      newTip = '<span class="help-tip" tabindex="0">?<span class="tip">' +
        '<b>' + e.new_renamed + ' events</b> that would otherwise look "new" ' +
        'are renamed baseline events (unit renamed, same conceptual event).' +
        ' They are shown as unchanged.</span></span>';
    }
    var removedTip = '';
    var hidden = (e.removed_renamed || 0) + (e.removed_unit_retired || 0) +
                 (e.removed_denser_variants || 0);
    if(hidden > 0){
      removedTip = '<span class="help-tip" tabindex="0">?<span class="tip">' +
        'Additionally, <b>' + hidden + ' events</b> present on the baseline ' +
        'do not appear on this platform, but are<br>' +
        '&nbsp;• ' + (e.removed_renamed || 0) + ' events under a renamed unit ' +
        '(same event, e.g. M2M→B2CMI)<br>' +
        '&nbsp;• ' + (e.removed_unit_retired || 0) + ' events in units that were retired ' +
        '(e.g. HBM controllers)<br>' +
        '&nbsp;• ' + (e.removed_denser_variants || 0) + ' denser baseline variants ' +
        '(per-slice variants the current release consolidates).<br>' +
        'These are filtered out to keep the highlight focused on real changes.' +
        '</span></span>';
    }
    var metricsPart = '';
    if(d.metrics_diff_available){
      metricsPart =
        '  Metrics: <span class="cs-new">+'+m.new+'</span> ' +
        '<span class="cs-changed">~'+m.changed+'</span> ' +
        '<span class="cs-removed">-'+m.removed+'</span>';
    } else {
      metricsPart =
        '  <span style="color:var(--muted);font-style:italic;">Metrics diff skipped ' +
        '— this platform has not yet published TMA formulas.</span>';
    }
    q('#cs-counts').innerHTML =
      'Events: <span class="cs-new">+'+e.new+'</span>' + newTip + ' ' +
      '<span class="cs-changed">~'+e.changed+'</span> ' +
      '<span class="cs-removed">-'+e.removed_genuinely_gone+'</span>' + removedTip +
      metricsPart;
    var host = q('#cs-cells');
    var cells = d.cell_rollup || {};
    // Show only cells that actually changed something
    var entries = Object.keys(cells).map(function(cid){
      var r = cells[cid];
      return {id: cid, r: r, activity: r.new + r.changed + r.removed};
    }).filter(function(x){ return x.activity > 0; })
      .sort(function(a,b){ return b.activity - a.activity; });
    host.innerHTML = entries.map(function(x){
      var name = (ARCH.cells[x.id] && ARCH.cells[x.id].title) || x.id;
      return '<span class="cs-cell"><b>'+escapeHtml(name)+'</b> ' +
        (x.r.new ? '<span class="cs-n">+'+x.r.new+'</span> ' : '') +
        (x.r.changed ? '<span class="cs-c">~'+x.r.changed+'</span> ' : '') +
        (x.r.removed ? '<span class="cs-r">-'+x.r.removed+'</span>' : '') +
        '</span>';
    }).join('');
  }

  function applyStatusToDom(){
    // For each uarch box, replace its "N events" corner label with a
    // "+N ~M -K" diff label (injected as text.node-diff at the same
    // position). The count itself is hidden via CSS while body.cmp-on.
    if(!ARCH.diff || !ARCH.diff.path_rollup) return;
    var rollup = ARCH.diff.path_rollup;
    // Idempotent — strip prior arch-map injections only (leave TMA-tree
    // labels alone; those are managed by applyTmaDiffLabels).
    qa('[data-path] > text.node-diff').forEach(function(el){ el.remove(); });
    qa('.cmp-box-outline').forEach(function(el){ el.classList.remove('cmp-box-outline'); });

    var NS = 'http://www.w3.org/2000/svg';
    qa('[data-path]').forEach(function(g){
      var p = g.getAttribute('data-path');
      var r = rollup[p];
      if(!r) return;
      var activity = (r["new"]||0) + (r["changed"]||0) + (r["removed"]||0);
      if(activity === 0) return;
      var count = g.querySelector(':scope > text.node-count');
      if(!count) return;
      var bits = [];
      if(r["new"] > 0)     bits.push({t: '+' + r["new"],     cls: 'diff-new'});
      if(r["changed"] > 0) bits.push({t: '~' + r["changed"], cls: 'diff-chg'});
      if(r["removed"] > 0) bits.push({t: '-' + r["removed"], cls: 'diff-rem'});
      if(!bits.length) return;
      var badge = document.createElementNS(NS, 'text');
      badge.setAttribute('class', 'node-diff');
      badge.setAttribute('x', count.getAttribute('x'));
      badge.setAttribute('y', count.getAttribute('y'));
      badge.setAttribute('text-anchor', 'end');
      // Same font as the count so the swap is visually stable.
      badge.setAttribute('style', count.getAttribute('style') || '');
      bits.forEach(function(b, i){
        var t = document.createElementNS(NS, 'tspan');
        t.setAttribute('class', b.cls);
        if(i > 0) t.setAttribute('dx', '4');
        t.textContent = b.t;
        badge.appendChild(t);
      });
      g.appendChild(badge);
      g.classList.add('cmp-box-outline');
    });
  }

  function applyTmaDiffLabels(){
    // Post-render decoration for TMA tree nodes: inject a <text class="node-diff">
    // sibling for every node whose subtree rollup has activity. CSS hides the
    // sibling <text class="lvl"> when body.cmp-on. We do this after render
    // (DOM manipulation, not string concat) to avoid an HTML-parser artifact
    // where tspans inside an initially-parsed <text> can be dropped.
    qa('#tma-svg-container text.node-diff').forEach(function(el){ el.remove(); });
    if(!compareOn) return;
    if(!ARCH.diff || !ARCH.diff.tma_rollup) return;
    var NS = 'http://www.w3.org/2000/svg';
    var rollup = ARCH.diff.tma_rollup;
    qa('#tma-svg-container [data-metric]').forEach(function(g){
      var name = g.getAttribute('data-metric');
      var r = rollup[name];
      if(!r) return;
      var activity = (r["new"]||0) + (r["changed"]||0) + (r["removed"]||0);
      if(activity === 0) return;
      var lvl = g.querySelector(':scope > text.lvl');
      if(!lvl) return;
      var text = document.createElementNS(NS, 'text');
      text.setAttribute('class', 'lvl node-diff');
      text.setAttribute('x', lvl.getAttribute('x'));
      text.setAttribute('y', lvl.getAttribute('y'));
      text.setAttribute('text-anchor', 'middle');
      var bits = [];
      if(r["new"] > 0)     bits.push({t: '+' + r["new"],     cls: 'diff-new'});
      if(r["changed"] > 0) bits.push({t: '~' + r["changed"], cls: 'diff-chg'});
      if(r["removed"] > 0) bits.push({t: '-' + r["removed"], cls: 'diff-rem'});
      bits.forEach(function(b, i){
        var ts = document.createElementNS(NS, 'tspan');
        ts.setAttribute('class', b.cls);
        if(i > 0) ts.setAttribute('dx', '4');
        ts.textContent = b.t;
        text.appendChild(ts);
      });
      g.appendChild(text);
    });
  }

  function renderRemovedSections(){
    if(!ARCH.diff) return;
    // Events tab: "Removed since baseline"
    var block = q('#removed-events-block');
    var list = q('#removed-events-list');
    var count = q('#removed-events-count');
    var evGone = ARCH.diff.events_removed_genuine || [];
    if(evGone.length){
      count.textContent = evGone.length;
      list.innerHTML = evGone.map(function(name){
        return '<li data-metric="__removed-ev__" title="'+escapeHtml(name)+'">'+
          escapeHtml(name)+' <span class="status-badge removed">removed</span></li>';
      }).join('');
      block.style.display = compareOn ? '' : 'none';
    } else {
      block.style.display = 'none';
    }
    // Metrics tab: "Removed since baseline" — attach into #view-metrics.
    var host = q('#view-metrics');
    var existing = q('#removed-metrics-block');
    if(existing) existing.remove();
    var mGone = (ARCH.diff.metrics_diff_available ? ARCH.diff.metrics_removed : []) || [];
    if(mGone.length){
      var det = document.createElement('details');
      det.className = 'subblock';
      det.id = 'removed-metrics-block';
      det.style.display = compareOn ? '' : 'none';
      det.innerHTML = '<summary>Removed since '+escapeHtml(ARCH.diff.baseline)+
        ' <span class="badge">'+mGone.length+'</span></summary>' +
        '<ul class="metric-list removed-list">' +
        mGone.map(function(name){
          return '<li title="'+escapeHtml(name)+'">'+escapeHtml(name)+
            ' <span class="status-badge removed">removed</span></li>';
        }).join('') +
        '</ul>';
      host.appendChild(det);
    }
  }
  // -------- Events tab: uarch selection --------
  function selectPath(pathStr){
    state.events.path = pathStr;
    state.events.eventName = null;
    // Clear only the SVG highlight in the events view (not metrics view).
    qa('#view-events .selected').forEach(function(el){ el.classList.remove('selected'); });
    var arr = pathStr.split('/');
    for(var i = 1; i <= arr.length; i++){
      var seg = arr.slice(0, i).join('/');
      var el = q('[data-path="'+seg+'"]');
      if(el) el.classList.add('selected');
    }
    // Selecting a path means the current "thing under inspection" is the
    // component itself, not any specific event yet — clear detail subject.
    state.detail.kind = null; state.detail.name = null;
    renderList();
    renderDetail();
  }

  function pathTitle(pathArr){
    var titles = [];
    var node = ARCH.cells[pathArr[0]];
    if(node) titles.push(node.title);
    for(var i = 1; i < pathArr.length; i++){
      node = (node && node.subs || []).filter(function(k){return k.id === pathArr[i];})[0];
      if(node) titles.push(node.title);
    }
    return titles.join(' › ');
  }

  function renderNodeGroup(node, pathStr){
    var parts = [];
    var kids = node.subs || [];
    if(kids.length === 0){
      parts.push('<ul class="event-list">');
      (node.events || []).forEach(function(name){
        var status = diffStatusForEvent(name);
        parts.push('<li data-ev="'+encodeURIComponent(name)+'"'+statusAttr(status)+'>'+
          escapeHtml(name)+statusBadgeHtml(status)+'</li>');
      });
      parts.push('</ul>');
      return parts.join('');
    }
    kids.forEach(function(k){
      var kPath = pathStr + '/' + k.id;
      parts.push('<div class="sub-summary" data-jump="'+kPath+'">');
      parts.push('<h3>'+escapeHtml(k.title)+' <span class="sub-badge">'+k.count+'</span></h3>');
      parts.push(renderNodeGroup(k, kPath));
      parts.push('</div>');
    });
    return parts.join('');
  }

  function renderList(){
    // The top-right pane reflects whichever tab is currently active.
    var pane = q('#pane-list');
    if(state.tab === 'metrics'){
      var name = state.metrics.metric;
      if(!name){
        pane.innerHTML = '<div class="empty">Click a metric on the left.</div>';
        return;
      }
      renderMetricFeederList(pane, name);
      return;
    }
    // Events tab
    if(!state.events.path){
      pane.innerHTML = '<div class="empty">Click a component on the left.</div>';
      return;
    }
    var arr = state.events.path.split('/');
    var node = findNode(arr);
    if(!node){
      pane.innerHTML = '<div class="empty">Unknown component.</div>';
      return;
    }
    var parts = [];
    parts.push('<h2>'+escapeHtml(node.title)+' <span class="badge">'+node.count+'</span></h2>');
    parts.push('<div class="path">'+escapeHtml(pathTitle(arr))+'</div>');
    parts.push(renderNodeGroup(node, state.events.path));
    pane.innerHTML = parts.join('');
    wireEventListItems();
    qa('#pane-list .sub-summary').forEach(function(el){
      var header = el.querySelector('h3');
      if(!header) return;
      header.style.cursor = 'pointer';
      header.addEventListener('click', function(e){
        e.stopPropagation();
        selectPath(el.getAttribute('data-jump'));
      });
    });
  }

  function buildMetricDiffSummary(m, st){
    // Produce a short bullet list summarizing what changed for this metric
    // vs the baseline. Only rendered when compareOn && the metric has some
    // diff signal (own status, or subtree activity for containers).
    if(!compareOn || !ARCH.diff) return '';
    var bullets = [];

    if(st === 'new'){
      bullets.push({tone: 'new', text:
        '<b>New in '+escapeHtml(ARCH.metrics_short_platform || 'this platform')+'</b> — not defined in '+
        escapeHtml(ARCH.diff.baseline)+'.'});
    } else if(st === 'changed'){
      var info = (ARCH.diff.metrics_changes || {})[m.name] || {};
      // Feeder-event churn
      var changedFeeders = m.events.filter(function(en){ return diffStatusForEvent(en) === 'changed'; });
      var newFeeders = m.events.filter(function(en){ return diffStatusForEvent(en) === 'new'; });
      if(changedFeeders.length){
        bullets.push({tone: 'chg', text:
          '<b>'+changedFeeders.length+' feeder event'+(changedFeeders.length===1?'':'s')+' changed encoding</b> ' +
          '(highlighted below).'});
      }
      if(newFeeders.length){
        bullets.push({tone: 'new', text:
          '<b>'+newFeeders.length+' feeder event'+(newFeeders.length===1?'':'s')+' new</b> since '+escapeHtml(ARCH.diff.baseline)+'.'});
      }
      if(info.events_added && info.events_added.length){
        bullets.push({tone: 'new', text:
          '<b>Formula references '+info.events_added.length+' new event'+
          (info.events_added.length===1?'':'s')+'</b>: <code>'+
          info.events_added.slice(0,3).map(escapeHtml).join(', </code><code>')+'</code>'+
          (info.events_added.length>3?' <span style="color:var(--muted)">(+'+(info.events_added.length-3)+' more)</span>':'')+
          '.'});
      }
      if(info.events_removed && info.events_removed.length){
        bullets.push({tone: 'rem', text:
          '<b>Formula no longer references '+info.events_removed.length+' event'+
          (info.events_removed.length===1?'':'s')+'</b>: <code>'+
          info.events_removed.slice(0,3).map(escapeHtml).join(', </code><code>')+'</code>'+
          (info.events_removed.length>3?' <span style="color:var(--muted)">(+'+(info.events_removed.length-3)+' more)</span>':'')+
          '.'});
      }
      if(info.formula_current && info.formula_baseline &&
         info.formula_current !== info.formula_baseline){
        bullets.push({tone: 'chg', text:
          '<b>Formula was rewritten</b> (see <em>Diff vs '+
          escapeHtml(ARCH.diff.baseline)+'</em> below for old/new side-by-side).'});
      }
      if(info.level_current !== undefined && info.level_baseline !== undefined &&
         info.level_current !== info.level_baseline){
        bullets.push({tone: 'chg', text:
          '<b>TMA level changed</b>: L'+info.level_baseline+' → L'+info.level_current+'.'});
      }
      // Fallback if nothing above matched — the metric was flagged 'changed'
      // by _metric_signature but our per-field detail didn't catch the reason.
      if(bullets.length === 0){
        bullets.push({tone: 'chg', text:
          'This metric differs from '+escapeHtml(ARCH.diff.baseline)+' in a way not captured here — '+
          'see <em>Diff vs '+escapeHtml(ARCH.diff.baseline)+'</em> below.'});
      }
    }

    if(bullets.length === 0) return '';
    var toneColour = {new: 'var(--mapped)', chg: '#fbbf24', rem: 'var(--unmapped)'};
    var html = '<div class="diff-summary">' +
      '<div class="diff-summary-hdr">What changed vs '+escapeHtml(ARCH.diff.baseline)+'</div>' +
      '<ul>' +
      bullets.map(function(b){
        return '<li style="border-color:'+toneColour[b.tone]+';">'+b.text+'</li>';
      }).join('') +
      '</ul></div>';
    return html;
  }

  function renderMetricFeederList(pane, name){
    var m = ARCH.metrics[name];
    if(!m){ pane.innerHTML = '<div class="empty">Unknown metric.</div>'; return; }
    var parts = [];
    var st = diffStatusForMetric(m.name);
    parts.push('<h2>'+escapeHtml(m.name)+' <span class="badge">L'+m.level+'</span>'+statusBadgeHtml(st)+'</h2>');
    var pathBits = [];
    if(m.category) pathBits.push(m.category);
    if(m.parent) pathBits.push(m.parent);
    if(pathBits.length) parts.push('<div class="path">'+escapeHtml(pathBits.join(' › '))+'</div>');
    // Diff summary — bullets describing what changed vs the baseline.
    var summary = buildMetricDiffSummary(m, st);
    if(summary) parts.push(summary);
    parts.push('<h4 style="margin:0.5rem 0 0.35rem;font-size:0.75rem;color:var(--muted);text-transform:uppercase;letter-spacing:0.08em;">Feeder events ('+m.events.length+')<span class="click-hint">single-click: preview · double-click: jump</span></h4>');
    // Detect the "primary" feeder — a pseudo-event whose name pattern matches
    // the metric (e.g. Frontend_Bound ↔ PERF_METRICS.FRONTEND_BOUND). This
    // isn't self-reference, it's the raw counter the metric is normalizing.
    var primary = primaryFeederFor(m.name, m.events);
    parts.push('<ul class="event-list">');
    m.events.forEach(function(ename){
      var badges = '';
      if(ename === primary) badges += ' <span class="primary-badge">primary</span>';
      var status = diffStatusForEvent(ename);
      badges += statusBadgeHtml(status);
      parts.push('<li data-ev="'+encodeURIComponent(ename)+'"'+statusAttr(status)+'>'+
        escapeHtml(ename)+badges+'</li>');
    });
    parts.push('</ul>');
    pane.innerHTML = parts.join('');
    wireEventListItems();
  }

  function primaryFeederFor(metricName, eventNames){
    // A metric like Frontend_Bound has PERF_METRICS.FRONTEND_BOUND in its
    // feeder list. That's the "primary" reading — everything else in the
    // formula is a normalizer (TOPDOWN.SLOTS) or sibling bucket. Match by
    // upper-casing the metric name and comparing the suffix.
    var target = metricName.toUpperCase();
    for(var i = 0; i < eventNames.length; i++){
      var ename = eventNames[i];
      if(!ename.startsWith('PERF_METRICS.')) continue;
      var tail = ename.slice('PERF_METRICS.'.length).replace(/_/g, '_');
      if(tail === target || tail === target.replace(/_/g, '')) {
        return ename;
      }
    }
    return null;
  }

  // Distinguish single vs double click. Single-click just shows the item's
  // detail in the bottom pane (stays on the current tab); double-click
  // navigates to the item's home tab and highlights it there.
  function bindNavClicks(el, onSingle, onDouble){
    var timer = null;
    el.addEventListener('click', function(e){
      e.preventDefault();
      if(timer){ return; }  // between two clicks of an in-progress double
      timer = setTimeout(function(){
        timer = null;
        onSingle();
      }, 220);
    });
    el.addEventListener('dblclick', function(e){
      e.preventDefault();
      if(timer){ clearTimeout(timer); timer = null; }
      onDouble();
    });
  }

  function wireEventListItems(){
    qa('#pane-list li[data-ev]').forEach(function(li){
      var name = decodeURIComponent(li.getAttribute('data-ev'));
      bindNavClicks(
        li,
        // Single-click: on Events tab, this is the primary event selection;
        // on Metrics tab, it's a preview that stays put.
        function(){
          if(state.tab === 'events') selectEvent(name);
          else previewEvent(name);
        },
        // Double-click: only meaningful from the Metrics tab (jump to Events).
        function(){
          if(state.tab === 'events') selectEvent(name);
          else jumpToEvent(name);
        }
      );
    });
  }

  function jumpToEvent(name){
    // Switch to the Events tab and highlight the event's uarch path only
    // when the event actually has a home in the arch-map. Pseudo-events
    // (PERF_METRICS.*, TSC, RAPL) have no uarch home, so we just show
    // their detail without switching tabs.
    if(!EVENT_INDEX) buildEventIndex();
    var entry = EVENT_INDEX && EVENT_INDEX[name];
    if(entry){
      setTab('events');
      selectPath(entry.path.join('/'));
      selectEvent(name);
      var el = q('[data-path="'+entry.path.join('/')+'"]');
      if(el && el.scrollIntoView){
        try { el.scrollIntoView({block: 'center', inline: 'center', behavior: 'smooth'}); }
        catch(e){}
      }
    } else if(ARCH.events[name]){
      // No uarch home — treat like a single-click preview.
      previewEvent(name);
    }
  }

  function selectEvent(name){
    // Called from the Events tab when an event <li> is clicked or from
    // jumpToEvent(). Records the event as the "current event on the
    // Events tab" and also as the current detail subject.
    state.events.eventName = name;
    state.detail.kind = 'event';
    state.detail.name = name;
    // Clear any previously-selected li in the shared top-right pane.
    // The pane isn't nested inside #view-events, so scope directly to it.
    qa('#pane-list li.selected').forEach(function(el){ el.classList.remove('selected'); });
    var target = q('#pane-list li[data-ev="'+encodeURIComponent(name)+'"]');
    if(target) target.classList.add('selected');
    renderDetail();
  }

  function previewEvent(name){
    // Show an event in the bottom detail pane WITHOUT changing tab or
    // left-column selection. Used for single-click on feeder events from
    // the Metrics tab, and for pseudo-event double-clicks.
    state.detail.kind = 'event';
    state.detail.name = name;
    qa('#pane-list li.selected').forEach(function(el){ el.classList.remove('selected'); });
    var target = q('#pane-list li[data-ev="'+encodeURIComponent(name)+'"]');
    if(target) target.classList.add('selected');
    renderDetail();
  }

  // -------- Metrics tab: metric selection --------
  function selectMetric(name){
    state.metrics.metric = name;
    state.detail.kind = 'metric';
    state.detail.name = name;
    // If the target metric is inside a collapsed subtree, expand its ancestors
    // and re-render before we try to highlight it.
    var wasReflowed = false;
    if(tmaExpandAncestors && tmaExpandAncestors(name)){
      wasReflowed = true;
      renderTmaTree();
    }
    qa('#view-metrics .selected').forEach(function(el){ el.classList.remove('selected'); });
    var svgEl = q('[data-metric="'+cssEsc(name)+'"]');
    if(svgEl) svgEl.classList.add('selected');
    qa('#view-metrics li[data-metric="'+cssEsc(name)+'"]').forEach(function(el){
      el.classList.add('selected');
    });
    renderList();
    renderDetail();
    if(svgEl && svgEl.scrollIntoView){
      try { svgEl.scrollIntoView({block: 'center', behavior: 'smooth'}); } catch(e){}
    }
  }

  function previewMetric(name){
    // Show a metric in the bottom detail pane WITHOUT changing tab.
    state.detail.kind = 'metric';
    state.detail.name = name;
    renderDetail();
  }

  function cssEsc(s){ return String(s).replace(/"/g, '\\\\"'); }

  function renderDetail(){
    var pane = q('#pane-detail');
    if(state.detail.kind === 'event' && state.detail.name){
      renderEventDetail(pane, ARCH.events[state.detail.name]);
      return;
    }
    if(state.detail.kind === 'metric' && state.detail.name){
      renderMetricDetail(pane, ARCH.metrics[state.detail.name]);
      return;
    }
    pane.innerHTML = '<div class="empty">Select an event or metric to see its full description.</div>';
  }

  function renderEventDetail(pane, ev){
    if(!ev){ pane.innerHTML = '<div class="empty">Unknown event.</div>'; return; }
    var parts = ['<div class="event-detail">'];
    var kindBadge = ev.pseudo
        ? '<span class="pseudo-badge">pseudo-event</span>'
        : '';
    parts.push('<div class="name">'+escapeHtml(ev.name)+kindBadge+'</div>');
    parts.push('<dl>');
    if(ev.brief){ parts.push('<dt>Brief</dt><dd class="desc">'+escapeHtml(ev.brief)+'</dd>'); }
    if(ev.public && ev.public !== ev.brief){
      parts.push('<dt>'+(ev.pseudo ? 'Detail' : 'Public')+'</dt>');
      parts.push('<dd class="desc">'+escapeHtml(ev.public)+'</dd>');
    }
    if(ev.unit){ parts.push('<dt>Unit</dt><dd>'+escapeHtml(ev.unit)+'</dd>'); }
    if(ev.code){ parts.push('<dt>Event code</dt><dd>'+escapeHtml(ev.code)+'</dd>'); }
    if(ev.umask){ parts.push('<dt>UMask</dt><dd>'+escapeHtml(ev.umask)+'</dd>'); }
    if(ev.counter){ parts.push('<dt>Counter</dt><dd>'+escapeHtml(ev.counter)+'</dd>'); }
    if(ev.precise && ev.precise !== '0'){ parts.push('<dt>PEBS</dt><dd>'+escapeHtml(ev.precise)+'</dd>'); }
    if(ev.sample){ parts.push('<dt>SampleAfter</dt><dd>'+escapeHtml(ev.sample)+'</dd>'); }
    parts.push('</dl>');

    if(ev.note){
      parts.push('<div class="detail-section">');
      parts.push('<h4>'+(ev.pseudo ? 'How to read it in perf' : 'What this means')+'</h4>');
      parts.push('<div class="note">'+escapeHtml(ev.note)+'</div>');
      parts.push('</div>');
    }

    if(ev.pseudo_formula){
      parts.push('<div class="detail-section">');
      parts.push('<h4>How it is computed</h4>');
      parts.push('<div class="formula">'+escapeHtml(ev.pseudo_formula)+'</div>');
      parts.push('</div>');
    }

    if(ev.acronyms && ev.acronyms.length){
      parts.push('<div class="detail-section">');
      parts.push('<h4>Acronyms in this event</h4>');
      parts.push('<div class="acronyms">');
      ev.acronyms.forEach(function(a){
        parts.push('<div class="acronym">');
        parts.push('<span class="tok">'+escapeHtml(a.tok)+'</span> — <span class="exp">'+escapeHtml(a.exp)+'</span>');
        parts.push('<span class="gloss">'+escapeHtml(a.gloss)+'</span>');
        parts.push('</div>');
      });
      parts.push('</div></div>');
    }

    if(ev.used_by && ev.used_by.length){
      parts.push('<div class="detail-section">');
      parts.push('<h4>Used by '+ev.used_by.length+' metric'+(ev.used_by.length===1?'':'s')
        +'<span class="click-hint">single-click: preview · double-click: jump</span></h4>');
      parts.push('<div class="usedby">');
      ev.used_by.forEach(function(mname){
        parts.push('<span class="m-chip" data-jump-metric="'+encodeURIComponent(mname)+'">'+escapeHtml(mname)+'</span>');
      });
      parts.push('</div></div>');
    }

    if(ev.perf){
      parts.push('<div class="detail-section">');
      parts.push('<h4>Copy-paste perf</h4>');
      ['stat','record','raw'].forEach(function(k){
        if(!ev.perf[k]) return;
        parts.push('<div class="perf-block">');
        parts.push('<div class="lbl">'+k+'</div>');
        parts.push('<button class="copy" data-copy="'+encodeURIComponent(ev.perf[k])+'">copy</button>');
        parts.push('<pre>'+escapeHtml(ev.perf[k])+'</pre>');
        parts.push('</div>');
      });
      if(ev.perf.notes && ev.perf.notes.length){
        parts.push('<ul class="perf-notes">');
        ev.perf.notes.forEach(function(n){
          parts.push('<li>'+escapeHtml(n)+'</li>');
        });
        parts.push('</ul>');
      }
      parts.push('</div>');
    }

    // Diff-vs-baseline section (only visible when compare mode is on).
    var evStatus = diffStatusForEvent(ev.name);
    if(compareOn && evStatus && evStatus !== 'same'){
      parts.push('<div class="detail-section">');
      parts.push('<h4>Diff vs '+escapeHtml((ARCH.diff && ARCH.diff.baseline) || '?')+'</h4>');
      if(evStatus === 'new'){
        parts.push('<div class="note">New in this platform — this event does not exist in the predecessor.</div>');
      } else if(evStatus === 'changed'){
        var fields = (ARCH.diff.events_changes || {})[ev.name] || {};
        var keys = Object.keys(fields);
        if(keys.length){
          parts.push('<table class="diff-table"><thead><tr><th>Field</th><th>' +
            escapeHtml(ARCH.diff.baseline) + '</th><th>' +
            escapeHtml(ARCH.diff.baseline ? 'now' : '') + '</th></tr></thead><tbody>');
          keys.forEach(function(k){
            var lo = fields[k][0], hi = fields[k][1];
            parts.push('<tr><td>'+escapeHtml(k)+'</td>'+
              '<td class="diff-old">'+escapeHtml(lo || '—')+'</td>'+
              '<td class="diff-new-cell">'+escapeHtml(hi || '—')+'</td></tr>');
          });
          parts.push('</tbody></table>');
        } else {
          parts.push('<div class="note">Encoding differs from the predecessor.</div>');
        }
      }
      parts.push('</div>');
    }

    parts.push('</div>');
    pane.innerHTML = parts.join('');
    wireDetailCopy();
    wireDetailMetricChips();
  }

  function renderMetricDetail(pane, m){
    if(!m){ pane.innerHTML = '<div class="empty">Unknown metric.</div>'; return; }
    var parts = ['<div class="metric-detail">'];
    parts.push('<div class="name">'+escapeHtml(m.name)+'</div>');
    var bits = [];
    if(m.category) bits.push(escapeHtml(m.category));
    if(m.parent) bits.push(escapeHtml(m.parent));
    bits.push('L' + m.level);
    if(m.unit) bits.push(escapeHtml(m.unit));
    parts.push('<div class="meta">'+bits.join(' · ')+'</div>');
    if(m.brief){ parts.push('<div style="font-size:0.82rem;line-height:1.5;margin-bottom:0.5rem;">'+escapeHtml(m.brief)+'</div>'); }

    parts.push('<div class="detail-section">');
    parts.push('<h4>Formula</h4>');
    parts.push('<div class="formula">'+escapeHtml(m.formula_expanded || m.formula_raw || '(no formula)')+'</div>');
    parts.push('</div>');

    if(m.threshold_formula){
      parts.push('<div class="detail-section">');
      parts.push('<h4>Threshold</h4>');
      parts.push('<div class="threshold">'+escapeHtml(m.threshold_gloss || m.threshold_formula)+'</div>');
      if(m.threshold_issues){
        parts.push('<div style="font-size:0.7rem;color:var(--muted);margin-top:0.35rem;">Signals: '+escapeHtml(m.threshold_issues)+'</div>');
      }
      parts.push('</div>');
    }

    if(m.events && m.events.length){
      var primary = primaryFeederFor(m.name, m.events);
      parts.push('<div class="detail-section">');
      parts.push('<h4>Feeder events ('+m.events.length+')'
        +'<span class="click-hint">single-click: preview · double-click: jump</span></h4>');
      parts.push('<div class="feeders">');
      m.events.forEach(function(ename){
        var cls = (ename === primary) ? 'feeder primary' : 'feeder';
        var badges = '';
        if(ename === primary) badges += ' <span class="primary-badge">primary</span>';
        var st = diffStatusForEvent(ename);
        badges += statusBadgeHtml(st);
        parts.push('<span class="'+cls+'" data-jump-event="'+encodeURIComponent(ename)+'"'+statusAttr(st)+'>'+escapeHtml(ename)+badges+'</span>');
      });
      parts.push('</div>');
      if(primary){
        parts.push('<div style="font-size:0.7rem;color:var(--muted);margin-top:0.35rem;">'
          +'The <b>primary</b> feeder is the fixed-function counter this metric normalizes — '
          +'it is not the metric feeding into itself; PERF_METRICS.* pseudo-events are distinct from the metric definitions.</div>');
      }
      parts.push('</div>');
    }

    if(m.group){
      parts.push('<div class="detail-section">');
      parts.push('<h4>Metadata</h4>');
      parts.push('<dl>');
      parts.push('<dt>Metric group</dt><dd class="desc">'+escapeHtml(m.group)+'</dd>');
      if(m.count_domain){ parts.push('<dt>Count domain</dt><dd class="desc">'+escapeHtml(m.count_domain)+'</dd>'); }
      if(m.legacy){ parts.push('<dt>Legacy name</dt><dd>'+escapeHtml(m.legacy)+'</dd>'); }
      parts.push('</dl></div>');
    }

    var mStatus = diffStatusForMetric(m.name);
    if(compareOn && mStatus && mStatus !== 'same'){
      parts.push('<div class="detail-section">');
      parts.push('<h4>Diff vs '+escapeHtml((ARCH.diff && ARCH.diff.baseline) || '?')+'</h4>');
      if(mStatus === 'new'){
        parts.push('<div class="note">New metric on this platform — the predecessor did not define it.</div>');
      } else if(mStatus === 'changed'){
        var info = (ARCH.diff.metrics_changes || {})[m.name];
        if(info){
          if(info.formula_baseline !== info.formula_current){
            parts.push('<div class="diff-label">Baseline formula:</div>');
            parts.push('<div class="formula diff-old-block">'+escapeHtml(info.formula_baseline || '(none)')+'</div>');
            parts.push('<div class="diff-label">Current formula:</div>');
            parts.push('<div class="formula diff-new-block">'+escapeHtml(info.formula_current || '(none)')+'</div>');
          }
          if(info.events_added && info.events_added.length){
            parts.push('<div class="diff-label">Feeder events added:</div>');
            parts.push('<div class="feeders">');
            info.events_added.forEach(function(en){
              parts.push('<span class="feeder diff-new-chip">+ '+escapeHtml(en)+'</span>');
            });
            parts.push('</div>');
          }
          if(info.events_removed && info.events_removed.length){
            parts.push('<div class="diff-label">Feeder events removed:</div>');
            parts.push('<div class="feeders">');
            info.events_removed.forEach(function(en){
              parts.push('<span class="feeder diff-rem-chip">− '+escapeHtml(en)+'</span>');
            });
            parts.push('</div>');
          }
          if(info.level_current !== info.level_baseline){
            parts.push('<div class="diff-label">TMA level changed: L'+info.level_baseline+' → L'+info.level_current+'</div>');
          }
        } else {
          parts.push('<div class="note">Formula, feeder events, or level differs from the predecessor.</div>');
        }
      }
      parts.push('</div>');
    }

    parts.push('</div>');
    pane.innerHTML = parts.join('');
    wireDetailFeederChips();
    wireDetailMetricChips();
  }

  function wireDetailCopy(){
    qa('#pane-detail button.copy').forEach(function(btn){
      btn.addEventListener('click', function(e){
        e.preventDefault();
        var txt = decodeURIComponent(btn.getAttribute('data-copy'));
        if(navigator.clipboard){
          navigator.clipboard.writeText(txt).then(function(){
            btn.textContent = 'copied';
            setTimeout(function(){ btn.textContent = 'copy'; }, 1200);
          });
        }
      });
    });
  }

  function wireDetailMetricChips(){
    qa('#pane-detail .m-chip[data-jump-metric]').forEach(function(el){
      var name = decodeURIComponent(el.getAttribute('data-jump-metric'));
      bindNavClicks(
        el,
        function(){ previewMetric(name); },
        function(){ setTab('metrics'); selectMetric(name); }
      );
    });
  }

  function wireDetailFeederChips(){
    qa('#pane-detail .feeder[data-jump-event]').forEach(function(el){
      var name = decodeURIComponent(el.getAttribute('data-jump-event'));
      bindNavClicks(
        el,
        function(){ previewEvent(name); },
        function(){ jumpToEvent(name); }
      );
    });
  }

  function escapeHtml(s){
    if(s == null) return '';
    return String(s).replace(/[&<>"']/g, function(c){
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
    });
  }

  function wireSvg(){
    qa('[data-path]').forEach(function(el){
      el.addEventListener('click', function(e){
        e.preventDefault();
        e.stopPropagation();
        selectPath(el.getAttribute('data-path'));
      });
    });
    qa('[data-metric]').forEach(function(el){
      el.addEventListener('click', function(e){
        e.preventDefault();
        e.stopPropagation();
        selectMetric(el.getAttribute('data-metric'));
      });
    });
  }

  // -------- Populate metrics tab sidebar lists --------
  // ============================================================
  // TMA tree — layout + render in JS, so expand/collapse can re-flow
  // ============================================================
  var TMA_CFG = {
    LEAF_W: 118, LEAF_GAP: 8,
    NODE_H: 28, ROW_H: 62,
    TOP_PAD: 24, LEFT_PAD: 24, BOTTOM_PAD: 24,
    INTER_ROOT_GAP: 34,
    // Nodes at depth ≥ COLLAPSE_DEPTH start collapsed. depth is 0-based within
    // an L1 subtree, so depth=1 means L2 (children of the L1 root). The default
    // shows L1 and L2 open, hides L3+.
    COLLAPSE_DEPTH: 1,
  };

  // Collapsed set — keyed by metric name. If a name is in this set, its
  // children are hidden.
  var TMA_COLLAPSED = new Set();

  function tmaInitCollapse(){
    TMA_COLLAPSED.clear();
    function walk(node, depth){
      // Collapse this node if it's internal AND at/beyond COLLAPSE_DEPTH.
      if(node.children && node.children.length && depth >= TMA_CFG.COLLAPSE_DEPTH){
        TMA_COLLAPSED.add(node.name);
      }
      (node.children || []).forEach(function(c){ walk(c, depth + 1); });
    }
    (ARCH.tma_roots || []).forEach(function(r){ walk(r, 0); });
  }

  function tmaIsCollapsed(name){ return TMA_COLLAPSED.has(name); }

  // Layout a subtree starting at cursorX. Returns width; appends layout rows.
  function tmaLayoutSubtree(node, depth, cursorX, rows){
    var effChildren = (node.children && !tmaIsCollapsed(node.name)) ? node.children : [];
    if(effChildren.length === 0){
      var w = TMA_CFG.LEAF_W;
      rows.push({
        node: node, depth: depth,
        cx: cursorX + w / 2,
        y: TMA_CFG.TOP_PAD + depth * TMA_CFG.ROW_H,
        collapsed: tmaIsCollapsed(node.name) && (node.children||[]).length > 0,
      });
      return w;
    }
    var childStart = cursorX;
    var childCxs = [];
    for(var i = 0; i < effChildren.length; i++){
      if(i > 0) childStart += TMA_CFG.LEAF_GAP;
      var cw = tmaLayoutSubtree(effChildren[i], depth + 1, childStart, rows);
      childCxs.push(childStart + cw / 2);
      childStart += cw;
    }
    var subtreeW = childStart - cursorX;
    if(subtreeW < TMA_CFG.LEAF_W){
      var shift = (TMA_CFG.LEAF_W - subtreeW) / 2;
      var descendants = tmaCountLive(node) - 1;
      for(var k = rows.length - descendants; k < rows.length; k++){
        rows[k].cx += shift;
      }
      for(var j = 0; j < childCxs.length; j++) childCxs[j] += shift;
      subtreeW = TMA_CFG.LEAF_W;
    }
    var parentCx = (childCxs[0] + childCxs[childCxs.length - 1]) / 2;
    rows.push({
      node: node, depth: depth,
      cx: parentCx,
      y: TMA_CFG.TOP_PAD + depth * TMA_CFG.ROW_H,
      collapsed: false,
    });
    return subtreeW;
  }

  // Count nodes in a subtree that would render right now (respects collapse).
  function tmaCountLive(node){
    if(!node.children || tmaIsCollapsed(node.name)) return 1;
    var n = 1;
    for(var i = 0; i < node.children.length; i++){
      n += tmaCountLive(node.children[i]);
    }
    return n;
  }

  function tmaMaxDepth(rows){
    var d = 0;
    for(var i = 0; i < rows.length; i++){
      if(rows[i].depth > d) d = rows[i].depth;
    }
    return d;
  }

  function tmaEscape(s){
    return String(s || '').replace(/[&<>"']/g, function(c){
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
    });
  }

  function tmaShort(s, n){
    if(s.length <= n) return s;
    return s.slice(0, n - 1) + '…';
  }

  function renderTmaTree(){
    var container = q('#tma-svg-container');
    if(!container) return;
    var roots = ARCH.tma_roots || [];
    if(!roots.length){ container.innerHTML = ''; return; }

    // Lay out each L1 root's subtree standalone, then stack vertically.
    var subtrees = [];
    var maxSubtreeW = 0;
    roots.forEach(function(root){
      var rows = [];
      var w = tmaLayoutSubtree(root, 0, TMA_CFG.LEFT_PAD, rows);
      subtrees.push({rows: rows, width: w, root: root});
      maxSubtreeW = Math.max(maxSubtreeW, Math.round(w + 2 * TMA_CFG.LEFT_PAD));
    });

    var canvasW = Math.max(320, maxSubtreeW);
    var yOffset = TMA_CFG.TOP_PAD;
    subtrees.forEach(function(st){
      for(var i = 0; i < st.rows.length; i++){
        st.rows[i].y += yOffset - TMA_CFG.TOP_PAD;
      }
      var d = tmaMaxDepth(st.rows);
      yOffset += (d + 1) * TMA_CFG.ROW_H + TMA_CFG.INTER_ROOT_GAP;
    });
    // Centre each subtree horizontally in the canvas.
    subtrees.forEach(function(st){
      var pad = (canvasW - st.width) / 2 - TMA_CFG.LEFT_PAD;
      if(pad > 0){
        for(var i = 0; i < st.rows.length; i++) st.rows[i].cx += pad;
      }
    });
    var canvasH = yOffset - TMA_CFG.INTER_ROOT_GAP + TMA_CFG.BOTTOM_PAD;

    var parts = [
      '<svg viewBox="0 0 '+canvasW+' '+canvasH+'" width="'+canvasW+'" height="'+canvasH+'" role="img">'
    ];

    // Root separators
    var yCursor = TMA_CFG.TOP_PAD;
    for(var s = 0; s < subtrees.length - 1; s++){
      var d = tmaMaxDepth(subtrees[s].rows);
      yCursor += (d + 1) * TMA_CFG.ROW_H;
      var sepY = yCursor + TMA_CFG.INTER_ROOT_GAP / 2;
      parts.push('<line class="tma-root-sep" x1="0" y1="'+sepY+'" x2="'+canvasW+'" y2="'+sepY+'"/>');
      yCursor += TMA_CFG.INTER_ROOT_GAP;
    }

    // Index rows by node reference for connector lookup.
    var allRows = [];
    subtrees.forEach(function(st){ st.rows.forEach(function(r){ allRows.push(r); }); });
    var rowByNode = new Map();
    allRows.forEach(function(r){ rowByNode.set(r.node, r); });

    // Elbow connectors behind boxes
    parts.push('<g class="tma-connectors">');
    allRows.forEach(function(r){
      var node = r.node;
      // No connector for leaves (children empty) or collapsed nodes.
      if(!node.children || !node.children.length || tmaIsCollapsed(node.name)) return;
      var pcx = r.cx;
      var pbot = r.y + TMA_CFG.NODE_H;
      var busY = r.y + TMA_CFG.NODE_H + (TMA_CFG.ROW_H - TMA_CFG.NODE_H) / 2;
      parts.push('<path class="tma-connector" d="M '+pcx+' '+pbot+' L '+pcx+' '+busY+'"/>');
      var childCxs = node.children.map(function(c){ return rowByNode.get(c).cx; });
      if(childCxs.length > 1){
        parts.push('<path class="tma-connector" d="M '+Math.min.apply(null, childCxs)+' '+busY+' L '+Math.max.apply(null, childCxs)+' '+busY+'"/>');
      }
      childCxs.forEach(function(cx){
        parts.push('<path class="tma-connector" d="M '+cx+' '+busY+' L '+cx+' '+(r.y + TMA_CFG.ROW_H)+'"/>');
      });
    });
    parts.push('</g>');

    // Node boxes
    allRows.forEach(function(r){
      var node = r.node;
      var isInternal = !!(node.children && node.children.length);
      var collapsed = tmaIsCollapsed(node.name);
      var hasThr = false;
      var m = ARCH.metrics[node.name];
      if(m && m.threshold_formula) hasThr = true;
      var cls = ['tma-node'];
      if(hasThr) cls.push('has-thr');
      if(collapsed) cls.push('collapsed');
      var w = TMA_CFG.LEAF_W;
      var x = r.cx - w / 2;
      var y = r.y;
      var label = tmaShort(node.name, 15);
      var lvlBits = 'L' + node.level;
      if(hasThr) lvlBits += ' ⚑';
      var st = diffStatusForMetric(node.name);
      parts.push('<g class="'+cls.join(' ')+'" data-metric="'+tmaEscape(node.name)+'"'+statusAttr(st)+'>');
      parts.push('<rect x="'+x+'" y="'+y+'" width="'+w+'" height="'+TMA_CFG.NODE_H+'" rx="4"/>');
      parts.push('<text class="title" x="'+r.cx+'" y="'+(y + 14)+'" text-anchor="middle">'+tmaEscape(label)+'</text>');
      // Always emit the "Lx ⚑" label; when compare mode is on, applyTmaDiffLabels()
      // will inject a sibling <text class="node-diff"> at the same coords and
      // CSS (body.cmp-on text.lvl) will hide the level label. Doing this via
      // DOM manipulation post-render avoids an HTML-parser quirk where tspans
      // inside an initially-parsed <text> can get dropped.
      parts.push('<text class="lvl" x="'+r.cx+'" y="'+(y + 24)+'" text-anchor="middle">'+tmaEscape(lvlBits)+'</text>');
      parts.push('<title>'+tmaEscape(node.name)+'</title>');
      if(isInternal){
        // Toggle glyph pinned to the top-right corner of the box.
        var tx = x + w - 8, ty = y + 4;
        var glyph = collapsed ? '+' : '−';
        parts.push('<g class="tma-toggle" data-toggle="'+tmaEscape(node.name)+'">');
        parts.push('<circle cx="'+tx+'" cy="'+ty+'" r="7"/>');
        parts.push('<text x="'+tx+'" y="'+(ty + 1)+'">'+glyph+'</text>');
        parts.push('</g>');
      }
      parts.push('</g>');
    });

    parts.push('</svg>');
    container.innerHTML = parts.join('');
    wireTmaClicks();

    // Re-apply selection highlight if state.metrics.metric exists
    if(state.metrics.metric){
      var el = q('[data-metric="'+cssEsc(state.metrics.metric)+'"]');
      if(el) el.classList.add('selected');
    }
    // Overlay subtree-rollup diff labels in place of the "Lx ⚑" label.
    applyTmaDiffLabels();
  }

  function wireTmaClicks(){
    // Node click = select metric. Toggle click stops propagation and re-lays out.
    qa('#tma-svg-container [data-metric]').forEach(function(el){
      el.addEventListener('click', function(e){
        e.preventDefault(); e.stopPropagation();
        selectMetric(el.getAttribute('data-metric'));
      });
    });
    qa('#tma-svg-container [data-toggle]').forEach(function(el){
      el.addEventListener('click', function(e){
        e.preventDefault(); e.stopPropagation();
        var name = el.getAttribute('data-toggle');
        if(TMA_COLLAPSED.has(name)) TMA_COLLAPSED.delete(name);
        else TMA_COLLAPSED.add(name);
        renderTmaTree();
      });
    });
    qa('.tma-btn[data-tma-action]').forEach(function(btn){
      btn.addEventListener('click', function(){
        var act = btn.getAttribute('data-tma-action');
        if(act === 'expand-all'){
          TMA_COLLAPSED.clear();
        } else if(act === 'collapse-all'){
          TMA_COLLAPSED.clear();
          // Collapse every node at or beyond L2 (depth 1)
          function walk(node, depth){
            if(node.children && node.children.length && depth >= 1){
              TMA_COLLAPSED.add(node.name);
            }
            (node.children || []).forEach(function(c){ walk(c, depth+1); });
          }
          (ARCH.tma_roots || []).forEach(function(r){ walk(r, 0); });
        }
        renderTmaTree();
      });
    });
  }

  // Expand ancestors of the given metric so its node is visible in the tree.
  function tmaExpandAncestors(metricName){
    if(!ARCH.tma_roots || !ARCH.tma_roots.length) return false;
    var found = false;
    function walk(node, ancestors){
      if(node.name === metricName){
        ancestors.forEach(function(a){ TMA_COLLAPSED.delete(a.name); });
        found = true;
        return true;
      }
      var kids = node.children || [];
      for(var i = 0; i < kids.length; i++){
        if(walk(kids[i], ancestors.concat([node]))) return true;
      }
      return false;
    }
    ARCH.tma_roots.some(function(r){ return walk(r, []); });
    return found;
  }

  // Compute a total-badge value for a list of metric names. In compare
  // mode, returns coloured HTML "+N ~M -K"; otherwise the raw count.
  function metricListBadge(names){
    if(!compareOn || !ARCH.diff || !ARCH.diff.metrics_diff_available){
      return String(names.length);
    }
    var n = 0, c = 0, x = 0;
    names.forEach(function(name){
      var st = diffStatusForMetric(name);
      if(st === 'new') n++;
      else if(st === 'changed') c++;
    });
    // Removed metrics show up separately in their own sidebar block
    // (handled by renderRemovedSections). Skip counting them here.
    if(n === 0 && c === 0 && x === 0) return String(names.length);
    var parts = [];
    if(n > 0) parts.push('<span class="diff-new">+' + n + '</span>');
    if(c > 0) parts.push('<span class="diff-chg">~' + c + '</span>');
    if(x > 0) parts.push('<span class="diff-rem">-' + x + '</span>');
    return parts.join(' ');
  }

  // Collect every TMA-tree metric name (flatten the roots).
  function tmaAllNodeNames(){
    var out = [];
    function walk(node){ out.push(node.name); (node.children||[]).forEach(walk); }
    (ARCH.tma_roots || []).forEach(walk);
    return out;
  }

  function renderMetricsSidebar(){
    // TMA Hierarchy header badge: total in normal mode, +/~/- in compare.
    var tmaCount = q('#tma-count');
    if(tmaCount){
      var names = tmaAllNodeNames();
      tmaCount.innerHTML = names.length ? metricListBadge(names) : '0';
      // Hide the badge on platforms with no TMA tree (CWF).
      tmaCount.style.display = names.length ? '' : 'none';
    }
    // Bottlenecks
    var bcount = q('#bottleneck-count');
    var blist = q('#bottleneck-list');
    if(ARCH.bottlenecks && ARCH.bottlenecks.length){
      bcount.innerHTML = metricListBadge(ARCH.bottlenecks);
      blist.innerHTML = ARCH.bottlenecks.map(function(name){
        var st = diffStatusForMetric(name);
        return '<li data-metric="'+escapeHtml(name)+'"'+statusAttr(st)+'>'+escapeHtml(name)+statusBadgeHtml(st)+'</li>';
      }).join('');
    } else {
      q('#bottleneck-block').style.display = 'none';
    }
    // Info groups
    var iBlock = q('#info-block');
    var iCount = q('#info-count');
    var iContainer = q('#info-groups');
    var infoGroups = ARCH.info_groups || {};
    var infoNames = Object.keys(infoGroups);
    if(infoNames.length){
      var total = 0;
      var allNames = [];
      var parts = [];
      infoNames.sort().forEach(function(g){
        var items = infoGroups[g];
        total += items.length;
        allNames = allNames.concat(items);
        parts.push('<div class="group-title">'+escapeHtml(g)+' ('+items.length+')</div>');
        parts.push('<ul class="metric-list">');
        items.forEach(function(name){
          var st = diffStatusForMetric(name);
          parts.push('<li data-metric="'+escapeHtml(name)+'"'+statusAttr(st)+'>'+escapeHtml(name)+statusBadgeHtml(st)+'</li>');
        });
        parts.push('</ul>');
      });
      iCount.innerHTML = metricListBadge(allNames);
      iContainer.innerHTML = parts.join('');
    } else {
      iBlock.style.display = 'none';
    }
    // Non-TMA (CWF-style)
    var nBlock = q('#nontma-block');
    var nCount = q('#nontma-count');
    var nContainer = q('#nontma-groups');
    var nonTma = ARCH.non_tma_categories || {};
    var nKeys = Object.keys(nonTma);
    if(nKeys.length){
      var nTotal = 0;
      var nAllNames = [];
      var nParts = [];
      nKeys.sort().forEach(function(g){
        var items = nonTma[g];
        nTotal += items.length;
        nAllNames = nAllNames.concat(items);
        nParts.push('<div class="group-title">'+escapeHtml(g || 'Uncategorized')+' ('+items.length+')</div>');
        nParts.push('<ul class="metric-list">');
        items.forEach(function(name){
          var st = diffStatusForMetric(name);
          nParts.push('<li data-metric="'+escapeHtml(name)+'"'+statusAttr(st)+'>'+escapeHtml(name)+statusBadgeHtml(st)+'</li>');
        });
        nParts.push('</ul>');
      });
      nCount.innerHTML = metricListBadge(nAllNames);
      nContainer.innerHTML = nParts.join('');
    } else {
      nBlock.style.display = 'none';
    }
    // Wire clicks
    qa('#view-metrics li[data-metric]').forEach(function(li){
      li.addEventListener('click', function(){ selectMetric(li.getAttribute('data-metric')); });
    });
  }

  // -------- Search (events + metrics) --------
  var EVENT_INDEX = null;   // {eventName: {path: [ids], titlePath: 'a › b › c'}}
  var suggestions = [];
  var activeIdx = -1;

  function buildEventIndex(){
    EVENT_INDEX = {};
    function walk(node, path, titles){
      var kids = node.subs || [];
      if(kids.length === 0){
        (node.events || []).forEach(function(name){
          EVENT_INDEX[name] = {path: path.slice(), titlePath: titles.join(' › ')};
        });
        return;
      }
      kids.forEach(function(k){
        walk(k, path.concat([k.id]), titles.concat([k.title]));
      });
    }
    Object.keys(ARCH.cells).forEach(function(cid){
      var cell = ARCH.cells[cid];
      walk(cell, [cid], [cell.title]);
    });
  }

  function search(query){
    if(!EVENT_INDEX) buildEventIndex();
    query = (query || '').trim().toUpperCase();
    if(!query){ return []; }
    var results = [];
    // Events
    var enames = Object.keys(EVENT_INDEX);
    for(var i = 0; i < enames.length; i++){
      var n = enames[i];
      var idx = n.toUpperCase().indexOf(query);
      if(idx !== -1){
        results.push({kind: 'event', name: n, idx: idx, len: n.length});
      }
    }
    // Metrics
    var mnames = Object.keys(ARCH.metrics || {});
    for(var j = 0; j < mnames.length; j++){
      var mn = mnames[j];
      var mi = mn.toUpperCase().indexOf(query);
      if(mi !== -1){
        results.push({kind: 'metric', name: mn, idx: mi, len: mn.length});
      }
    }
    // Rank: startsWith first, then shorter names first
    results.sort(function(a, b){
      if((a.idx === 0) !== (b.idx === 0)) return a.idx === 0 ? -1 : 1;
      if(a.idx !== b.idx) return a.idx - b.idx;
      return a.len - b.len;
    });
    return results.slice(0, 40);
  }

  function renderSuggestions(query){
    var box = q('#search-suggestions');
    suggestions = search(query);
    activeIdx = -1;
    if(!query){
      box.classList.remove('open');
      box.innerHTML = '';
      return;
    }
    if(suggestions.length === 0){
      box.innerHTML = '<div class="search-empty">No matching events or metrics.</div>';
      box.classList.add('open');
      return;
    }
    var parts = [];
    suggestions.forEach(function(s, i){
      var pos = s.idx;
      var pre = escapeHtml(s.name.slice(0, pos));
      var hit = escapeHtml(s.name.slice(pos, pos + query.length));
      var post = escapeHtml(s.name.slice(pos + query.length));
      var sub = '';
      if(s.kind === 'event'){
        var entry = EVENT_INDEX[s.name];
        sub = entry ? entry.titlePath : '';
      } else {
        var m = ARCH.metrics[s.name];
        sub = m ? ('metric · L' + m.level + (m.category ? ' · ' + m.category : '')) : 'metric';
      }
      parts.push('<div class="item" data-i="'+i+'">');
      parts.push('<span style="opacity:0.55;font-size:0.68rem;text-transform:uppercase;margin-right:0.35rem;">'+s.kind+'</span>');
      parts.push(pre + '<mark>' + hit + '</mark>' + post);
      parts.push('<span class="path">'+escapeHtml(sub)+'</span>');
      parts.push('</div>');
    });
    box.innerHTML = parts.join('');
    box.classList.add('open');
    qa('#search-suggestions .item').forEach(function(el){
      el.addEventListener('mousedown', function(e){
        e.preventDefault();
        pickSuggestion(parseInt(el.getAttribute('data-i'), 10));
      });
    });
  }

  function pickSuggestion(i){
    var s = suggestions[i];
    if(!s) return;
    q('#search-input').value = s.name;
    q('#search-suggestions').classList.remove('open');
    if(s.kind === 'event'){
      var entry = EVENT_INDEX[s.name];
      if(!entry) return;
      setTab('events');
      selectPath(entry.path.join('/'));
      selectEvent(s.name);
      var el = q('[data-path="'+entry.path.join('/')+'"]');
      if(el && el.scrollIntoView){
        try { el.scrollIntoView({block: 'center', inline: 'center', behavior: 'smooth'}); }
        catch(e){}
      }
    } else {
      setTab('metrics');
      selectMetric(s.name);
    }
  }

  function highlightActive(){
    qa('#search-suggestions .item').forEach(function(el, i){
      el.classList.toggle('active', i === activeIdx);
    });
    var active = q('#search-suggestions .item.active');
    if(active && active.scrollIntoView) active.scrollIntoView({block: 'nearest'});
  }

  function wireSearch(){
    var input = q('#search-input');
    if(!input) return;
    var box = q('#search-suggestions');
    var t;
    input.addEventListener('input', function(){
      clearTimeout(t);
      t = setTimeout(function(){ renderSuggestions(input.value); }, 40);
    });
    input.addEventListener('keydown', function(e){
      if(!box.classList.contains('open')) return;
      if(e.key === 'ArrowDown'){
        e.preventDefault();
        activeIdx = Math.min(activeIdx + 1, suggestions.length - 1);
        highlightActive();
      } else if(e.key === 'ArrowUp'){
        e.preventDefault();
        activeIdx = Math.max(activeIdx - 1, 0);
        highlightActive();
      } else if(e.key === 'Enter'){
        e.preventDefault();
        if(activeIdx >= 0) pickSuggestion(activeIdx);
        else if(suggestions.length) pickSuggestion(0);
      } else if(e.key === 'Escape'){
        box.classList.remove('open');
      }
    });
    input.addEventListener('blur', function(){
      setTimeout(function(){ box.classList.remove('open'); }, 150);
    });
    input.addEventListener('focus', function(){
      if(input.value) renderSuggestions(input.value);
    });
  }

  addEventListener('DOMContentLoaded', function(){
    wireTabs();
    wireSvg();
    wireSearch();
    tmaInitCollapse();
    initCompareToggle();
    renderTmaTree();
    renderMetricsSidebar();
    renderRemovedSections();
    renderList();
    renderDetail();
    // If compare is on by default, decorate the SVGs now that they exist.
    if(compareOn) applyStatusToDom();
  });
})();
"""


# ---------------------------------------------------------------------------
# Recursive box sizing and rendering.
#
# A node (Cell or SubComponent) with no children renders as a leaf box.
# A node with children renders as a container that contains a grid of child
# boxes; each child recurses. Sizes cascade bottom-up.
# ---------------------------------------------------------------------------

# Leaf box footprint (deepest level; no grandchildren).
LEAF_W = 155
LEAF_H = 32

# Padding for containers at various depths.
PAD_TITLE = {1: 26, 2: 22, 3: 20}       # top padding for the title bar
PAD_BOTTOM = {1: 10, 2: 8, 3: 8}
PAD_X = {1: 10, 2: 8, 3: 6}
GAP_X = {1: 8, 2: 6, 3: 4}
GAP_Y = {1: 6, 2: 5, 3: 4}

# Font styling per depth (title, count) applied via CSS class.
TITLE_FONT = {1: 12, 2: 11, 3: 10, 4: 9}


def _short(text: str, maxlen: int = 22) -> str:
    if len(text) <= maxlen:
        return text
    return text[: maxlen - 1] + "…"


def _cols_hint_for_depth(n_children: int, depth: int) -> int:
    """How many columns to lay children in, based on child count and depth."""
    if n_children <= 1:
        return 1
    if depth == 1:
        return min(2, n_children)
    if depth == 2:
        return min(3, n_children)
    if depth >= 3:
        # deep leaves get compact grids
        if n_children <= 4:
            return min(2, n_children)
        return min(3, n_children)
    return 2


def _node_size(node, depth: int) -> tuple:
    """Return (w, h) for a node at the given depth."""
    kids = getattr(node, "subcomponents", []) or []
    if not kids:
        return (LEAF_W, LEAF_H)
    cols_hint = _cols_hint_for_depth(len(kids), depth)
    # Compute child sizes
    child_dims = [_node_size(k, depth + 1) for k in kids]
    cols = cols_hint
    rows = (len(kids) + cols - 1) // cols
    # Row heights: max height per row
    row_heights = []
    col_widths = [0] * cols
    for r in range(rows):
        row_slice = child_dims[r * cols:(r + 1) * cols]
        row_heights.append(max(h for _, h in row_slice))
        for c, (w, _) in enumerate(row_slice):
            col_widths[c] = max(col_widths[c], w)
    total_w = sum(col_widths) + GAP_X[min(depth, 3)] * (cols - 1)
    total_h = sum(row_heights) + GAP_Y[min(depth, 3)] * (rows - 1)
    w = total_w + 2 * PAD_X[min(depth, 3)]
    h = PAD_TITLE[min(depth, 3)] + total_h + PAD_BOTTOM[min(depth, 3)]
    return (max(w, 180), h)


def _render_node(x: int, y: int, node, path: tuple, depth: int,
                 empty: bool = False, force_width: Optional[int] = None) -> tuple:
    """Render a node at (x,y). Return (svg_str, width, height).

    depth=1 for a top-level cell, depth=2 for its subcomponents, etc.
    path is the tuple of ids from root down to this node.
    """
    w, h = _node_size(node, depth)
    if force_width:
        w = max(w, force_width)

    path_str = "/".join(path)
    is_leaf = not (getattr(node, "subcomponents", []) or [])

    # Class hierarchy: depth-1 = cell, depth-2+ = sub (styled the same)
    if depth == 1:
        cls = "cell empty" if empty else "cell"
    else:
        cls = "sub"

    parts = [f'<g class="{cls}" data-path="{path_str}" data-depth="{depth}">']
    parts.append(
        f'<rect class="cell-frame" x="{x}" y="{y}" width="{w}" height="{h}" rx="{6 if depth == 1 else 4}"/>'
    )
    font_size = TITLE_FONT.get(depth, 9)
    title_text = html.escape(_short(node.title, maxlen=32 if depth == 1 else 24))
    parts.append(
        f'<text class="node-title" x="{x + PAD_X[min(depth,3)]}" y="{y + font_size + 4}" '
        f'style="font-size:{font_size}px">{title_text}</text>'
    )
    parts.append(
        f'<text class="node-count" x="{x + w - PAD_X[min(depth,3)]}" y="{y + font_size + 4}" '
        f'text-anchor="end" style="font-size:{max(font_size - 1, 8)}px">{node.count}</text>'
    )

    if is_leaf:
        parts.append('</g>')
        return "\n".join(parts), w, h

    # Container: lay out children in a grid, centered
    kids = node.subcomponents
    cols_hint = _cols_hint_for_depth(len(kids), depth)
    cols = cols_hint
    rows = (len(kids) + cols - 1) // cols
    child_dims = [_node_size(k, depth + 1) for k in kids]

    row_heights = []
    col_widths = [0] * cols
    for r in range(rows):
        row_slice = child_dims[r * cols:(r + 1) * cols]
        row_heights.append(max(hh for _, hh in row_slice))
        for c, (ww, _) in enumerate(row_slice):
            col_widths[c] = max(col_widths[c], ww)

    grid_w = sum(col_widths) + GAP_X[min(depth, 3)] * (cols - 1)
    grid_h = sum(row_heights) + GAP_Y[min(depth, 3)] * (rows - 1)

    start_x = x + (w - grid_w) // 2
    start_y = y + PAD_TITLE[min(depth, 3)]

    # Row cursor
    cursor_y = start_y
    for r in range(rows):
        cursor_x = start_x
        for c in range(cols):
            i = r * cols + c
            if i >= len(kids):
                break
            child = kids[i]
            cw = col_widths[c]
            svg, _, _ = _render_node(
                cursor_x, cursor_y, child,
                path=path + (child.id,), depth=depth + 1,
                force_width=cw,
            )
            parts.append(svg)
            cursor_x += cw + GAP_X[min(depth, 3)]
        cursor_y += row_heights[r] + GAP_Y[min(depth, 3)]

    parts.append('</g>')
    return "\n".join(parts), w, h


def _cell_size(cell, cols_hint: int = 2) -> tuple:  # noqa: ARG001
    """Back-compat alias: returns the cell's total size."""
    return _node_size(cell, depth=1)


def _render_cell(x, y, cell, cols_hint=2, empty=False, force_width=None):
    """Back-compat wrapper — renders a top-level cell (depth=1)."""
    svg, w, h = _render_node(x, y, cell, path=(cell.id,), depth=1,
                             empty=empty, force_width=force_width)
    return svg, w, h


def _arrow_defs():
    return '''<defs>
    <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="#94a3b8"/>
    </marker>
  </defs>'''


def _by_id(cells: list) -> dict:
    return {c.id: c for c in cells}


# ---------------------------------------------------------------------------
# Core P-core layout
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# TMA tree renderer.
# The actual top-down layout runs in JavaScript so the user can toggle
# expand/collapse without a page round-trip. Python only emits a container.
# ---------------------------------------------------------------------------

def render_tma_svg(tree: TmaTree, target_width: int,
                   metrics_header: Optional[dict] = None) -> str:
    """Emit a placeholder container. The actual TMA tree is laid out and
    rendered in JavaScript (see PAGE_JS::renderTmaTree) so the user can
    toggle expand/collapse without a round-trip.

    On platforms whose metrics JSON does not (yet) define a TMA tree, we
    render a data-driven explanation instead — the metrics-file header
    tells us which version shipped and whether TmaVersion is empty.
    """
    if not tree.roots:
        return _render_tma_placeholder(target_width, metrics_header)
    # Real trees are rendered by JS at DOMContentLoaded time.
    return (
        '<div class="tma-toolbar">'
        '<button class="tma-btn" data-tma-action="expand-all">Expand all</button>'
        '<button class="tma-btn" data-tma-action="collapse-all">Collapse to L2</button>'
        '<span class="tma-hint">Click <b>+</b>/<b>−</b> on a node to toggle its subtree.</span>'
        '</div>'
        '<div id="tma-svg-container"></div>'
    )


def _render_tma_placeholder(target_width: int,
                            metrics_header: Optional[dict]) -> str:
    """Explain, using the metrics-file header, why this platform has no TMA
    hierarchy. Falls back to a generic message if the header is unavailable."""
    header = metrics_header or {}
    version = header.get("Version") or ""
    date = header.get("DatePublished") or ""
    tma_version = (header.get("TmaVersion") or "").strip()
    tma_flavor = (header.get("TmaFlavor") or "").strip()

    lines = []
    if tma_version:
        # Shouldn't reach here (tree.roots would be populated) but handle it.
        lines.append(f'This platform advertises TMA v{tma_version} '
                     f'({tma_flavor or "unknown flavor"}) but no tree metrics were parsed.')
    else:
        lines.append("Intel has not yet published TMA formulas for this platform.")
        details = []
        if version:
            details.append(f"metrics-file v{version}")
        if date:
            details.append(f"published {date}")
        details.append("TmaVersion field is empty")
        lines.append(" (" + ", ".join(details) + ")")
    lines.append("A TMA tree is expected in a future upstream metrics release.")

    text = "".join(lines)
    # SVG can't wrap text easily; use a foreignObject-like approach with two
    # tspan lines for a graceful two-line fallback.
    svg_h = 120
    return (
        f'<svg viewBox="0 0 {target_width} {svg_h}" width="{target_width}" '
        f'height="{svg_h}" role="img">'
        f'<text x="{target_width // 2}" y="42" class="tma-empty" '
        f'text-anchor="middle">{html.escape(lines[0] + lines[1] if len(lines) > 1 else lines[0])}</text>'
        f'<text x="{target_width // 2}" y="74" class="tma-empty-sub" '
        f'text-anchor="middle">{html.escape(lines[-1])}</text>'
        f'</svg>'
    )


def _core_canvas_width(cells: list, is_ecore: bool = False) -> int:
    """Compute the total width of the core diagram — used to size the uncore
    canvas to match, so both diagrams render at identical scale."""
    by_id = _by_id(cells)
    row1 = [by_id["fe_fetch"], by_id["fe_decode"], by_id["be_alloc"], by_id["be_execute"]]
    row1_w = [max(200, _cell_size(c, cols_hint=2)[0]) for c in row1]
    misc_w = _cell_size(by_id["misc_pmu"], cols_hint=1)[0]
    gap = 24
    left = 30
    return left + sum(row1_w) + gap * (len(row1_w) - 1) + gap + misc_w + gap


def render_core_svg_pcore(cells: list) -> str:
    by_id = _by_id(cells)
    row1 = [by_id["fe_fetch"], by_id["fe_decode"], by_id["be_alloc"], by_id["be_execute"]]
    row1_dims = [_cell_size(c, cols_hint=2) for c in row1]
    row1_h = max(h for _, h in row1_dims)
    row1_w = [max(200, w) for w, _ in row1_dims]

    bad_spec = by_id["bad_spec"]
    mem_l1 = by_id["mem_l1"]
    mem_l2 = by_id["mem_l2"]
    mem_l3 = by_id["mem_l3"]
    misc = by_id["misc_pmu"]
    unc = by_id["unclassified"]

    bs_w, bs_h = _cell_size(bad_spec, cols_hint=1)
    l1_w, l1_h = _cell_size(mem_l1, cols_hint=2)
    l2_w, l2_h = _cell_size(mem_l2, cols_hint=1)
    l3_w, l3_h = _cell_size(mem_l3, cols_hint=3)
    misc_w, misc_h = _cell_size(misc, cols_hint=1)

    gap = 24
    left = 30
    xs = [left]
    for w in row1_w[:-1]:
        xs.append(xs[-1] + w + gap)
    canvas_w = xs[-1] + row1_w[-1] + gap + misc_w + gap

    y1 = 32
    y2 = y1 + row1_h + 50
    y3 = y2 + max(bs_h, l1_h) + 34
    y4 = y3 + l2_h + 34
    canvas_h = y4 + l3_h + 30

    parts = [f'<svg viewBox="0 0 {canvas_w} {canvas_h}" width="{canvas_w}" height="{canvas_h}" role="img">']
    parts.append(_arrow_defs())

    for cell, x, w in zip(row1, xs, row1_w):
        svg, _, _ = _render_cell(x, y1, cell, cols_hint=2, force_width=w)
        parts.append(svg)
    parts.append('<g class="flow">')
    for i in range(3):
        parts.append(
            f'<line x1="{xs[i] + row1_w[i]}" y1="{y1 + row1_h/2}" x2="{xs[i+1] - 4}" y2="{y1 + row1_h/2}" marker-end="url(#arrow)"/>'
        )
    parts.append('</g>')

    bs_x = xs[2] + (row1_w[2] - bs_w) // 2
    svg, _, _ = _render_cell(bs_x, y2, bad_spec, cols_hint=1)
    parts.append(svg)
    l1_x = xs[3] + (row1_w[3] - l1_w) // 2
    svg, _, _ = _render_cell(l1_x, y2, mem_l1, cols_hint=2)
    parts.append(svg)

    parts.append('<g class="flow control">')
    parts.append(
        f'<line x1="{xs[2] + row1_w[2]/2}" y1="{y1 + row1_h}" x2="{xs[2] + row1_w[2]/2}" y2="{y2 - 4}" marker-end="url(#arrow)"/>'
    )
    parts.append(
        f'<path d="M {bs_x} {y2 + bs_h/2} L 15 {y2 + bs_h/2} L 15 {y1 + row1_h/2} L {xs[0] - 4} {y1 + row1_h/2}" marker-end="url(#arrow)"/>'
    )
    parts.append(f'<text x="20" y="{y1 + row1_h + 40}" class="flow-label">flush</text>')
    parts.append('</g>')

    parts.append('<g class="flow">')
    ex_cx = xs[3] + row1_w[3] / 2
    parts.append(
        f'<line x1="{ex_cx - 10}" y1="{y1 + row1_h}" x2="{ex_cx - 10}" y2="{y2 - 4}" marker-end="url(#arrow)"/>'
    )
    parts.append(
        f'<line x1="{ex_cx + 10}" y1="{y2 - 4}" x2="{ex_cx + 10}" y2="{y1 + row1_h}" marker-end="url(#arrow)"/>'
    )
    parts.append(f'<text x="{ex_cx + 20}" y="{(y1 + row1_h + y2)/2 + 4}" class="flow-label">ld/st</text>')
    parts.append('</g>')

    l2_x = l1_x + (l1_w - l2_w) // 2
    svg, _, _ = _render_cell(l2_x, y3, mem_l2, cols_hint=1)
    parts.append(svg)
    parts.append('<g class="flow">')
    l1_cx = l1_x + l1_w / 2
    parts.append(
        f'<line x1="{l1_cx - 10}" y1="{y2 + l1_h}" x2="{l1_cx - 10}" y2="{y3 - 4}" marker-end="url(#arrow)"/>'
    )
    parts.append(
        f'<line x1="{l1_cx + 10}" y1="{y3 - 4}" x2="{l1_cx + 10}" y2="{y2 + l1_h}" marker-end="url(#arrow)"/>'
    )
    parts.append('</g>')

    l3_x = xs[2]
    force_l3_w = xs[3] + row1_w[3] - xs[2]
    svg, _, _ = _render_cell(l3_x, y4, mem_l3, cols_hint=3, force_width=force_l3_w)
    parts.append(svg)
    parts.append('<g class="flow">')
    l2_cx = l2_x + l2_w / 2
    parts.append(
        f'<line x1="{l2_cx - 10}" y1="{y3 + l2_h}" x2="{l2_cx - 10}" y2="{y4 - 4}" marker-end="url(#arrow)"/>'
    )
    parts.append(
        f'<line x1="{l2_cx + 10}" y1="{y4 - 4}" x2="{l2_cx + 10}" y2="{y3 + l2_h}" marker-end="url(#arrow)"/>'
    )
    parts.append('</g>')

    misc_x = xs[-1] + row1_w[-1] + gap
    svg, _, _ = _render_cell(misc_x, y1, misc, cols_hint=1)
    parts.append(svg)
    if unc.count > 0:
        svg, _, _ = _render_cell(misc_x, y2, unc, cols_hint=1)
        parts.append(svg)

    parts.append('</svg>')
    return "\n".join(parts)


def render_core_svg_ecore(cells: list) -> str:
    by_id = _by_id(cells)
    row1 = [by_id["fe_fetch"], by_id["fe_decode"], by_id["be_alloc"], by_id["be_execute"]]
    row1_dims = [_cell_size(c, cols_hint=2) for c in row1]
    row1_h = max(h for _, h in row1_dims)
    row1_w = [max(200, w) for w, _ in row1_dims]

    bad_spec = by_id["bad_spec"]
    mem_l1 = by_id["mem_l1"]
    mem_l2 = by_id["mem_l2"]
    mem_l3 = by_id["mem_l3"]
    misc = by_id["misc_pmu"]
    unc = by_id["unclassified"]

    bs_w, bs_h = _cell_size(bad_spec, cols_hint=1)
    l1_w, l1_h = _cell_size(mem_l1, cols_hint=2)
    l2_w, l2_h = _cell_size(mem_l2, cols_hint=1)
    l3_w, l3_h = _cell_size(mem_l3, cols_hint=2)
    misc_w, _  = _cell_size(misc, cols_hint=1)

    gap = 24
    left = 30
    xs = [left]
    for w in row1_w[:-1]:
        xs.append(xs[-1] + w + gap)
    canvas_w = xs[-1] + row1_w[-1] + gap + misc_w + gap

    y1 = 32
    y2 = y1 + row1_h + 50
    y3 = y2 + max(bs_h, l1_h) + 34
    canvas_h = y3 + max(l2_h, l3_h) + 30

    parts = [f'<svg viewBox="0 0 {canvas_w} {canvas_h}" width="{canvas_w}" height="{canvas_h}" role="img">']
    parts.append(_arrow_defs())

    for cell, x, w in zip(row1, xs, row1_w):
        svg, _, _ = _render_cell(x, y1, cell, cols_hint=2, force_width=w)
        parts.append(svg)
    parts.append('<g class="flow">')
    for i in range(3):
        parts.append(
            f'<line x1="{xs[i] + row1_w[i]}" y1="{y1 + row1_h/2}" x2="{xs[i+1] - 4}" y2="{y1 + row1_h/2}" marker-end="url(#arrow)"/>'
        )
    parts.append('</g>')

    bs_x = xs[2] + (row1_w[2] - bs_w) // 2
    svg, _, _ = _render_cell(bs_x, y2, bad_spec, cols_hint=1)
    parts.append(svg)
    l1_x = xs[3] + (row1_w[3] - l1_w) // 2
    svg, _, _ = _render_cell(l1_x, y2, mem_l1, cols_hint=2)
    parts.append(svg)
    parts.append('<g class="flow control">')
    parts.append(
        f'<line x1="{xs[2] + row1_w[2]/2}" y1="{y1 + row1_h}" x2="{xs[2] + row1_w[2]/2}" y2="{y2 - 4}" marker-end="url(#arrow)"/>'
    )
    parts.append(
        f'<path d="M {bs_x} {y2 + bs_h/2} L 15 {y2 + bs_h/2} L 15 {y1 + row1_h/2} L {xs[0] - 4} {y1 + row1_h/2}" marker-end="url(#arrow)"/>'
    )
    parts.append(f'<text x="20" y="{y1 + row1_h + 40}" class="flow-label">flush</text>')
    parts.append('</g>')

    parts.append('<g class="flow">')
    ex_cx = xs[3] + row1_w[3] / 2
    parts.append(
        f'<line x1="{ex_cx - 10}" y1="{y1 + row1_h}" x2="{ex_cx - 10}" y2="{y2 - 4}" marker-end="url(#arrow)"/>'
    )
    parts.append(
        f'<line x1="{ex_cx + 10}" y1="{y2 - 4}" x2="{ex_cx + 10}" y2="{y1 + row1_h}" marker-end="url(#arrow)"/>'
    )
    parts.append(f'<text x="{ex_cx + 20}" y="{(y1 + row1_h + y2)/2 + 4}" class="flow-label">ld/st</text>')
    parts.append('</g>')

    l2_x = l1_x
    svg, _, _ = _render_cell(l2_x, y3, mem_l2, cols_hint=1)
    parts.append(svg)
    l3_x = l2_x + l2_w + 20
    svg, _, _ = _render_cell(l3_x, y3, mem_l3, cols_hint=2)
    parts.append(svg)
    parts.append('<g class="flow">')
    parts.append(
        f'<line x1="{l2_x + l2_w/2}" y1="{y2 + l1_h}" x2="{l2_x + l2_w/2}" y2="{y3 - 4}" marker-end="url(#arrow)"/>'
    )
    parts.append(
        f'<line x1="{l2_x + l2_w}" y1="{y3 + l2_h/2}" x2="{l3_x - 4}" y2="{y3 + l2_h/2}" marker-end="url(#arrow)"/>'
    )
    parts.append('</g>')

    misc_x = xs[-1] + row1_w[-1] + gap
    svg, _, _ = _render_cell(misc_x, y1, misc, cols_hint=1)
    parts.append(svg)
    if unc.count > 0:
        svg, _, _ = _render_cell(misc_x, y2, unc, cols_hint=1)
        parts.append(svg)

    parts.append('</svg>')
    return "\n".join(parts)


def render_uncore_svg(cells: list, include_cxl: bool = True,
                      target_width: Optional[int] = None) -> str:
    """Uncore layout, width-matched to the core diagram.

    Row 1 (peripherals strip):  UPI | PCIe/IO | CXL
    Row 2 (mesh hub):           Coherence / LLC (CHA) — full width
    Row 3 (memory subsystem):   Memory Controller — full width, stacked below CHA
    Row 4 (side-band):          Power / System — centered narrow

    Vertical stack because CHA and MC are the largest cells (~1000px each) and
    naturally align at full width. Peripherals sit above CHA feeding coherent
    traffic in; MC sits below feeding DRAM out. Power is a control-plane box.
    """
    by_id = _by_id(cells)
    cha   = by_id["coherence_llc"]
    mc    = by_id["memory_ctrl"]
    upi   = by_id["upi"]
    pcie  = by_id["pcie_io"]
    cxl   = by_id["cxl"]
    power = by_id["power_sys"]

    # Natural sizes for each cell
    cha_w,  cha_h  = _cell_size(cha,   cols_hint=3)
    mc_w,   mc_h   = _cell_size(mc,    cols_hint=3)
    upi_w,  upi_h  = _cell_size(upi,   cols_hint=1)
    pcie_w, pcie_h = _cell_size(pcie,  cols_hint=3)
    cxl_w,  cxl_h  = _cell_size(cxl,   cols_hint=1)
    pw_w,   pw_h   = _cell_size(power, cols_hint=1)

    margin = 30
    gap = 24

    # Canvas width = target (core width) if provided, else fits the widest hub cell
    natural_hub_w = max(cha_w, mc_w) + 2 * margin
    canvas_w = max(target_width or 0, natural_hub_w)

    # Full-width hub cells get force_width equal to available inner width
    inner_w = canvas_w - 2 * margin

    # Row 1: peripherals. Distribute inner_w between them proportionally to
    # their natural widths, then force each to that share.
    empty_cxl = not (include_cxl and cxl.count > 0)
    periph_cells = [upi, pcie, cxl]
    periph_natural = [upi_w, pcie_w, cxl_w]
    periph_total = sum(periph_natural)
    # Two gaps between three cells
    periph_avail = inner_w - 2 * gap
    periph_widths = [
        max(180, int(periph_avail * w / periph_total))
        for w in periph_natural
    ]
    # Adjust rounding drift so cells + gaps sum exactly to inner_w
    drift = inner_w - (sum(periph_widths) + 2 * gap)
    periph_widths[1] += drift

    # Peripheral row heights use the tallest of the three so they line up
    periph_h = max(upi_h, pcie_h, cxl_h)

    # Layout Y coordinates
    y1 = margin              # peripherals row
    y2 = y1 + periph_h + 40  # CHA
    y3 = y2 + cha_h + 34     # MC
    y4 = y3 + mc_h + 40      # Power
    canvas_h = y4 + pw_h + margin

    # X coordinates
    x_upi = margin
    x_pcie = x_upi + periph_widths[0] + gap
    x_cxl = x_pcie + periph_widths[1] + gap
    x_hub = margin
    pw_x = margin + (inner_w - pw_w) // 2

    parts = [
        f'<svg viewBox="0 0 {canvas_w} {canvas_h}" '
        f'width="{canvas_w}" height="{canvas_h}" role="img">'
    ]
    parts.append(_arrow_defs())

    # Peripherals row
    svg, _, _ = _render_cell(x_upi,  y1, upi,  cols_hint=1, force_width=periph_widths[0])
    parts.append(svg)
    svg, _, _ = _render_cell(x_pcie, y1, pcie, cols_hint=3, force_width=periph_widths[1])
    parts.append(svg)
    svg, _, _ = _render_cell(x_cxl,  y1, cxl,  cols_hint=1, force_width=periph_widths[2],
                             empty=empty_cxl)
    parts.append(svg)

    # CHA (mesh hub) — full width
    svg, _, _ = _render_cell(x_hub, y2, cha, cols_hint=5, force_width=inner_w)
    parts.append(svg)

    # Memory Controller — full width, directly below CHA
    svg, _, _ = _render_cell(x_hub, y3, mc, cols_hint=3, force_width=inner_w)
    parts.append(svg)

    # Power — narrow, centred
    svg, _, _ = _render_cell(pw_x, y4, power, cols_hint=1)
    parts.append(svg)

    # -------- Arrows --------
    parts.append('<g class="flow">')

    # From core into CHA (from top of canvas)
    hub_top_cx = x_hub + inner_w / 2
    parts.append(
        f'<line x1="{hub_top_cx}" y1="0" x2="{hub_top_cx}" y2="{y2 - 4}" marker-end="url(#arrow)"/>'
    )
    parts.append(
        f'<text x="{hub_top_cx + 8}" y="18" class="flow-label">from core L3/Offcore</text>'
    )

    # Peripherals ↔ CHA (each peripheral drops into the top of CHA at its column center)
    for i, (px, pw) in enumerate([
        (x_upi, periph_widths[0]),
        (x_pcie, periph_widths[1]),
        (x_cxl, periph_widths[2]),
    ]):
        if i == 2 and empty_cxl:
            continue
        p_bottom_cx = px + pw / 2
        # Down-arrow: peripheral -> CHA (offset by 6 to sit next to opposite-direction one)
        parts.append(
            f'<line x1="{p_bottom_cx - 6}" y1="{y1 + periph_h}" '
            f'x2="{p_bottom_cx - 6}" y2="{y2 - 4}" marker-end="url(#arrow)"/>'
        )
        # Up-arrow: CHA -> peripheral
        parts.append(
            f'<line x1="{p_bottom_cx + 6}" y1="{y2 - 4}" '
            f'x2="{p_bottom_cx + 6}" y2="{y1 + periph_h}" marker-end="url(#arrow)"/>'
        )

    # CHA ↔ MC — a pair of vertical arrows between the two full-width cells
    ch2mc_cx1 = x_hub + inner_w * 0.30
    ch2mc_cx2 = x_hub + inner_w * 0.70
    parts.append(
        f'<line x1="{ch2mc_cx1}" y1="{y2 + cha_h}" x2="{ch2mc_cx1}" y2="{y3 - 4}" marker-end="url(#arrow)"/>'
    )
    parts.append(
        f'<line x1="{ch2mc_cx2}" y1="{y3 - 4}" x2="{ch2mc_cx2}" y2="{y2 + cha_h}" marker-end="url(#arrow)"/>'
    )
    parts.append(
        f'<text x="{x_hub + inner_w * 0.5 - 30}" y="{(y2 + cha_h + y3) / 2 + 4}" '
        f'class="flow-label">directory / data</text>'
    )
    parts.append('</g>')

    # Power → dashed control lines to CHA and MC
    parts.append('<g class="flow control">')
    pw_cx = pw_x + pw_w / 2
    parts.append(
        f'<line x1="{pw_cx}" y1="{y4}" x2="{pw_cx}" y2="{y3 + mc_h + 4}" marker-end="url(#arrow)"/>'
    )
    parts.append('</g>')

    parts.append('</svg>')
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# JSON payload — events + cell/sub structure for the interactive right column
# ---------------------------------------------------------------------------

def _serialize_node(node) -> dict:
    """Recursively serialize a Cell/SubComponent tree. Leaves carry events;
    containers carry `subs` but no direct event list."""
    kids = getattr(node, "subcomponents", []) or []
    if kids:
        return {
            "id": node.id,
            "title": node.title,
            "count": node.count,
            "subs": [_serialize_node(k) for k in kids],
        }
    return {
        "id": node.id,
        "title": node.title,
        "count": node.count,
        "events": [ev.name for ev in node.events],
    }


def _leaf_paths(node, path: tuple, out: dict) -> None:
    """Walk the tree; for every EventDef in a leaf, record its full path."""
    kids = getattr(node, "subcomponents", []) or []
    if kids:
        for k in kids:
            _leaf_paths(k, path + (k.id,), out)
        return
    for ev in node.events:
        out[ev.name] = path


def _threshold_gloss(threshold: dict) -> str:
    """Return a short plain-English description of a metric's threshold."""
    if not threshold:
        return ""
    formula = threshold.get("Formula") or threshold.get("BaseFormula") or ""
    if not formula:
        return ""
    # The formula is like "a > 15" where a is the metric itself. Just show the
    # numeric side.
    return f"Bottleneck when {formula.strip()}"


def _serialize_tma_node(node) -> dict:
    """Recursively serialize a TmaNode into JSON-friendly form."""
    m = node.metric
    return {
        "name": m.name,
        "level": m.level,
        "is_leaf": node.is_leaf,
        "children": [_serialize_tma_node(c) for c in node.children],
    }


def _serialize_metric(m) -> dict:
    """Full metric detail — formula, threshold, feeders, metadata."""
    return {
        "name": m.name,
        "legacy": m.legacy_name,
        "level": m.level,
        "category": m.category,
        "parent": m.parent_category,
        "brief": m.brief_description,
        "formula_raw": m.formula,
        "formula_expanded": expand_formula(m),
        "threshold_formula": (m.threshold or {}).get("Formula", ""),
        "threshold_base": (m.threshold or {}).get("BaseFormula", ""),
        "threshold_issues": (m.threshold or {}).get("ThresholdIssues", ""),
        "threshold_gloss": _threshold_gloss(m.threshold),
        "events": sorted(m.event_names),
        "unit": m.unit_of_measure,
        "group": m.metric_group,
        "count_domain": m.count_domain,
    }


# Same-core-type predecessor for the "compare against baseline" feature.
# P-core server → previous P-core server; E-core server → previous E-core
# server. Adding a new supported platform here is a one-line change.
PREDECESSOR = {
    "GNR": "EMR",  # Granite Rapids (P-core) ← Emerald Rapids
    "CWF": "SRF",  # Clearwater Forest (E-core) ← Sierra Forest
}


# Uncore-unit renames between generations. When comparing GNR to EMR, an
# EMR event under `M2M` almost always has a counterpart under `B2CMI` on GNR
# (same event, new Unit name). We use this map to classify "removed" events
# into buckets so the user sees "1000 renamed" rather than "1000 gone."
#
# The map is intentionally per-current-platform so a future GNR-successor's
# renames can be added without disturbing this one.
UNIT_RENAMES = {
    "GNR": {
        # EMR name → GNR name  (or None if the unit was retired)
        "iMC":    "IMC",      # capitalisation change
        "M2M":    "B2CMI",    # mesh↔memory bridge renamed
        "M3UPI":  "B2UPI",    # mesh↔UPI bridge renamed
        "M2PCIe": None,       # merged into other units
        "M2HBM":  None,       # HBM discontinued
        "MCHBM":  None,       # HBM controller discontinued
    },
    # CWF's E-core predecessor SRF may have its own renames — none known yet.
    "CWF": {},
}


def _event_signature(ev) -> tuple:
    """Fingerprint used to detect "changed" events across platforms.
    Only counts semantic differences — encoding and counter set. Description
    edits between releases don't count as a change; they're editorial."""
    return (
        ev.event_code or "",
        ev.umask or "",
        (ev.raw.get("UMaskExt") or "") if ev.raw else "",
        ev.counter or "",
    )


def _normalize_formula(formula: str) -> str:
    """Return a canonical form of a metric formula for equivalence checks.

    Strips whitespace and removes ALL parentheses for the signature. This
    is aggressive: two formulas with genuinely different parenthesization
    (and therefore different semantics) will still compare equal here. In
    practice Intel's cross-generation formula edits either (a) keep the
    same operator sequence and just add/remove syntactic parens, or (b)
    change the events themselves (caught by the event-list signature).
    So dropping parens catches the "cosmetic" case cleanly while still
    flagging meaningful edits via the event-list difference.

    Example — treated as equal (cosmetic re-parenthesisation):
      "100 * ( ( a / ( b ) ) * c / ( c + d ) )"
      "100 * ( a / ( b ) * c / ( c + d ) )"

    Example — still flagged as changed (event set differs):
      "UNC_M_CAS_COUNT.RD"
      "UNC_M_CAS_COUNT_SCH0.RD + UNC_M_CAS_COUNT_SCH1.RD"
    """
    if not formula:
        return ""
    s = "".join(formula.split())
    s = s.replace("(", "").replace(")", "")
    return s


def _metric_signature(m) -> tuple:
    """Fingerprint for detecting semantic metric changes across platforms."""
    return (
        _normalize_formula(m.formula or ""),
        tuple(sorted(e["Name"] for e in m.events)),
        m.level,
    )


def _has_tma(catalog: PlatformCatalog) -> bool:
    """True iff the catalog's metrics file advertises a TMA version — i.e.
    Intel has published TMA formulas for this platform. When either side
    lacks TMA the metrics diff is dominated by the missing TMA tree
    and is misleading, so we skip metrics diffing while still doing events."""
    h = getattr(catalog, "metrics_header", None) or {}
    return bool((h.get("TmaVersion") or "").strip())


def _build_diff(current: PlatformCatalog,
                baseline: PlatformCatalog) -> Optional[dict]:
    """Compute per-event / per-metric status maps + summary counts.

    Skips the metrics diff (metrics_status stays empty, counts show zeros)
    when either the current or baseline catalog lacks a TMA hierarchy —
    the diff would otherwise be dominated by "missing TMA tree" noise
    rather than architectural change.
    """
    skip_metrics = not (_has_tma(current) and _has_tma(baseline))
    events_status = {}     # ev name -> 'new' | 'changed' | 'same'
    metrics_status = {}    # metric name -> 'new' | 'changed' | 'same'
    events_removed = []    # names that exist in baseline but not current
    metrics_removed = []

    events_changes = {}   # name -> {field: [old, new], ...} for status == "changed"
    metrics_changes = {}  # name -> {formula: [old, new], events_added: [...], events_removed: [...]}
    cur_events = {e.name: e for e in current.events if not e.deprecated}
    base_events = {e.name: e for e in baseline.events if not e.deprecated}
    for name, e in cur_events.items():
        b = base_events.get(name)
        if b is None:
            events_status[name] = "new"
        elif _event_signature(e) != _event_signature(b):
            events_status[name] = "changed"
            fields = {}
            if (e.event_code or "") != (b.event_code or ""):
                fields["event_code"] = [b.event_code or "", e.event_code or ""]
            if (e.umask or "") != (b.umask or ""):
                fields["umask"] = [b.umask or "", e.umask or ""]
            cur_ext = (e.raw.get("UMaskExt") or "") if e.raw else ""
            base_ext = (b.raw.get("UMaskExt") or "") if b.raw else ""
            if cur_ext != base_ext:
                fields["umask_ext"] = [base_ext, cur_ext]
            if (e.counter or "") != (b.counter or ""):
                fields["counter"] = [b.counter or "", e.counter or ""]
            if fields:
                events_changes[name] = fields
        else:
            events_status[name] = "same"
    for name in sorted(set(base_events) - set(cur_events)):
        events_removed.append(name)

    if not skip_metrics:
        cur_metrics = {m.name: m for m in current.metrics}
        base_metrics = {m.name: m for m in baseline.metrics}
        for name, m in cur_metrics.items():
            b = base_metrics.get(name)
            if b is None:
                metrics_status[name] = "new"
            elif _metric_signature(m) != _metric_signature(b):
                metrics_status[name] = "changed"
                cur_ev = {ev["Name"] for ev in m.events}
                base_ev = {ev["Name"] for ev in b.events}
                # Only record the formula diff when the normalized (whitespace-
                # and paren-agnostic) forms actually differ. This avoids
                # showing a "formula changed" panel for pure re-parenthesisations.
                formula_changed = (_normalize_formula(m.formula or "")
                                   != _normalize_formula(b.formula or ""))
                metrics_changes[name] = {
                    "formula_current": expand_formula(m) if (m.formula and formula_changed) else "",
                    "formula_baseline": expand_formula(b) if (b.formula and formula_changed) else "",
                    "events_added": sorted(cur_ev - base_ev),
                    "events_removed": sorted(base_ev - cur_ev),
                    "level_current": m.level,
                    "level_baseline": b.level,
                }
            else:
                metrics_status[name] = "same"
        for name in sorted(set(base_metrics) - set(cur_metrics)):
            metrics_removed.append(name)

    from ..core.arch_map import build_arch_map
    cur_am = build_arch_map(current)
    ev_to_cell = {}
    for cell in list(cur_am.core_cells) + list(cur_am.uncore_cells):
        _leaf_paths(cell, (cell.id,), ev_to_cell)

    # Bucket the "removed" events by why they went away — many are just
    # unit renames (M2M → B2CMI on GNR). Users care about *genuine* removals,
    # not rename churn. See UNIT_RENAMES.
    renames = UNIT_RENAMES.get(current.platform.shortname, {})
    # Symmetric map for the "new" direction (target unit → source unit): a
    # GNR event under a rename-target Unit isn't really "new" if the same
    # basename existed on the baseline under the old Unit.
    reverse_renames = {v: k for k, v in renames.items() if v is not None}

    removed_buckets = {
        "renamed": [],       # unit rename (still exists under a new Unit name)
        "unit_retired": [],  # unit dropped entirely (e.g. HBM)
        "denser_variants": [],  # EMR shipped per-slice variants
        "genuinely_gone": [],  # core events or otherwise-unmatched drops
    }
    new_buckets = {
        "renamed": [],       # exists on baseline under the old Unit name
        "genuinely_new": [], # not present on the baseline at all
    }
    # Best-effort basename extractor (drops UNC_<UNIT>_ prefix so we can
    # match a rename-pair by remainder).
    def _base(name):
        # UNC_M2M_IMC_READS.NORMAL → IMC_READS
        if not name.startswith("UNC_"):
            return name
        parts = name[len("UNC_"):].split("_", 1)
        return parts[1] if len(parts) > 1 else parts[0]

    cur_bases_by_unit = {}
    for e in current.events:
        u = e.raw.get("Unit") or ""
        if not u:
            continue
        cur_bases_by_unit.setdefault(u, set()).add(_base(e.name))
    base_bases_by_unit = {}
    for e in baseline.events:
        if e.deprecated:
            continue
        u = e.raw.get("Unit") or ""
        if not u:
            continue
        base_bases_by_unit.setdefault(u, set()).add(_base(e.name))

    base_events_lookup = {e.name: e for e in baseline.events if not e.deprecated}
    for name in events_removed:
        e = base_events_lookup.get(name)
        u = (e.raw.get("Unit") if e else "") or ""
        if u in renames:
            target = renames[u]
            if target is None:
                removed_buckets["unit_retired"].append(name)
            else:
                b = _base(name)
                if b in cur_bases_by_unit.get(target, set()):
                    removed_buckets["renamed"].append(name)
                else:
                    removed_buckets["unit_retired"].append(name)
        elif u and u not in cur_bases_by_unit:
            removed_buckets["unit_retired"].append(name)
        elif u and _base(name) not in cur_bases_by_unit.get(u, set()):
            removed_buckets["denser_variants"].append(name)
        else:
            removed_buckets["genuinely_gone"].append(name)

    # Reclassify the "new" set: if a current event is under a rename-target
    # Unit and the baseline had the same basename under the old Unit, it's
    # a rename in disguise, not new.
    cur_events_lookup = {e.name: e for e in current.events if not e.deprecated}
    for name, status in list(events_status.items()):
        if status != "new":
            continue
        e = cur_events_lookup.get(name)
        u = (e.raw.get("Unit") if e else "") or ""
        old_unit = reverse_renames.get(u)
        if old_unit and _base(name) in base_bases_by_unit.get(old_unit, set()):
            # This "new" event is really the same event under a renamed unit.
            events_status[name] = "same"      # don't highlight in diff mode
            new_buckets["renamed"].append(name)
            # remove it from any per-cell rollup as new; recount later
        else:
            new_buckets["genuinely_new"].append(name)

    # Per-path rollup: rolls each event's status up along its full path so
    # the top-level cell, every subcomponent, and every sub-sub can render
    # a diff badge. Key is the '/'-joined path (e.g. "coherence_llc",
    # "coherence_llc/tor", "coherence_llc/tor/ia").
    cell_rollup = {}   # top-level for the summary strip
    path_rollup = {}   # every ancestor path

    def _bump(path_key, status):
        r = path_rollup.setdefault(
            path_key,
            {"new": 0, "changed": 0, "same": 0, "removed": 0},
        )
        r[status] += 1

    for name, status in events_status.items():
        path = ev_to_cell.get(name)
        if not path:
            continue
        # Roll up to every ancestor prefix, including the leaf.
        for i in range(1, len(path) + 1):
            _bump("/".join(path[:i]), status)

    # Genuinely-gone removed events: bucket by baseline classifier path.
    try:
        base_am = build_arch_map(baseline)
        base_ev_cells = {}
        for cell in list(base_am.core_cells) + list(base_am.uncore_cells):
            _leaf_paths(cell, (cell.id,), base_ev_cells)
    except ValueError:
        base_ev_cells = {}
    for name in removed_buckets["genuinely_gone"]:
        path = base_ev_cells.get(name, ("unclassified",))
        for i in range(1, len(path) + 1):
            _bump("/".join(path[:i]), "removed")

    # Legacy top-level cell_rollup for the summary strip (unchanged callers).
    for key, counts_dict in path_rollup.items():
        if "/" not in key:
            cell_rollup[key] = counts_dict

    # -------- TMA subtree rollup --------
    # For each TMA node the badge shows "how many metrics in this subtree
    # changed". Semantics:
    #   agg[status] = (1 if own metric has that status else 0)
    #               + sum of children's agg[status]
    # A parent box always shows the sum of its descendants plus itself.
    tma_rollup = {}   # metric name -> {new, changed, same, removed}
    if not skip_metrics:
        tree = TmaTree(current)
        def _rollup_node(node):
            agg = {"new": 0, "changed": 0, "same": 0, "removed": 0}
            own = metrics_status.get(node.metric.name)
            if own in agg:
                agg[own] += 1
            for c in node.children:
                child_agg = _rollup_node(c)
                for k in agg:
                    agg[k] += child_agg[k]
            tma_rollup[node.metric.name] = agg
            return agg
        for root in tree.roots:
            _rollup_node(root)

    counts = {
        "events": {
            # Post-reclassification counts — these match what the UI highlights.
            "new": sum(1 for s in events_status.values() if s == "new"),
            "changed": sum(1 for s in events_status.values() if s == "changed"),
            "same": sum(1 for s in events_status.values() if s == "same"),
            "new_renamed": len(new_buckets["renamed"]),
            "removed_total": len(events_removed),
            "removed_renamed": len(removed_buckets["renamed"]),
            "removed_unit_retired": len(removed_buckets["unit_retired"]),
            "removed_denser_variants": len(removed_buckets["denser_variants"]),
            "removed_genuinely_gone": len(removed_buckets["genuinely_gone"]),
        },
        "metrics": {
            "new": sum(1 for s in metrics_status.values() if s == "new"),
            "changed": sum(1 for s in metrics_status.values() if s == "changed"),
            "same": sum(1 for s in metrics_status.values() if s == "same"),
            "removed": len(metrics_removed),
        },
    }
    return {
        "baseline": baseline.platform.shortname,
        "baseline_name": baseline.platform.name,
        "metrics_diff_available": not skip_metrics,
        "events_status": events_status,
        "metrics_status": metrics_status,
        "events_removed": events_removed,
        "events_removed_genuine": removed_buckets["genuinely_gone"],
        "events_removed_buckets": {
            k: v for k, v in removed_buckets.items()
        },
        "metrics_removed": metrics_removed,
        "counts": counts,
        "cell_rollup": cell_rollup,
        "path_rollup": path_rollup,
        "tma_rollup": tma_rollup,
        "events_changes": events_changes,
        "metrics_changes": metrics_changes,
    }


def _build_payload(arch_map: ArchMap, catalog: Optional[PlatformCatalog] = None,
                   baseline: Optional[PlatformCatalog] = None) -> dict:
    cells = {}
    events = {}

    # Compute the leaf path each event belongs to so we can attach the right
    # "what this means" note.
    ev_paths = {}
    for cell in list(arch_map.core_cells) + list(arch_map.uncore_cells):
        _leaf_paths(cell, (cell.id,), ev_paths)

    # Reverse index: event name -> [metric names] using this event. Populated
    # below once we have the metrics list.
    events_to_metrics: dict = {}

    for cell in list(arch_map.core_cells) + list(arch_map.uncore_cells):
        cells[cell.id] = _serialize_node(cell)
        for ev in cell.events:
            path = ev_paths.get(ev.name, (cell.id,))
            acronyms = find_acronyms(
                (ev.brief_description or "") + " " + (ev.public_description or "")
            )
            examples = build_examples(ev)
            events[ev.name] = {
                "name": ev.name,
                "brief": ev.brief_description,
                "public": ev.public_description,
                "unit": ev.raw.get("Unit") or "",
                "code": ev.event_code,
                "umask": ev.umask,
                "counter": ev.counter,
                "precise": ev.precise,
                "sample": ev.sample_after_value,
                "note": note_for_path(path),
                "acronyms": [
                    {"tok": a, "exp": exp, "gloss": gloss}
                    for a, exp, gloss in acronyms
                ],
                "perf": examples,
                # will be filled in after metrics are indexed
                "used_by": [],
            }

    # -------- Metrics + TMA tree --------
    metrics = {}
    tma_roots = []
    bottlenecks = []
    info_groups = {}
    non_tma_categories = {}   # for CWF-style platforms with no TMA tree

    if catalog is not None:
        # Populate metrics dict, event→metrics reverse index
        for m in catalog.metrics:
            metrics[m.name] = _serialize_metric(m)
            for ev_name in m.event_names:
                events_to_metrics.setdefault(ev_name, []).append(m.name)

        # Fill in each event's `used_by` list (sorted for stable output)
        for ev_name, mlist in events_to_metrics.items():
            if ev_name in events:
                events[ev_name]["used_by"] = sorted(set(mlist))

        # Synthesize pseudo-events (PERF_METRICS.*, RAPL, TSC, TOPDOWN.SLOTS)
        # so clicking them from a metric's feeder list opens a useful detail
        # page instead of a dead link. These aren't in perfmon's events JSON —
        # they're kernel-exposed synthetic counters.
        for ev_name, mlist in events_to_metrics.items():
            if ev_name in events:
                continue
            pseudo = get_pseudo_event(ev_name)
            if pseudo is None:
                continue
            events[ev_name] = {
                "name": ev_name,
                "brief": pseudo["brief"],
                "public": pseudo["detail"],
                "unit": "",
                "code": "",
                "umask": "",
                "counter": "",
                "precise": "0",
                "sample": "",
                "note": pseudo["source"],
                "acronyms": [],
                "perf": None,
                "used_by": sorted(set(mlist)),
                "pseudo": True,
                "pseudo_formula": pseudo.get("formula"),
            }

        # Build the TMA tree (may be empty on platforms like CWF)
        tree = TmaTree(catalog)
        tma_roots = [_serialize_tma_node(r) for r in tree.roots]
        bottlenecks = [m.name for m in tree.bottlenecks]

        # Group Info metrics by their first MetricGroup token
        for m in tree.info_metrics:
            g = (m.metric_group or "Uncategorized").split(";")[0].strip() or "Uncategorized"
            info_groups.setdefault(g, []).append(m.name)
        for g in info_groups:
            info_groups[g].sort()

        # For platforms without a TMA tree (CWF), also expose the flat
        # category-keyed list so the UI has something to show.
        if not tma_roots:
            for m in catalog.metrics:
                if m.is_info or m.is_bottleneck:
                    continue
                cat_key = m.category or "Uncategorized"
                non_tma_categories.setdefault(cat_key, []).append(m.name)
            for k in non_tma_categories:
                non_tma_categories[k].sort()

    diff = None
    if catalog is not None and baseline is not None:
        try:
            diff = _build_diff(catalog, baseline)
        except Exception:
            # Compare failure should never break page render.
            diff = None

    return {
        "cells": cells,
        "events": events,
        "metrics": metrics,
        "tma_roots": tma_roots,
        "bottlenecks": bottlenecks,
        "info_groups": info_groups,
        "non_tma_categories": non_tma_categories,
        "diff": diff,
    }


# ---------------------------------------------------------------------------
# Page assembly
# ---------------------------------------------------------------------------

def render_page(arch_map: ArchMap,
                platform_display: Optional[str] = None,
                catalog: Optional[PlatformCatalog] = None,
                baseline_catalog: Optional[PlatformCatalog] = None) -> str:
    display = platform_display or arch_map.platform
    total = arch_map.total_core + arch_map.total_uncore
    mapped = arch_map.core_mapped + arch_map.uncore_mapped
    unmapped = arch_map.core_unmapped + arch_map.uncore_unmapped

    is_ecore = arch_map.platform in {"CWF"}  # add SRF/GRR here when classifier rules land
    core_svg = (render_core_svg_ecore if is_ecore else render_core_svg_pcore)(arch_map.core_cells)
    # Whether to draw CXL as connected: any platform that actually carries CXL
    # events (GNR + CWF today, via the experimental uncore file).
    has_cxl = any(c.id == "cxl" and c.count > 0 for c in arch_map.uncore_cells)
    canvas_w = _core_canvas_width(arch_map.core_cells, is_ecore=is_ecore)
    uncore_svg = render_uncore_svg(
        arch_map.uncore_cells,
        include_cxl=has_cxl,
        target_width=canvas_w,
    )

    payload = _build_payload(arch_map, catalog=catalog, baseline=baseline_catalog)
    payload_json = json.dumps(payload, separators=(",", ":"))
    n_metrics = len(payload["metrics"])
    n_events = len(payload["events"])

    # Metric distribution — count each category from the metrics list so it
    # stays consistent with the payload rather than re-derived at render time.
    n_tma_tree = sum(1 for m in payload["metrics"].values()
                     if m.get("category") == "TMA"
                     and not m["name"].startswith("Bottleneck_")
                     and not m["name"].startswith("Info_"))
    n_bottleneck = len(payload["bottlenecks"])
    n_info = sum(len(v) for v in payload["info_groups"].values())
    n_non_tma = sum(len(v) for v in payload["non_tma_categories"].values())

    # TMA tree SVG (may be an empty placeholder for CWF etc.)
    tma_svg = ""
    if catalog is not None:
        tree = TmaTree(catalog)
        tma_svg = render_tma_svg(
            tree, target_width=canvas_w,
            metrics_header=getattr(catalog, "metrics_header", None),
        )

    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{html.escape(display)} — arch map</title>
<style>{PAGE_CSS}</style>
</head>
<body>
<header>
  <div class="head-row">
    <div class="head-info">
      <h1>{html.escape(display)} — Architecture Event Map</h1>
      <div class="subtitle">Click a component or metric on the left, or search across both.</div>
      <div class="stats">
        <span class="stats-label">Events:</span>
        <div class="stat"><b>{total}</b>total</div>
        <div class="stat mapped"><b>{mapped}</b>mapped</div>
        <div class="stat unmapped"><b>{unmapped}</b>unmapped</div>
        <div class="stat"><b>{arch_map.total_core}</b>core</div>
        <div class="stat"><b>{arch_map.total_uncore}</b>uncore</div>
      </div>
      <div class="stats">
        <span class="stats-label">Metrics:</span>
        <div class="stat"><b>{n_metrics}</b>total</div>
        <div class="stat"><b>{n_tma_tree}</b>TMA</div>
        <div class="stat"><b>{n_bottleneck}</b>Bottleneck</div>
        <div class="stat"><b>{n_info}</b>Info</div>
        {'<div class="stat"><b>' + str(n_non_tma) + '</b>flat</div>' if n_non_tma else ''}
      </div>
    </div>
    <div class="search-box">
      <input id="search-input" type="text" placeholder="Search events or metrics…" autocomplete="off" spellcheck="false" />
      <div class="search-suggestions" id="search-suggestions"></div>
    </div>
  </div>
  <div class="tabs">
    <div class="tab active" data-tab="events">Events <span class="badge">{n_events}</span><span class="help-tip" tabindex="0">?<span class="tip"><b>Hardware PMU events</b> — the raw counters exposed by the CPU. Each has an EventCode+UMask that programs a physical counter register. Grouped here by which uarch block generates them (Frontend / Backend / Memory / CHA / IMC / …).</span></span></div>
    <div class="tab" data-tab="metrics">Metrics <span class="badge">{n_metrics}</span><span class="help-tip" tabindex="0">?<span class="tip"><b>Derived measurements</b> — arithmetic formulas over one or more events that produce a meaningful number (IPC, DRAM bandwidth, L2 miss rate, TMA slot fractions). Comes from Intel's <code>*_metrics.json</code>. Includes TMA nodes, bottleneck aggregates, and standalone info metrics.</span></span></div>
    <div class="compare-toggle-wrap"><label class="compare-toggle" id="compare-toggle-label" style="display:none;">
      <input type="checkbox" id="compare-toggle" checked> Compare to <span id="compare-baseline">—</span>
      <span class="help-tip" tabindex="0">?<span class="tip">When on, every event and metric is coloured by its status vs the immediate predecessor of the same core type: <b class="dot dot-new"></b> new since the baseline, <b class="dot dot-changed"></b> encoding/formula changed, unmarked = unchanged. Removed items appear in a dedicated section since they don't exist on the current platform's diagram.</span></span>
    </label></div>
  </div>
  <div class="compare-strip" id="compare-strip" style="display:none;">
    <div class="cs-header">Compared to <b id="cs-baseline">—</b>
      <span class="cs-counts" id="cs-counts"></span>
    </div>
    <div class="cs-cells" id="cs-cells"></div>
  </div>
</header>

<div class="layout">
  <div class="left-col">
    <div class="view active" id="view-events">
      <div class="diagram-block">
        <h2>Core Pipeline</h2>
        {core_svg}
      </div>
      <div class="diagram-block">
        <h2>Uncore / SoC</h2>
        {uncore_svg}
      </div>
      <details class="subblock" id="removed-events-block" style="display:none;">
        <summary>Removed since baseline <span class="badge" id="removed-events-count">0</span><span class="help-tip" tabindex="0">?<span class="tip"><b>Events present on the predecessor that this platform no longer defines.</b> Note that many "removed" events are actually renamed — e.g. EMR's <code>UNC_M2M_*</code> became GNR's <code>UNC_B2CMI_*</code>, and <code>iMC</code> became <code>IMC</code>. The count includes those renames, so it can look large. HBM-related units (<code>M2HBM</code>, <code>MCHBM</code>) are genuinely gone since HBM was SPR-only.</span></span></summary>
        <ul class="metric-list removed-list" id="removed-events-list"></ul>
      </details>
    </div>
    <div class="view" id="view-metrics">
      <div class="diagram-block tma-block">
        <h2>TMA Hierarchy <span class="badge" id="tma-count">0</span><span class="help-tip" tabindex="0">?<span class="tip"><b>Top-down Microarchitecture Analysis</b> — Intel's structured methodology for classifying every pipeline slot. L1 has four buckets (Retiring / Bad-Spec / Frontend-Bound / Backend-Bound) whose fractions sum to 100%. Deeper levels drill into each root: e.g. Backend_Bound → Memory_Bound → DRAM_Bound. Nodes with a ⚑ carry an official <em>bottleneck threshold</em> (e.g. "flagged if &gt; 20%") — use them to decide where to drill next.</span></span></h2>
        <div class="tree-scroll">{tma_svg}</div>
      </div>
      <details class="subblock" id="bottleneck-block">
        <summary>Bottleneck aggregates <span class="badge" id="bottleneck-count">0</span><span class="help-tip" tabindex="0">?<span class="tip"><b>Cross-cutting summary metrics</b> that combine multiple TMA leaves into a single number. e.g. <code>Bottleneck_Memory_Data_TLBs</code> rolls together load-side and store-side TLB stalls from different subtrees. Handy when you want <em>one</em> number to describe "how much of the workload is X."</span></span></summary>
        <ul class="metric-list" id="bottleneck-list"></ul>
      </details>
      <details class="subblock" id="info-block">
        <summary>Info metrics <span class="badge" id="info-count">0</span><span class="help-tip" tabindex="0">?<span class="tip"><b>Standalone observability metrics</b> — not part of the TMA tree, no thresholds. IPC, CPI, GFLOPS, cache-hit rates, branch statistics, etc. Grouped by their <code>MetricGroup</code> prefix (Mem / Fed / Flops / Branches / …). These answer "what is my workload doing?" rather than "where is it stalling?"</span></span></summary>
        <div id="info-groups"></div>
      </details>
      <details class="subblock" id="nontma-block">
        <summary>Metrics (no TMA hierarchy) <span class="badge" id="nontma-count">0</span><span class="help-tip" tabindex="0">?<span class="tip">Intel has not yet published a TMA tree for this platform — the metrics JSON header's <code>TmaVersion</code> field is empty. Only system-level metrics (Freq / BW / IO / NUMA / Latency / …) are defined so far. Common on newly-launched parts: event files typically arrive first, TMA metrics land in a later release. As soon as Intel publishes them, this page will pick them up automatically on the next rebuild.</span></span></summary>
        <div id="nontma-groups"></div>
      </details>
    </div>
  </div>
  <div class="right-col">
    <div class="right-pane top" id="pane-list">
      <div class="empty">Click a component or metric on the left.</div>
    </div>
    <div class="right-pane bottom" id="pane-detail">
      <div class="empty">Select an event or metric to see its full description.</div>
    </div>
  </div>
</div>

<script>const ARCH = {payload_json};</script>
<script>{PAGE_JS}</script>
</body>
</html>
'''
