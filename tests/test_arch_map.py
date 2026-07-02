"""Tests for the architectural event-map classifier."""

import pytest

from perfmon_tools.core.arch_map import build_arch_map
from perfmon_tools.core.catalog import PlatformCatalog
from perfmon_tools.core.platform import CpuInfo, list_platforms, resolve_platform


def _catalog_for(shortname: str) -> PlatformCatalog:
    plats = list_platforms()
    p = next((pp for pp in plats if pp.shortname == shortname), None)
    if p is None:
        pytest.skip(f"platform {shortname} not present in perfmon data")
    model_hex = p.family_model.split("-")[-1].split("[")[0]
    cpu = CpuInfo(
        vendor="GenuineIntel", family=6, model=int(model_hex, 16), stepping=0,
        model_name="", family_model=p.family_model,
    )
    return PlatformCatalog(resolve_platform(cpu))


@pytest.mark.parametrize("shortname", ["GNR", "CWF"])
def test_all_events_accounted_for(shortname):
    """Every non-deprecated event lands in exactly one cell."""
    catalog = _catalog_for(shortname)
    am = build_arch_map(catalog)

    non_deprecated = [e for e in catalog.events if not e.deprecated]
    total_in_cells = sum(c.count for c in am.core_cells) + sum(
        c.count for c in am.uncore_cells
    )
    assert total_in_cells == len(non_deprecated), (
        f"cells hold {total_in_cells} but catalog has {len(non_deprecated)} non-deprecated events"
    )


@pytest.mark.parametrize("shortname", ["GNR", "CWF"])
def test_no_unmapped_events(shortname):
    """The classifier rules cover 100% of GNR/CWF events."""
    catalog = _catalog_for(shortname)
    am = build_arch_map(catalog)
    unmapped = am.core_unmapped + am.uncore_unmapped
    assert unmapped == 0, (
        f"{shortname}: {unmapped} unmapped events — "
        f"core={am.core_unmapped}, uncore={am.uncore_unmapped}"
    )


def test_gnr_pcore_assignments():
    """Spot-check a few known-good GNR assignments."""
    am = build_arch_map(_catalog_for("GNR"))
    by_cell = {c.id: {e.name for e in c.events} for c in am.core_cells}

    assert "BR_MISP_RETIRED.ALL_BRANCHES" in by_cell["fe_fetch"]
    assert "IDQ.MITE_UOPS" in by_cell["fe_decode"]
    assert "UOPS_DISPATCHED.PORT_0" in by_cell["be_execute"] or any(
        n.startswith("UOPS_DISPATCHED.") for n in by_cell["be_execute"]
    )
    assert any(n.startswith("L2_RQSTS.") for n in by_cell["mem_l2"])
    assert any(n.startswith("MEM_LOAD_L3_MISS_RETIRED.") for n in by_cell["mem_l3"])
    assert any(n.startswith("MACHINE_CLEARS.") for n in by_cell["bad_spec"])


def test_cwf_ecore_assignments():
    """Spot-check CWF E-core cells reflect the E-core vocabulary."""
    am = build_arch_map(_catalog_for("CWF"))
    by_cell = {c.id: {e.name for e in c.events} for c in am.core_cells}

    assert any(n.startswith("TOPDOWN_FE_BOUND.") for n in by_cell["fe_decode"])
    assert any(n.startswith("TOPDOWN_BAD_SPECULATION.") for n in by_cell["bad_spec"])
    assert any(n.startswith("MEM_UOPS_RETIRED.") for n in by_cell["mem_l1"])
    assert any(n.startswith("L2_REQUEST.") for n in by_cell["mem_l2"])


def test_uncore_units_route_correctly():
    """Uncore events group by Unit, not by name."""
    am = build_arch_map(_catalog_for("GNR"))
    by_cell = {c.id: c.events for c in am.uncore_cells}
    for ev in by_cell["coherence_llc"]:
        assert ev.raw.get("Unit") in {"CHA", "CHACMS"}
    for ev in by_cell["memory_ctrl"]:
        assert ev.raw.get("Unit") in {"IMC", "B2CMI", "MDF"}


def test_gnr_has_cxl_events():
    """GNR carries B2CXL / CXLCM / CXLDP events."""
    cxl = next(c for c in build_arch_map(_catalog_for("GNR")).uncore_cells if c.id == "cxl")
    units = {ev.raw.get("Unit") for ev in cxl.events}
    assert cxl.count >= 3
    assert units & {"B2CXL", "CXLCM", "CXLDP"}


