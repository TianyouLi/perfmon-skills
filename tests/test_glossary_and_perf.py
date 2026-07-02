"""Tests for glossary lookup and perf-example generation."""

import pytest

from perfmon_tools.core.glossary import ACRONYMS, find_acronyms, note_for_path
from perfmon_tools.core.catalog import PlatformCatalog
from perfmon_tools.core.platform import CpuInfo, list_platforms, resolve_platform
from perfmon_tools.archmap.perf_examples import build_examples


def _catalog_for(shortname):
    plats = list_platforms()
    p = next((pp for pp in plats if pp.shortname == shortname), None)
    if p is None:
        pytest.skip(f"{shortname} not present")
    model_hex = p.family_model.split("-")[-1].split("[")[0]
    cpu = CpuInfo(vendor="GenuineIntel", family=6, model=int(model_hex, 16),
                  stepping=0, model_name="", family_model=p.family_model)
    return PlatformCatalog(resolve_platform(cpu))


def test_glossary_covers_common_acronyms():
    """Sanity: the essentials are there."""
    for key in ("TOR", "STLB", "DTLB", "RFO", "PEBS", "CHA", "IMC", "OCR", "DRD"):
        assert key in ACRONYMS, f"{key} missing from glossary"


def test_find_acronyms_returns_whole_tokens():
    """Match only whole tokens — 'CAS' should NOT match 'because'."""
    hits = find_acronyms("This event fires because a load hit the DTLB then the STLB.")
    tokens = {h[0] for h in hits}
    assert "DTLB" in tokens and "STLB" in tokens
    assert "CAS" not in tokens  # not present as whole word


def test_find_acronyms_deduplicates():
    hits = find_acronyms("TOR TOR TOR")
    tokens = [h[0] for h in hits]
    assert tokens == ["TOR"]


def test_note_for_path_uses_longest_prefix():
    """Leaf inherits from the closest ancestor with a note."""
    # Direct hit at leaf
    assert note_for_path(("coherence_llc", "tor", "ia", "drd")) is not None
    # 3-deep path — walks up ia → tor → coherence_llc (whichever hits first)
    got = note_for_path(("coherence_llc", "tor", "ia"))
    assert got is not None and "IA_" in got.upper() or "IA" in got
    # No note anywhere on the path → None
    assert note_for_path(("truly_not_a_cell",)) is None


def test_note_for_path_returns_none_for_unknown():
    assert note_for_path(("nonexistent",)) is None


def test_perf_examples_core_event_uses_symbolic_name():
    cat = _catalog_for("GNR")
    ev = cat.get_event("BR_MISP_RETIRED.ALL_BRANCHES")
    assert ev is not None
    out = build_examples(ev)
    assert "BR_MISP_RETIRED.ALL_BRANCHES" in out["stat"]
    assert out["stat"].startswith("perf stat -e ")
    # It's a PEBS-capable event → :ppp appears in record
    assert ":ppp" in out["record"]
    # Raw fallback references event=/umask=
    assert "event=0x" in out["raw"]


def test_perf_examples_uncore_event_uses_pmu_prefix():
    cat = _catalog_for("GNR")
    ev = cat.get_event("UNC_CHA_TOR_INSERTS.IA_MISS_DRD")
    assert ev is not None
    out = build_examples(ev)
    assert "uncore_cha/" in out["stat"]
    assert "event=0x" in out["stat"]
    # Uncore requires -a
    assert "-a" in out["stat"]


def test_perf_examples_imc_uses_uncore_imc():
    cat = _catalog_for("GNR")
    ev = cat.get_event("UNC_M_CAS_COUNT_SCH0.RD")
    assert ev is not None
    out = build_examples(ev)
    assert "uncore_imc/" in out["stat"]
