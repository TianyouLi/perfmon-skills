"""Tests for the metrics section of the arch-map HTML payload."""

import pytest

from perfmon_tools.archmap.render import _build_payload
from perfmon_tools.core.arch_map import build_arch_map
from perfmon_tools.core.catalog import PlatformCatalog
from perfmon_tools.core.platform import CpuInfo, list_platforms, resolve_platform


def _catalog_for(shortname: str) -> PlatformCatalog:
    plats = list_platforms()
    p = next((pp for pp in plats if pp.shortname == shortname), None)
    if p is None:
        pytest.skip(f"platform {shortname} not present")
    model_hex = p.family_model.split("-")[-1].split("[")[0]
    cpu = CpuInfo(vendor="GenuineIntel", family=6, model=int(model_hex, 16),
                  stepping=0, model_name="", family_model=p.family_model)
    return PlatformCatalog(resolve_platform(cpu))


def _payload(shortname):
    cat = _catalog_for(shortname)
    return _build_payload(build_arch_map(cat), catalog=cat)


def test_gnr_payload_has_tma_tree():
    p = _payload("GNR")
    assert len(p["tma_roots"]) == 4
    root_names = {r["name"] for r in p["tma_roots"]}
    assert root_names == {"Frontend_Bound", "Bad_Speculation", "Backend_Bound", "Retiring"}


def test_gnr_payload_metric_count_matches_catalog():
    cat = _catalog_for("GNR")
    p = _build_payload(build_arch_map(cat), catalog=cat)
    assert len(p["metrics"]) == len(cat.metrics)


def test_metric_formula_is_expanded():
    """The serialized formula should have event/constant names, not a,b,c aliases."""
    p = _payload("GNR")
    m = p["metrics"]["DRAM_Bound"]
    # DRAM_Bound uses MEMORY_ACTIVITY.STALLS_L3_MISS and CPU_CLK_UNHALTED.THREAD
    assert "MEMORY_ACTIVITY" in m["formula_expanded"]
    assert "CPU_CLK_UNHALTED" in m["formula_expanded"]


def test_bottlenecks_appear_on_gnr():
    p = _payload("GNR")
    assert len(p["bottlenecks"]) >= 10
    # Sanity: bottleneck names start with 'Bottleneck_'
    for name in p["bottlenecks"]:
        assert name.startswith("Bottleneck_")


def test_info_groups_populated_on_gnr():
    p = _payload("GNR")
    # Should have several distinct group prefixes
    assert len(p["info_groups"]) >= 5
    # Every info metric is present in exactly one group
    all_info = sum(len(v) for v in p["info_groups"].values())
    assert all_info > 100


def test_event_used_by_metrics_reverse_index():
    """Every event referenced by any metric should appear in some metric's
    formula and get a used_by entry."""
    p = _payload("GNR")
    ev = p["events"].get("INST_RETIRED.ANY")
    assert ev is not None
    # INST_RETIRED.ANY is used by many metrics (>= 30 conservatively)
    assert len(ev["used_by"]) >= 30
    # And each entry should be a real metric key
    for m in ev["used_by"]:
        assert m in p["metrics"]


def test_cwf_has_no_tma_tree_but_has_flat_categories():
    """CWF has 44 metrics but no TMA hierarchy; they should show up in
    non_tma_categories instead."""
    p = _payload("CWF")
    assert len(p["tma_roots"]) == 0
    assert len(p["non_tma_categories"]) > 0
    all_flat = sum(len(v) for v in p["non_tma_categories"].values())
    assert all_flat > 0


def test_threshold_metrics_carry_glosses():
    """L1 TMA nodes have thresholds — serialized form should include them."""
    p = _payload("GNR")
    fb = p["metrics"]["Frontend_Bound"]
    assert fb["threshold_formula"]
    assert fb["threshold_gloss"].startswith("Bottleneck when ")


def test_tma_tree_children_are_ordered_by_level():
    """A parent's children should include only that parent's direct kids."""
    p = _payload("GNR")
    be = next(r for r in p["tma_roots"] if r["name"] == "Backend_Bound")
    child_names = {c["name"] for c in be["children"]}
    assert child_names == {"Core_Bound", "Memory_Bound"}


def test_pseudo_events_synthesized():
    """PERF_METRICS.* and TSC are referenced by metrics but not in perfmon's
    events JSON — they should appear as synthetic entries with pseudo=True."""
    p = _payload("GNR")
    assert "PERF_METRICS.FRONTEND_BOUND" in p["events"]
    pf = p["events"]["PERF_METRICS.FRONTEND_BOUND"]
    assert pf.get("pseudo") is True
    assert "fixed-function counter" in pf["public"] or "TMA" in pf["brief"]
    # Used-by should be populated for pseudo events too
    assert "Frontend_Bound" in pf["used_by"]


def test_pseudo_events_have_no_perf_block():
    """Pseudo events don't get regular perf stat/record snippets."""
    p = _payload("GNR")
    pf = p["events"]["PERF_METRICS.BACKEND_BOUND"]
    assert pf["perf"] is None