def _walk(node, path):
    """Yield (path_tuple, node) for every node in the tree, including the root."""
    yield path, node
    for k in getattr(node, "subcomponents", []) or []:
        yield from _walk(k, path + (k.id,))


@pytest.mark.parametrize("shortname", ["GNR", "CWF"])
def test_subcomponent_totals_match_cell(shortname):
    """At every level, sum of children counts equals the parent count."""
    am = build_arch_map(_catalog_for(shortname))
    for cell in list(am.core_cells) + list(am.uncore_cells):
        for path, node in _walk(cell, (cell.id,)):
            kids = getattr(node, "subcomponents", []) or []
            if not kids:
                continue
            s = sum(k.count for k in kids)
            assert s == node.count, (
                f"{shortname}/{'/'.join(path)}: children sum to {s} but node has {node.count}"
            )


@pytest.mark.parametrize("shortname", ["GNR", "CWF"])
def test_no_other_bucket_anywhere(shortname):
    """At every level, the 'Other' bucket should be empty."""
    am = build_arch_map(_catalog_for(shortname))
    for cell in list(am.core_cells) + list(am.uncore_cells):
        for path, node in _walk(cell, (cell.id,)):
            if node.id == "other" and node.count > 0:
                sample = [ev.name for ev in getattr(node, "events", [])][:5]
                raise AssertionError(
                    f"{shortname}/{'/'.join(path)}: 'Other' has {node.count} events, e.g. {sample}"
                )


def test_gnr_tor_ia_opcode_split():
    """GNR TOR/IA should split into 7 opcode-class buckets."""
    am = build_arch_map(_catalog_for("GNR"))
    cha = next(c for c in am.uncore_cells if c.id == "coherence_llc")
    tor = next(s for s in cha.subcomponents if s.id == "tor")
    ia = next(s for s in tor.subcomponents if s.id == "ia")
    ids = {k.id for k in ia.subcomponents}
    assert {"drd", "own", "crd", "pref", "wb", "nc", "agg"} == ids


def test_gnr_imc_split():
    am = build_arch_map(_catalog_for("GNR"))
    mc = next(c for c in am.uncore_cells if c.id == "memory_ctrl")
    imc = next(s for s in mc.subcomponents if s.id == "imc")
    ids = {k.id for k in imc.subcomponents}
    assert {"cas", "queues", "cmds", "pwr", "thr", "clk"} <= ids


def test_gnr_iio_split():
    am = build_arch_map(_catalog_for("GNR"))
    pcie = next(c for c in am.uncore_cells if c.id == "pcie_io")
    iio = next(s for s in pcie.subcomponents if s.id == "iio")
    ids = {k.id for k in iio.subcomponents}
    assert {"data", "txn", "compbuf", "iommu"} <= ids


def test_gnr_subcomponent_shape():
    """Spot-check GNR subcomponent structure."""
    am = build_arch_map(_catalog_for("GNR"))
    by_cell = {c.id: c for c in am.core_cells + am.uncore_cells}

    fe = by_cell["fe_fetch"]
    sub_ids = {s.id for s in fe.subcomponents}
    assert {"bpu", "itlb", "icache", "fe_sample"} <= sub_ids

    l3 = by_cell["mem_l3"]
    sub_ids = {s.id for s in l3.subcomponents}
    assert {"ocr", "offcore", "l3_hit", "l3_miss"} <= sub_ids

    cha = by_cell["coherence_llc"]
    sub_ids = {s.id for s in cha.subcomponents}
    assert {"tor", "llc", "requests"} <= sub_ids


def test_cwf_subcomponent_shape():
    """Spot-check CWF subcomponent structure."""
    am = build_arch_map(_catalog_for("CWF"))
    by_cell = {c.id: c for c in am.core_cells + am.uncore_cells}

    fe = by_cell["fe_decode"]
    sub_ids = {s.id for s in fe.subcomponents}
    # CWF fe_decode has TOPDOWN_FE_BOUND + MS_DECODED
    assert "fe_bound" in sub_ids

    mem_l1 = by_cell["mem_l1"]
    sub_ids = {s.id for s in mem_l1.subcomponents}
    assert {"lsu", "stalls", "dtlb"} <= sub_ids
