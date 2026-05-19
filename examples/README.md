# Examples

Runnable examples demonstrating each aspect of perfmon-skills.

## Prerequisites

```bash
pip install -e .
# Ensure ./perfmon symlink or PERFMON_DATA points to intel/perfmon repo
```

## Files

| Example | Requires Hardware? | What it shows |
|---------|-------------------|---------------|
| `01_quick_start.sh` | No (uses SPR data) | All 5 CLI commands in action |
| `02_tma_drilldown.py` | No (synthetic data) | Full TMA drill-down workflow step-by-step |
| `03_trace_visualization.py` | No | Decision tracing DAG in all 4 output formats |
| `04_perf_output_parsing.py` | No | Parsing real perf stat output (text + JSON) |

## Quick Start

```bash
# See all commands at a glance
bash examples/01_quick_start.sh

# Understand the TMA drill-down methodology
python examples/02_tma_drilldown.py

# See how decision tracing works
python examples/03_trace_visualization.py

# Understand perf output parsing and event normalization
python examples/04_perf_output_parsing.py
```

## On Real Hardware (Intel)

```bash
# Start an actual investigation
perfmon-skills recommend start --cmd "./my_workload"

# Run the suggested perf command, then:
perf stat -j -e ... -- ./my_workload 2> perf_out.txt
perfmon-skills recommend analyze --input perf_out.txt

# Repeat until investigation completes (typically 3-5 steps)
```
