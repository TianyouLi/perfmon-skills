# perfmon-skills

Performance analysis toolkit built on [Intel perfmon](https://github.com/intel/perfmon) data. Provides CLI tools and Claude Code slash commands for streamlined performance investigation on Intel platforms.

## What it does

- **Event/metric lookup** — Search 2600+ PMU events and 300+ TMA metrics across 50+ Intel platforms
- **Command generation** — Generate ready-to-run `perf stat` commands with counter budget awareness
- **Cross-platform comparison** — Diff events and metrics between platform generations (e.g., ICX → SPR)
- **TMA drill-down** — Iterative recommendation engine that automates the Top-down Microarchitecture Analysis methodology
- **Decision tracing** — Record and visualize every decision as an inspectable DAG (Mermaid, DOT, HTML)
- **Architecture event map** — Interactive HTML browser that classifies every event into a 4-level uarch hierarchy (core pipeline + uncore/SoC), with acronym glossary and copy-paste perf snippets. GNR and CWF today.

## Installation

### Prerequisites

- Python 3.9+
- Linux with `perf` tool (for actual data collection; not needed for lookup/comparison/examples)

### Clone and install

```bash
git clone --recurse-submodules https://github.com/TianyouLi/perfmon-skills.git
cd perfmon-skills
pip install -e .
```

If you already cloned without `--recurse-submodules`:

```bash
git submodule update --init
```

### Verify installation

```bash
perfmon-skills --help
perfmon-skills lookup "cache miss" --platform SPR
```

### Install as Claude Code skills

perfmon-skills includes slash commands that integrate directly with [Claude Code](https://claude.ai/code). To install:

```bash
# Option 1: Add to your project (skills available in that project only)
cp -r /path/to/perfmon-skills/skills/*.md /your/project/.claude/skills/

# Option 2: Add to your global Claude Code configuration (available everywhere)
mkdir -p ~/.claude/skills
cp /path/to/perfmon-skills/skills/*.md ~/.claude/skills/
```

After installation, the following slash commands become available in Claude Code:

| Command | Description |
|---------|-------------|
| `/perf-lookup` | Search for Intel PMU events and TMA metrics |
| `/perf-cmdgen` | Generate ready-to-run `perf stat` commands |
| `/perf-compare` | Compare events/metrics across platform generations |
| `/perf-recommend` | Run a guided TMA drill-down investigation |

The skills invoke the CLI with `--format json` and interpret results conversationally.

**Note:** The `perfmon-skills` CLI must be on your PATH (installed via `pip install -e .`) for the skills to work. The skills also need access to the perfmon data — either via the `PERFMON_DATA` environment variable or by running from within the perfmon-skills directory.

## Quick Start

### Search for events

```bash
$ perfmon-skills lookup "cache miss" --platform SPR
======================================================================
EVENTS (SPR) — 67 matches
======================================================================
  L2_RQSTS.DEMAND_DATA_RD_MISS
    Demand Data Read miss L2 cache
    Code: 0x24, UMask: 0x21, Counter: 0,1,2,3, PEBS: 0
  ...
```

### Generate perf commands

```bash
$ perfmon-skills cmdgen --tma-level 1 --platform SPR
# TMA Level 1 (4 nodes) [SPR]
# Events: 6 (GP: 1, Fixed: 0, PerfMetrics: 5)
# Counters available: 12 (GP: 8)

perf stat -e cpu/INT_MISC.UOP_DROPPING/,topdown-be-bound,topdown-bad-spec,topdown-fe-bound,topdown-retiring,slots sleep 5
```

### Compare platforms

```bash
$ perfmon-skills compare ICX SPR --type metrics
======================================================================
ICX → SPR Comparison (metrics)
======================================================================
  Added metrics:   26
  Removed metrics: 8
  Changed metrics: 91
```

### Run a guided investigation

```bash
$ perfmon-skills recommend start --platform SPR --cmd "./my_workload"
======================================================================
NEW INVESTIGATION SESSION
======================================================================
  Platform: SPR
  Counter budget: ...

  STEP 1: Run this command and feed the output back:

  perf stat -j -e cpu/INT_MISC.UOP_DROPPING/,topdown-be-bound,... -- ./my_workload

$ perf stat -j -e <events> -- ./my_workload 2> step1.txt
$ perfmon-skills recommend analyze --input step1.txt
======================================================================
ANALYSIS — Step 1 [COLLECTING]
======================================================================
  Path: Backend_Bound

  Node Values:
    Backend_Bound                      50.0% ◀ BOTTLENECK
    Frontend_Bound                     25.0%
    Retiring                           17.0%
    Bad_Speculation                     8.0%

  NEXT STEP: Run this command:
  perf stat -j -e ... -- ./my_workload
```

Repeat until the investigation reaches a leaf node with tuning guidance.

### Browse the uarch event map

```bash
$ perfmon-skills arch-map --platform GNR --out gnr.html
Wrote gnr.html (1,548,432 bytes)
```

Open the file in a browser: clickable SVG on the left (core pipeline + uncore/SoC),
event list and full details (with acronym expansions and ready-to-run `perf stat`/`perf record`
commands) on the right. Search box in the header finds any event by name.

### Visualize decision trace

```bash
$ PERFMON_TRACE=1 perfmon-skills recommend start --platform SPR --cmd "./workload"
# ... run investigation steps ...
$ perfmon-skills trace --last --format mermaid
graph TD
    d001[start_investigation\nSelected SPR platform]
    d002[evaluate_l1\nBackend_Bound=50%]
    d001 -->|L1 TMA computed| d002
    d003[select_bottleneck\nChose Backend_Bound]
    d002 -->|threshold passed| d003
    ...
```

## Examples

The `examples/` directory contains runnable scripts that work without real hardware:

```bash
bash examples/01_quick_start.sh          # All CLI commands at a glance
python examples/02_tma_drilldown.py      # Full iterative drill-down with synthetic data
python examples/03_trace_visualization.py # Decision tracing in all 4 formats
python examples/04_perf_output_parsing.py # Perf output parsing and event normalization
```

See [examples/README.md](examples/README.md) for captured output from each example.

## Architecture

```
perfmon-skills/
├── perfmon/                  # git submodule → intel/perfmon data
├── src/perfmon_tools/
│   ├── core/                 # Platform detection, catalog, TMA tree, formula eval,
│   │                         # perf output parsing, context budget, decision tracing,
│   │                         # arch-map classifier, glossary
│   ├── lookup/               # Event/metric search
│   ├── cmdgen/               # Perf command generation
│   ├── compare/              # Cross-platform diff
│   ├── recommend/            # TMA drill-down engine (state machine, session mgmt,
│   │                         # coverage tracking, tuning guidance)
│   ├── archmap/              # Uarch event-map HTML renderer + perf-example generator
│   └── cli/                  # CLI entry points (lookup, cmdgen, compare, recommend,
│                             # trace, arch-map)
├── skills/                   # Claude Code slash commands
├── examples/                 # Runnable demos with output
└── tests/                    # Test suite (pytest)
```

### Design principles

- **Zero mandatory dependencies** — stdlib only (`json`, `csv`, `re`, `pathlib`, `subprocess`)
- **Deterministic core** — TMA drill-down runs without an LLM; the LLM layer (skills) adds interpretation
- **Context budget aware** — raw perf output stays on disk; only compact findings (~200 tokens/step) flow between steps
- **Counter budget aware** — knows platform-specific counter counts (SPR: 8 GP + 4 fixed) to minimize multiplexing
- **Session persistence** — plain JSON files, trivially inspectable and shareable

## Supported Platforms

All platforms in Intel's perfmon repository are supported, including:

| Platform | Codename | TMA Levels |
|----------|----------|------------|
| SPR | Sapphire Rapids | 6 |
| EMR | Emerald Rapids | 6 |
| GNR | Granite Rapids | 6 |
| ICX | Ice Lake Server | 5 |
| SKX/CLX | Skylake/Cascade Lake | 4 |
| ADL/RPL | Alder Lake/Raptor Lake (hybrid) | 5 |
| MTL/ARL | Meteor Lake/Arrow Lake (hybrid) | 5 |

And 40+ more. Run `perfmon-skills lookup --cross-arch "your_query"` to search across all.

## Development

```bash
pip install -e ".[dev]"
python -m pytest tests/ -v
```

## License

BSD-3-Clause
