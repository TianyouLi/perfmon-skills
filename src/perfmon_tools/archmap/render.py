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
.primary-badge {
  display: inline-block; margin-left: 0.3rem;
  background: var(--accent); color: #0f172a;
  padding: 0.02rem 0.35rem; border-radius: 8px;
  font-family: inherit; font-size: 0.6rem; font-weight: 700;
  text-transform: uppercase; letter-spacing: 0.06em;
  vertical-align: middle;
}
.metric-detail .feeder.primary { border-color: var(--accent); }

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
        parts.push('<li data-ev="'+encodeURIComponent(name)+'">'+escapeHtml(name)+'</li>');
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

  function renderMetricFeederList(pane, name){
    var m = ARCH.metrics[name];
    if(!m){ pane.innerHTML = '<div class="empty">Unknown metric.</div>'; return; }
    var parts = [];
    parts.push('<h2>'+escapeHtml(m.name)+' <span class="badge">L'+m.level+'</span></h2>');
    var pathBits = [];
    if(m.category) pathBits.push(m.category);
    if(m.parent) pathBits.push(m.parent);
    if(pathBits.length) parts.push('<div class="path">'+escapeHtml(pathBits.join(' › '))+'</div>');
    parts.push('<h4 style="margin:0.5rem 0 0.35rem;font-size:0.75rem;color:var(--muted);text-transform:uppercase;letter-spacing:0.08em;">Feeder events ('+m.events.length+')<span class="click-hint">single-click: preview · double-click: jump</span></h4>');
    // Detect the "primary" feeder — a pseudo-event whose name pattern matches
    // the metric (e.g. Frontend_Bound ↔ PERF_METRICS.FRONTEND_BOUND). This
    // isn't self-reference, it's the raw counter the metric is normalizing.
    var primary = primaryFeederFor(m.name, m.events);
    parts.push('<ul class="event-list">');
    m.events.forEach(function(ename){
      var badge = (ename === primary)
        ? ' <span class="primary-badge">primary</span>'
        : '';
      parts.push('<li data-ev="'+encodeURIComponent(ename)+'">'+escapeHtml(ename)+badge+'</li>');
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
    qa('#view-events #pane-list li.selected').forEach(function(el){ el.classList.remove('selected'); });
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
    // Clear only the metrics-view highlights (leave the events SVG alone).
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
        var badge = (ename === primary) ? ' <span class="primary-badge">primary</span>' : '';
        parts.push('<span class="'+cls+'" data-jump-event="'+encodeURIComponent(ename)+'">'+escapeHtml(ename)+badge+'</span>');
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
  function renderMetricsSidebar(){
    // Bottlenecks
    var bcount = q('#bottleneck-count');
    var blist = q('#bottleneck-list');
    if(ARCH.bottlenecks && ARCH.bottlenecks.length){
      bcount.textContent = ARCH.bottlenecks.length;
      blist.innerHTML = ARCH.bottlenecks.map(function(name){
        return '<li data-metric="'+escapeHtml(name)+'">'+escapeHtml(name)+'</li>';
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
      var parts = [];
      infoNames.sort().forEach(function(g){
        var items = infoGroups[g];
        total += items.length;
        parts.push('<div class="group-title">'+escapeHtml(g)+' ('+items.length+')</div>');
        parts.push('<ul class="metric-list">');
        items.forEach(function(name){
          parts.push('<li data-metric="'+escapeHtml(name)+'">'+escapeHtml(name)+'</li>');
        });
        parts.push('</ul>');
      });
      iCount.textContent = total;
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
      var nParts = [];
      nKeys.sort().forEach(function(g){
        var items = nonTma[g];
        nTotal += items.length;
        nParts.push('<div class="group-title">'+escapeHtml(g || 'Uncategorized')+' ('+items.length+')</div>');
        nParts.push('<ul class="metric-list">');
        items.forEach(function(name){
          nParts.push('<li data-metric="'+escapeHtml(name)+'">'+escapeHtml(name)+'</li>');
        });
        nParts.push('</ul>');
      });
      nCount.textContent = nTotal;
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
    renderMetricsSidebar();
    renderList();
    renderDetail();
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
# TMA tree renderer — top-down family-tree layout
#
# L1 roots at the top. Each node's children fan out horizontally below it.
# Layout pass:
#   1. Bottom-up: compute the horizontal footprint of each subtree so leaves
#      never overlap. Internal nodes get max(own_width, sum(children_widths)).
#   2. Top-down: assign each node an x centred over its subtree.
#   3. y is determined by depth × row spacing.
# Elbow connectors go straight down from parent bottom, then horizontally,
# then down into child top.
# ---------------------------------------------------------------------------

TMA_LEAF_W = 118          # each leaf occupies at least this much horizontal space
TMA_LEAF_GAP = 8          # min gap between sibling subtrees
TMA_NODE_H = 28           # box height
TMA_ROW_H = 62            # vertical distance from row N to row N+1
TMA_ROOT_GAP = 40         # extra gap between L1 subtrees
TMA_TOP_PAD = 24
TMA_LEFT_PAD = 24
TMA_BOTTOM_PAD = 24


def _tma_layout_subtree(node, depth, cursor_x, rows):
    """Recursively lay out a subtree starting at cursor_x. Returns the total
    horizontal width consumed by this subtree. Appends layout dicts to `rows`.
    """
    if not node.children:
        # Leaf: fixed width
        w = TMA_LEAF_W
        rows.append({
            "node": node,
            "depth": depth,
            "cx": cursor_x + w / 2,
            "y": TMA_TOP_PAD + depth * TMA_ROW_H,
        })
        return w

    # Layout children first, side by side
    child_start = cursor_x
    child_center_xs = []
    for i, c in enumerate(node.children):
        if i > 0:
            child_start += TMA_LEAF_GAP
        child_w = _tma_layout_subtree(c, depth + 1, child_start, rows)
        child_center_xs.append(child_start + child_w / 2)
        child_start += child_w

    subtree_w = child_start - cursor_x
    # Parent width — must accommodate its own box (TMA_LEAF_W) even if kids are
    # narrower.
    if subtree_w < TMA_LEAF_W:
        # Center the narrow subtree under the parent. We've appended all
        # descendants to `rows` but not the parent itself yet, so the shift
        # applies to (subtree_size - 1) trailing rows.
        shift = (TMA_LEAF_W - subtree_w) / 2
        descendants = _count_subtree(node) - 1
        for r in rows[-descendants:]:
            r["cx"] += shift
        for k in range(len(child_center_xs)):
            child_center_xs[k] += shift
        subtree_w = TMA_LEAF_W

    parent_cx = (child_center_xs[0] + child_center_xs[-1]) / 2
    rows.append({
        "node": node,
        "depth": depth,
        "cx": parent_cx,
        "y": TMA_TOP_PAD + depth * TMA_ROW_H,
    })
    return subtree_w


def _count_subtree(node):
    n = 1
    for c in node.children:
        n += _count_subtree(c)
    return n


def render_tma_svg(tree: TmaTree, target_width: int) -> str:
    """Render the TMA tree as a top-down family tree."""
    if not tree.roots:
        # Placeholder — platforms with no TMA hierarchy (e.g. CWF).
        return (
            f'<svg viewBox="0 0 {target_width} 60" width="{target_width}" '
            f'height="60" role="img">'
            f'<text x="{target_width // 2}" y="34" class="tma-empty" '
            f'text-anchor="middle">No TMA hierarchy defined for this platform.</text>'
            f'</svg>'
        )

    rows = []
    cursor_x = TMA_LEFT_PAD
    for i, root in enumerate(tree.roots):
        if i > 0:
            cursor_x += TMA_ROOT_GAP
        w = _tma_layout_subtree(root, 0, cursor_x, rows)
        cursor_x += w

    max_depth = max(r["depth"] for r in rows)
    canvas_w = max(target_width, int(cursor_x + TMA_LEFT_PAD))
    canvas_h = TMA_TOP_PAD + (max_depth + 1) * TMA_ROW_H + TMA_BOTTOM_PAD

    parts = [
        f'<svg viewBox="0 0 {canvas_w} {canvas_h}" width="{canvas_w}" '
        f'height="{canvas_h}" role="img">'
    ]
    parts.append('<style>'
                 '.tma-node rect { fill: var(--box); stroke: var(--border); stroke-width: 1; }'
                 '.tma-node:hover rect { fill: var(--box-hover); stroke: var(--accent); cursor: pointer; }'
                 '.tma-node.selected rect { fill: rgba(56,189,248,0.25); stroke: var(--accent); stroke-width: 2; }'
                 '.tma-node text.title { fill: var(--ink); font-size: 11px; font-weight: 500; pointer-events: none; }'
                 '.tma-node text.lvl { fill: var(--accent); font-size: 9px; font-weight: 600; pointer-events: none; }'
                 '.tma-node.has-thr rect { stroke: var(--accent); }'
                 '.tma-connector { stroke: var(--border); stroke-width: 1; fill: none; }'
                 '.tma-empty { fill: var(--muted); font-size: 13px; font-style: italic; }'
                 '</style>')

    # Index rows by node identity for connector lookup.
    row_by_id = {id(r["node"]): r for r in rows}

    # Elbows first, behind the boxes.
    parts.append('<g class="tma-connectors">')
    for r in rows:
        node = r["node"]
        if not node.children:
            continue
        parent_cx = r["cx"]
        parent_bottom = r["y"] + TMA_NODE_H
        # A single horizontal bus at the midpoint between the parent row and
        # the child row makes the tree readable even when many siblings share
        # a parent.
        bus_y = r["y"] + TMA_NODE_H + (TMA_ROW_H - TMA_NODE_H) / 2
        # Vertical stem down from parent to bus
        parts.append(
            f'<path class="tma-connector" '
            f'd="M {parent_cx} {parent_bottom} L {parent_cx} {bus_y}"/>'
        )
        # Horizontal bus spanning first→last child (if >1 kid)
        child_cxs = [row_by_id[id(c)]["cx"] for c in node.children]
        if len(child_cxs) > 1:
            parts.append(
                f'<path class="tma-connector" '
                f'd="M {min(child_cxs)} {bus_y} L {max(child_cxs)} {bus_y}"/>'
            )
        # Vertical stems from bus down to each child top
        for cx in child_cxs:
            child_top = r["y"] + TMA_ROW_H
            parts.append(
                f'<path class="tma-connector" '
                f'd="M {cx} {bus_y} L {cx} {child_top}"/>'
            )
    parts.append('</g>')

    # Node boxes
    for r in rows:
        node = r["node"]
        m = node.metric
        has_thr = bool((m.threshold or {}).get("Formula"))
        cls = "tma-node has-thr" if has_thr else "tma-node"
        w = TMA_LEAF_W
        x = r["cx"] - w / 2
        y = r["y"]
        label = _short(m.name, maxlen=15)
        lvl_label = f'L{m.level}{" ⚑" if has_thr else ""}'
        parts.append(
            f'<g class="{cls}" data-metric="{html.escape(m.name)}">'
            f'<rect x="{x}" y="{y}" width="{w}" height="{TMA_NODE_H}" rx="4"/>'
            f'<text class="title" x="{r["cx"]}" y="{y + 14}" text-anchor="middle">'
            f'{html.escape(label)}</text>'
            f'<text class="lvl" x="{r["cx"]}" y="{y + 24}" text-anchor="middle">'
            f'{lvl_label}</text>'
            f'<title>{html.escape(m.name)}</title>'
            f'</g>'
        )

    parts.append('</svg>')
    return "\n".join(parts)


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


def _build_payload(arch_map: ArchMap, catalog: Optional[PlatformCatalog] = None) -> dict:
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

    return {
        "cells": cells,
        "events": events,
        "metrics": metrics,
        "tma_roots": tma_roots,
        "bottlenecks": bottlenecks,
        "info_groups": info_groups,
        "non_tma_categories": non_tma_categories,
    }


# ---------------------------------------------------------------------------
# Page assembly
# ---------------------------------------------------------------------------

def render_page(arch_map: ArchMap,
                platform_display: Optional[str] = None,
                catalog: Optional[PlatformCatalog] = None) -> str:
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

    payload = _build_payload(arch_map, catalog=catalog)
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
        tma_svg = render_tma_svg(tree, target_width=canvas_w)

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
    </div>
    <div class="view" id="view-metrics">
      <div class="diagram-block tma-block">
        <h2>TMA Hierarchy<span class="help-tip" tabindex="0">?<span class="tip"><b>Top-down Microarchitecture Analysis</b> — Intel's structured methodology for classifying every pipeline slot. L1 has four buckets (Retiring / Bad-Spec / Frontend-Bound / Backend-Bound) whose fractions sum to 100%. Deeper levels drill into each root: e.g. Backend_Bound → Memory_Bound → DRAM_Bound. Nodes with a ⚑ carry an official <em>bottleneck threshold</em> (e.g. "flagged if &gt; 20%") — use them to decide where to drill next.</span></span></h2>
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
        <summary>Metrics (no TMA hierarchy) <span class="badge" id="nontma-count">0</span><span class="help-tip" tabindex="0">?<span class="tip">This platform's perfmon JSON does not (yet) define a TMA tree. Instead, metrics are grouped by their <code>Category</code> field (Freq / BW / IO / NUMA / …). Common on newer E-core-only servers where Intel has released event data but not yet the full TMA hierarchy.</span></span></summary>
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
