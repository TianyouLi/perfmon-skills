"""Classify perfmon events into architectural components for diagramming.

The chip is decomposed into a fixed set of cells (Frontend, Backend, Memory,
etc. for the core; Coherence/LLC, Memory Controller, UPI, PCIe, CXL, Power/Sys
for the uncore). Each event lands in exactly one cell based on:

  - uncore: the `Unit` field (CHA, IMC, UPI LL, IIO, ...)
  - core: the leading token(s) of `EventName` matched against per-uarch rules

Events that don't match any rule land in an `Unclassified` cell so gaps in
the mapping are visible instead of silently dropped.
"""

from dataclasses import dataclass, field
from typing import Optional

from .catalog import EventDef, PlatformCatalog


# Uncore Unit -> (cell_id, cell_title). Same table for all server uarchs today.
UNCORE_UNIT_TO_CELL = {
    "CHA":     ("coherence_llc", "Coherence / LLC"),
    "CHACMS":  ("coherence_llc", "Coherence / LLC"),
    "IMC":     ("memory_ctrl",   "Memory Controller"),
    "B2CMI":   ("memory_ctrl",   "Memory Controller"),
    "MDF":     ("memory_ctrl",   "Memory Controller"),
    "UPI LL":  ("upi",           "UPI (socket interconnect)"),
    "B2UPI":   ("upi",           "UPI (socket interconnect)"),
    "IIO":     ("pcie_io",       "PCIe / IO"),
    "IRP":     ("pcie_io",       "PCIe / IO"),
    "B2HOT":   ("pcie_io",       "PCIe / IO"),
    "CXLCM":   ("cxl",           "CXL"),
    "CXLDP":   ("cxl",           "CXL"),
    "B2CXL":   ("cxl",           "CXL"),
    "PCU":     ("power_sys",     "Power / System"),
    "UBOX":    ("power_sys",     "Power / System"),
}


# Core cells share this display order across uarchs.
CORE_CELL_TITLES = {
    "fe_fetch":     "Frontend — Fetch / Predict",
    "fe_decode":    "Frontend — Decode / Deliver",
    "bad_spec":     "Bad Speculation",
    "be_alloc":     "Backend — Rename / Alloc / Retire",
    "be_execute":   "Backend — Execute (EUs / Ports)",
    "mem_l1":       "Memory — L1 / LSU / TLB",
    "mem_l2":       "Memory — L2",
    "mem_l3":       "Memory — L3 / Offcore",
    "misc_pmu":     "Misc / PMU",
    "unclassified": "Unclassified",
}


# GNR (P-core) rules. Order matters: first prefix match wins.
# Each entry is (prefix, cell_id). Prefix matched against EventName after
# splitting on the first '.'.
GNR_CORE_RULES = [
    # Frontend — fetch & predict
    ("BR_MISP_RETIRED",              "fe_fetch"),
    ("BR_INST_RETIRED",              "fe_fetch"),
    ("BACLEARS",                     "fe_fetch"),
    ("FRONTEND_RETIRED",             "fe_fetch"),
    ("ITLB_MISSES",                  "fe_fetch"),
    ("ICACHE_DATA",                  "fe_fetch"),
    ("ICACHE_TAG",                   "fe_fetch"),
    ("ICACHE",                       "fe_fetch"),

    # Frontend — decode & deliver
    ("IDQ_BUBBLES",                  "fe_decode"),
    ("IDQ_UOPS_NOT_DELIVERED",       "fe_decode"),
    ("IDQ",                          "fe_decode"),
    ("DSB2MITE_SWITCHES",            "fe_decode"),
    ("LSD",                          "fe_decode"),
    ("MS_DECODED",                   "fe_decode"),
    ("INST_DECODED",                 "fe_decode"),
    ("UOPS_DECODED",                 "fe_decode"),
    ("DECODE",                       "fe_decode"),

    # Bad speculation
    ("MACHINE_CLEARS",               "bad_spec"),
    ("RTM_RETIRED",                  "bad_spec"),
    ("TX_MEM",                       "bad_spec"),

    # Backend — alloc / retire
    ("TOPDOWN",                      "be_alloc"),
    ("INT_MISC",                     "be_alloc"),
    ("RESOURCE_STALLS",              "be_alloc"),
    ("RS",                           "be_alloc"),
    ("XQ",                           "be_alloc"),
    ("INST_RETIRED",                 "be_alloc"),
    ("UOPS_RETIRED",                 "be_alloc"),
    ("UOPS_ISSUED",                  "be_alloc"),
    ("ASSISTS",                      "be_alloc"),

    # Backend — execute
    ("UOPS_DISPATCHED",              "be_execute"),
    ("UOPS_EXECUTED",                "be_execute"),
    ("EXE_ACTIVITY",                 "be_execute"),
    ("EXE",                          "be_execute"),
    ("CYCLE_ACTIVITY",               "be_execute"),
    ("ARITH",                        "be_execute"),
    ("INT_VEC_RETIRED",              "be_execute"),
    ("FP_ARITH_DISPATCHED",          "be_execute"),
    ("FP_ARITH_INST_RETIRED",        "be_execute"),
    ("FP_ARITH_INST_RETIRED2",       "be_execute"),
    ("MISC2_RETIRED",                "be_execute"),

    # Memory — L1 / LSU / TLB
    ("L1D_PEND_MISS",                "mem_l1"),
    ("L1D",                          "mem_l1"),
    ("DTLB_LOAD_MISSES",             "mem_l1"),
    ("DTLB_STORE_MISSES",            "mem_l1"),
    ("MEM_INST_RETIRED",             "mem_l1"),
    ("MEM_UOP_RETIRED",              "mem_l1"),
    ("MEM_STORE_RETIRED",            "mem_l1"),
    ("LOAD_HIT_PREFETCH",            "mem_l1"),
    ("LOCK_CYCLES",                  "mem_l1"),
    ("LD_BLOCKS",                    "mem_l1"),
    ("MEM_LOAD_COMPLETED",           "mem_l1"),

    # Memory — L2
    ("L2_RQSTS",                     "mem_l2"),
    ("L2_REQUEST",                   "mem_l2"),
    ("L2_LINES_IN",                  "mem_l2"),
    ("L2_LINES_OUT",                 "mem_l2"),
    ("L2_TRANS",                     "mem_l2"),
    ("SQ_MISC",                      "mem_l2"),
    ("MEMORY_ACTIVITY",              "mem_l2"),

    # Memory — L3 / Offcore
    ("OCR",                          "mem_l3"),
    ("OFFCORE_REQUESTS_OUTSTANDING", "mem_l3"),
    ("OFFCORE_REQUESTS",             "mem_l3"),
    ("LONGEST_LAT_CACHE",            "mem_l3"),
    ("MEM_LOAD_L3_HIT_RETIRED",      "mem_l3"),
    ("MEM_LOAD_L3_MISS_RETIRED",     "mem_l3"),
    ("MEM_LOAD_RETIRED",             "mem_l3"),
    ("MEM_LOAD_MISC_RETIRED",        "mem_l3"),
    ("MEM_TRANS_RETIRED",            "mem_l3"),
    ("SW_PREFETCH_ACCESS",           "mem_l3"),

    # Misc / PMU counters
    ("CPU_CLK_UNHALTED",             "misc_pmu"),
    ("HW_INTERRUPTS",                "misc_pmu"),
    ("MISC_RETIRED",                 "misc_pmu"),
]


# CWF (E-core) rules. E-core vocabulary differs: TOPDOWN_* buckets are
# first-class events, no IDQ / LSD / OFFCORE prefix, MEM_UOPS_RETIRED instead
# of MEM_INST_RETIRED, etc.
CWF_CORE_RULES = [
    # Frontend
    ("BR_MISP_RETIRED",              "fe_fetch"),
    ("BR_INST_RETIRED",              "fe_fetch"),
    ("BACLEARS",                     "fe_fetch"),
    ("FRONTEND_RETIRED_SOURCE",      "fe_fetch"),
    ("FRONTEND_RETIRED",             "fe_fetch"),
    ("ITLB_MISSES",                  "fe_fetch"),
    ("ICACHE",                       "fe_fetch"),
    ("PREDICTION",                   "fe_fetch"),
    ("TOPDOWN_FE_BOUND",             "fe_decode"),
    ("MS_DECODED",                   "fe_decode"),

    # Bad speculation
    ("TOPDOWN_BAD_SPECULATION",      "bad_spec"),
    ("MACHINE_CLEARS",               "bad_spec"),
    ("SERIALIZATION",                "bad_spec"),

    # Backend — alloc / retire
    ("TOPDOWN_BE_BOUND",             "be_alloc"),
    ("TOPDOWN_RETIRING",             "be_alloc"),
    ("TOPDOWN",                      "be_alloc"),
    ("INST_RETIRED",                 "be_alloc"),
    ("UOPS_RETIRED",                 "be_alloc"),
    ("UOPS_ISSUED",                  "be_alloc"),
    ("LBR_INSERTS",                  "be_alloc"),
    ("MISC_RETIRED1",                "be_alloc"),
    ("MISC_RETIRED2",                "be_alloc"),

    # Backend — execute
    ("INT_UOPS_EXECUTED",            "be_execute"),
    ("FP_VINT_UOPS_EXECUTED",        "be_execute"),
    ("FP_FLOPS_RETIRED",             "be_execute"),
    ("FP_INST_RETIRED",              "be_execute"),
    ("ARITH",                        "be_execute"),

    # Memory — L1 / LSU / TLB
    ("MEM_LOAD_UOPS_L3_MISS_RETIRED", "mem_l3"),  # steer L3-miss variant first
    ("MEM_LOAD_UOPS_MISC_RETIRED",   "mem_l1"),
    ("MEM_LOAD_UOPS_RETIRED",        "mem_l1"),
    ("MEM_UOPS_RETIRED",             "mem_l1"),
    ("MEM_BOUND_STALLS_LOAD",        "mem_l1"),
    ("MEM_SCHEDULER_BLOCK",          "mem_l1"),
    ("MISALIGN_MEM_REF",             "mem_l1"),
    ("LD_HEAD",                      "mem_l1"),
    ("LD_BLOCKS",                    "mem_l1"),
    ("DTLB_LOAD_MISSES",             "mem_l1"),
    ("DTLB_STORE_MISSES",            "mem_l1"),

    # Memory — L2
    ("L2_REQUEST",                   "mem_l2"),
    ("L2_REJECT_XQ",                 "mem_l2"),
    ("CORE_REJECT_L2Q",              "mem_l2"),

    # Memory — L3 / Offcore
    ("OCR",                          "mem_l3"),
    ("LONGEST_LAT_CACHE",            "mem_l3"),

    # Misc / PMU
    ("CPU_CLK_UNHALTED",             "misc_pmu"),
]


CORE_RULES_BY_PLATFORM = {
    "GNR": GNR_CORE_RULES,
    "CWF": CWF_CORE_RULES,
}


# Subcomponent rules per (platform, cell_id).
# Each rule is (matcher, sub_id, sub_title). Matcher is either:
#   - a str: matched against EventName's first '.' token (or startswith prefix)
#   - a tuple ("unit", "CHA"): matches on the uncore Unit field
#   - a tuple ("contains", "TOR"): substring match on the full EventName
# First match wins. Events with no match land in an implicit "other" sub.
GNR_SUBCOMPONENTS = {
    "fe_fetch": [
        ("BR_MISP_RETIRED",   "bpu",       "Branch Predictor"),
        ("BR_INST_RETIRED",   "bpu",       "Branch Predictor"),
        ("BACLEARS",          "bpu",       "Branch Predictor"),
        ("ITLB_MISSES",       "itlb",      "ITLB"),
        ("ICACHE_DATA",       "icache",    "ICache"),
        ("ICACHE_TAG",        "icache",    "ICache"),
        ("FRONTEND_RETIRED",  "fe_sample", "FE Retirement Sampling"),
    ],
    "fe_decode": [
        ("IDQ_BUBBLES",             "idq",  "IDQ (delivery queue)"),
        ("IDQ_UOPS_NOT_DELIVERED",  "idq",  "IDQ (delivery queue)"),
        ("IDQ",                     "idq",  "IDQ (delivery queue)"),
        ("LSD",                     "lsd",  "LSD (loop stream)"),
        ("DSB2MITE_SWITCHES",       "dsb",  "DSB (uop cache)"),
        ("INST_DECODED",            "mite", "MITE (legacy decode)"),
        ("UOPS_DECODED",            "mite", "MITE (legacy decode)"),
        ("DECODE",                  "mite", "MITE (legacy decode)"),
    ],
    "be_alloc": [
        ("TOPDOWN",           "slots",  "TMA Slots"),
        ("INT_MISC",          "rename", "Rename / Alloc"),
        ("RESOURCE_STALLS",   "rename", "Rename / Alloc"),
        ("RS",                "rename", "Rename / Alloc"),
        ("XQ",                "rename", "Rename / Alloc"),
        ("UOPS_ISSUED",       "rename", "Rename / Alloc"),
        ("INST_RETIRED",      "retire", "Retirement"),
        ("UOPS_RETIRED",      "retire", "Retirement"),
        ("ASSISTS",           "retire", "Retirement"),
    ],
    "be_execute": [
        ("UOPS_DISPATCHED",       "ports",   "Ports / Dispatch"),
        ("UOPS_EXECUTED",         "ports",   "Ports / Dispatch"),
        ("EXE_ACTIVITY",          "stalls",  "Execution Stalls"),
        ("EXE",                   "stalls",  "Execution Stalls"),
        ("CYCLE_ACTIVITY",        "stalls",  "Execution Stalls"),
        ("ARITH",                 "int_alu", "INT ALUs"),
        ("INT_VEC_RETIRED",       "int_alu", "INT ALUs"),
        ("FP_ARITH_DISPATCHED",   "fp_vec",  "FP / Vector"),
        ("FP_ARITH_INST_RETIRED", "fp_vec",  "FP / Vector"),
        ("FP_ARITH_INST_RETIRED2", "fp_vec", "FP / Vector"),
        ("MISC2_RETIRED",         "stalls",  "Execution Stalls"),
    ],
    "mem_l1": [
        ("L1D_PEND_MISS",     "l1d",   "L1D Cache"),
        ("L1D",               "l1d",   "L1D Cache"),
        ("LOAD_HIT_PREFETCH", "l1d",   "L1D Cache"),
        ("MEM_LOAD_COMPLETED","l1d",   "L1D Cache"),
        ("DTLB_LOAD_MISSES",  "dtlb",  "DTLB"),
        ("DTLB_STORE_MISSES", "dtlb",  "DTLB"),
        ("MEM_INST_RETIRED",  "lsu",   "LSU / Memory Ordering"),
        ("MEM_UOP_RETIRED",   "lsu",   "LSU / Memory Ordering"),
        ("MEM_STORE_RETIRED", "lsu",   "LSU / Memory Ordering"),
        ("LD_BLOCKS",         "lsu",   "LSU / Memory Ordering"),
        ("LOCK_CYCLES",       "lsu",   "LSU / Memory Ordering"),
    ],
    "mem_l3": [
        ("OCR",                          "ocr",       "OCR Response Matrix"),
        ("OFFCORE_REQUESTS_OUTSTANDING", "offcore",   "Offcore Requests"),
        ("OFFCORE_REQUESTS",             "offcore",   "Offcore Requests"),
        ("MEM_LOAD_L3_HIT_RETIRED",      "l3_hit",    "L3 Hit"),
        ("MEM_LOAD_L3_MISS_RETIRED",     "l3_miss",   "L3 Miss / DRAM"),
        ("MEM_LOAD_RETIRED",             "l3_hit",    "L3 Hit"),
        ("MEM_LOAD_MISC_RETIRED",        "l3_hit",    "L3 Hit"),
        ("MEM_TRANS_RETIRED",            "l3_hit",    "L3 Hit"),
        ("SW_PREFETCH_ACCESS",           "prefetch",  "SW Prefetch"),
        ("LONGEST_LAT_CACHE",            "llc_ref",   "LLC Ref/Miss"),
    ],
    "coherence_llc": [
        (("unit", "CHACMS"),         "chacms", "CHACMS (mesh stop)"),
        (("contains", "_CHA_TOR"),   "tor",    "TOR (Table of Requests)"),
        (("contains", "_CHA_LLC"),   "llc",    "LLC Cache"),
        (("contains", "_CHA_SF"),    "sf",     "Snoop Filter"),
        (("contains", "_CHA_DIR"),   "dir",    "Directory"),
        (("contains", "_CHA_REQUESTS"), "requests", "Requests"),
        (("contains", "_CHA_REMOTE"), "remote", "Remote Snoop"),
        (("contains", "_CHA_OSB"),   "osb",    "OSB (Snoop Broadcast)"),
        (("contains", "_CHA_IMC"),   "imc_traffic", "IMC Traffic"),
        (("contains", "_CHA_MISC"),  "misc_cha", "CHA Misc / Ingress"),
        (("contains", "_CHA_RxC"),   "misc_cha", "CHA Misc / Ingress"),
        (("contains", "_CHA_DISTRESS"), "misc_cha", "CHA Misc / Ingress"),
        (("contains", "_CHA_CLOCKTICKS"), "misc_cha", "CHA Misc / Ingress"),
    ],
    "memory_ctrl": [
        (("unit", "IMC"),   "imc",   "IMC (DDR channels)"),
        (("unit", "B2CMI"), "b2cmi", "B2CMI (mesh ↔ IMC bridge)"),
        (("unit", "MDF"),   "mdf",   "MDF (mesh fabric)"),
    ],
    "pcie_io": [
        (("unit", "IIO"),   "iio",   "IIO (PCIe root)"),
        (("unit", "IRP"),   "irp",   "IRP (I/O cache)"),
        (("unit", "B2HOT"), "b2hot", "B2HOT (hot-plug bridge)"),
    ],
    "upi": [
        (("unit", "UPI LL"), "upi_ll", "UPI Link Layer"),
        (("unit", "B2UPI"),  "b2upi",  "B2UPI (mesh ↔ UPI bridge)"),
    ],
}

# CWF (E-core) subcomponents. Some cells overlap with GNR — reuse rules where
# prefixes exist on both. E-core-specific prefixes get their own sub.
CWF_SUBCOMPONENTS = {
    "fe_fetch": [
        ("BR_MISP_RETIRED",         "bpu",       "Branch Predictor"),
        ("BR_INST_RETIRED",         "bpu",       "Branch Predictor"),
        ("BACLEARS",                "bpu",       "Branch Predictor"),
        ("PREDICTION",              "bpu",       "Branch Predictor"),
        ("ITLB_MISSES",             "itlb",      "ITLB"),
        ("ICACHE",                  "icache",    "ICache"),
        ("FRONTEND_RETIRED_SOURCE", "fe_sample", "FE Retirement Sampling"),
        ("FRONTEND_RETIRED",        "fe_sample", "FE Retirement Sampling"),
    ],
    "fe_decode": [
        ("TOPDOWN_FE_BOUND", "fe_bound", "TMA FE-bound buckets"),
        ("MS_DECODED",       "ms",       "MSROM"),
    ],
    "be_alloc": [
        ("TOPDOWN_BE_BOUND",  "slots",  "TMA BE-bound"),
        ("TOPDOWN_RETIRING",  "slots",  "TMA Retiring"),
        ("TOPDOWN",           "slots",  "TMA Slots"),
        ("UOPS_ISSUED",       "rename", "Rename / Alloc"),
        ("INST_RETIRED",      "retire", "Retirement"),
        ("UOPS_RETIRED",      "retire", "Retirement"),
        ("LBR_INSERTS",       "retire", "Retirement"),
        ("MISC_RETIRED1",     "retire", "Retirement"),
        ("MISC_RETIRED2",     "retire", "Retirement"),
    ],
    "be_execute": [
        ("INT_UOPS_EXECUTED",    "int_alu", "INT ALUs"),
        ("ARITH",                "int_alu", "INT ALUs"),
        ("FP_VINT_UOPS_EXECUTED","fp_vec",  "FP / Vector"),
        ("FP_FLOPS_RETIRED",     "fp_vec",  "FP / Vector"),
        ("FP_INST_RETIRED",      "fp_vec",  "FP / Vector"),
    ],
    "mem_l1": [
        ("MEM_UOPS_RETIRED",         "lsu",   "LSU (memory uops)"),
        ("MEM_LOAD_UOPS_RETIRED",    "lsu",   "LSU (memory uops)"),
        ("MEM_LOAD_UOPS_MISC_RETIRED","lsu",  "LSU (memory uops)"),
        ("MEM_BOUND_STALLS_LOAD",    "stalls","Load Stalls"),
        ("MEM_SCHEDULER_BLOCK",      "stalls","Load Stalls"),
        ("LD_HEAD",                  "stalls","Load Stalls"),
        ("LD_BLOCKS",                "stalls","Load Stalls"),
        ("MISALIGN_MEM_REF",         "stalls","Load Stalls"),
        ("DTLB_LOAD_MISSES",         "dtlb",  "DTLB"),
        ("DTLB_STORE_MISSES",        "dtlb",  "DTLB"),
    ],
    "mem_l3": [
        ("OCR",                            "ocr",     "OCR Response Matrix"),
        ("MEM_LOAD_UOPS_L3_MISS_RETIRED",  "l3_miss", "L3 Miss / DRAM"),
        ("LONGEST_LAT_CACHE",              "llc_ref", "LLC Ref/Miss"),
    ],
    # Uncore subs — same shape as GNR (Unit-based)
    "coherence_llc": [
        (("unit", "CHACMS"),            "chacms",     "CHACMS (mesh stop)"),
        (("contains", "_CHA_TOR"),      "tor",        "TOR (Table of Requests)"),
        (("contains", "_CHA_LLC"),      "llc",        "LLC Cache"),
        (("contains", "_CHA_SF"),       "sf",         "Snoop Filter"),
        (("contains", "_CHA_DIR"),      "dir",        "Directory"),
        (("contains", "_CHA_REQUESTS"), "requests",   "Requests"),
        (("contains", "_CHA_REMOTE"),   "remote",     "Remote Snoop"),
        (("contains", "_CHA_OSB"),      "osb",        "OSB (Snoop Broadcast)"),
        (("contains", "_CHA_IMC"),      "imc_traffic","IMC Traffic"),
        (("contains", "_CHA_MISC"),     "misc_cha",   "CHA Misc / Ingress"),
        (("contains", "_CHA_RxC"),      "misc_cha",   "CHA Misc / Ingress"),
        (("contains", "_CHA_DISTRESS"), "misc_cha",   "CHA Misc / Ingress"),
        (("contains", "_CHA_CLOCKTICKS"),"misc_cha",  "CHA Misc / Ingress"),
    ],
    "memory_ctrl": [
        (("unit", "IMC"),   "imc",   "IMC (DDR channels)"),
        (("unit", "B2CMI"), "b2cmi", "B2CMI (mesh ↔ IMC bridge)"),
        (("unit", "MDF"),   "mdf",   "MDF (mesh fabric)"),
    ],
    "pcie_io": [
        (("unit", "IIO"),   "iio",   "IIO (PCIe root)"),
        (("unit", "IRP"),   "irp",   "IRP (I/O cache)"),
        (("unit", "B2HOT"), "b2hot", "B2HOT (hot-plug bridge)"),
    ],
    "upi": [
        (("unit", "UPI LL"), "upi_ll", "UPI Link Layer"),
        (("unit", "B2UPI"),  "b2upi",  "B2UPI (mesh ↔ UPI bridge)"),
    ],
}

SUBCOMPONENTS_BY_PLATFORM = {
    "GNR": GNR_SUBCOMPONENTS,
    "CWF": CWF_SUBCOMPONENTS,
}


# ---------------------------------------------------------------------------
# Level-3 (and deeper) subcomponent rules. Keyed by tuple path:
#   ("coherence_llc", "tor") means: applied to the TOR sub of coherence_llc.
#   ("coherence_llc", "tor", "ia") means: applied to the IA sub of TOR.
# Same matcher grammar as level-2 rules. Reused across GNR and CWF where the
# uncore units are the same.
# ---------------------------------------------------------------------------

DEEP_SUBCOMPONENTS = {
    # ---- TOR (Table of Requests) split by requester type ----
    ("coherence_llc", "tor"): [
        (("contains", ".IA_"),         "ia",       "IA (core requests)"),
        (("contains", ".IA"),          "ia",       "IA (core requests)"),  # bare IA
        (("contains", ".IO_"),         "io",       "IO (device requests)"),
        (("contains", ".IO"),          "io",       "IO (device requests)"),
        (("contains", ".CXL_"),        "cxl",      "CXL requests"),
        (("contains", ".LOC_"),        "loc",      "Local requests"),
        (("contains", ".REM_"),        "rem",      "Remote requests"),
        (("contains", ".ALL"),         "all",      "Aggregate"),
        (("contains", ".LLC"),         "all",      "Aggregate"),
    ],
    # ---- TOR / IA further split by opcode class ----
    ("coherence_llc", "tor", "ia"): [
        # Aggregate first
        (("regex_suffix", r"^IA(_HIT|_MISS)?$"), "agg", "Aggregate (IA / IA_HIT / IA_MISS)"),
        # Prefetch
        (("contains_suffix", "LLCPREF"),         "pref",  "Prefetch"),
        # Code Read
        (("contains_suffix", "CRD"),             "crd",   "Code Read"),
        # Ownership (RFO + ITOM variants + SPECITOM)
        (("contains_suffix", "RFO"),             "own",   "Ownership (RFO / ITOM)"),
        (("contains_suffix", "ITOM"),            "own",   "Ownership (RFO / ITOM)"),
        (("contains_suffix", "SPECITOM"),        "own",   "Ownership (RFO / ITOM)"),
        # Writeback / Streaming Store (WCIL, WCILF, WB*, LOCAL/REMOTE NUMA-labelled WCIL)
        (("contains_suffix", "WCILF"),           "wb",    "Writeback / Streaming"),
        (("contains_suffix", "WCIL"),            "wb",    "Writeback / Streaming"),
        (("contains_suffix", "WBEFTOE"),         "wb",    "Writeback / Streaming"),
        (("contains_suffix", "WBEFTOI"),         "wb",    "Writeback / Streaming"),
        (("contains_suffix", "WBMTOE"),          "wb",    "Writeback / Streaming"),
        (("contains_suffix", "WBMTOI"),          "wb",    "Writeback / Streaming"),
        (("contains_suffix", "WBSTOI"),          "wb",    "Writeback / Streaming"),
        (("contains_suffix", "LOCAL_"),          "wb",    "Writeback / Streaming"),
        (("contains_suffix", "REMOTE_"),         "wb",    "Writeback / Streaming"),
        # Non-coherent / flush / CXL
        (("contains_suffix", "CLFLUSH"),         "nc",    "Non-coherent / Flush"),
        (("contains_suffix", "UCRDF"),           "nc",    "Non-coherent / Flush"),
        (("contains_suffix", "WIL"),             "nc",    "Non-coherent / Flush"),
        (("contains_suffix", "CXL"),             "nc",    "Non-coherent / Flush"),
        # Demand Read + Page-Walk (DRD, DRDPTE) — placed AFTER RFO/ITOM/etc
        (("contains_suffix", "DRDPTE"),          "drd",   "Demand Data Read"),
        (("contains_suffix", "DRD"),             "drd",   "Demand Data Read"),
    ],
    # ---- IMC split by function ----
    ("memory_ctrl", "imc"): [
        ("UNC_M_CAS_COUNT_SCH0",              "cas",    "CAS commands"),
        ("UNC_M_CAS_COUNT_SCH1",              "cas",    "CAS commands"),
        (("startswith", "UNC_M_RPQ"),         "queues", "Read/Write Queues"),
        (("startswith", "UNC_M_WPQ"),         "queues", "Read/Write Queues"),
        (("startswith", "UNC_M_RDB"),         "queues", "Read/Write Queues"),
        ("UNC_M_PRE_COUNT",                   "cmds",   "DDR Commands (ACT/PRE)"),
        ("UNC_M_ACT_COUNT",                   "cmds",   "DDR Commands (ACT/PRE)"),
        (("startswith", "UNC_M_POWERDOWN"),   "pwr",    "Powerdown / Refresh"),
        (("startswith", "UNC_M_SELF_REFRESH"),"pwr",    "Powerdown / Refresh"),
        (("startswith", "UNC_M_MR4"),         "pwr",    "Powerdown / Refresh"),
        (("startswith", "UNC_M_PDC_"),        "pwr",    "Powerdown / Refresh"),
        (("startswith", "UNC_M_MNTCMD_REFRATE"), "pwr", "Powerdown / Refresh"),
        (("startswith", "UNC_M_POWER_CHANNEL_PPD"), "pwr", "Powerdown / Refresh"),
        (("startswith", "UNC_M_POWER_THROTTLE"),         "thr", "Throttling"),
        (("startswith", "UNC_M_POWER_CRITICAL_THROTTLE"),"thr", "Throttling"),
        (("startswith", "UNC_M_THROTTLE"),               "thr", "Throttling"),
        (("startswith", "UNC_M_CLOCKTICKS"),  "clk",    "Clocks"),
        (("startswith", "UNC_M_HCLOCKTICKS"), "clk",    "Clocks"),
    ],
    # ---- B2CMI split by function ----
    ("memory_ctrl", "b2cmi"): [
        (("startswith", "UNC_B2CMI_DIRECTORY"),  "dir",     "Directory"),
        (("startswith", "UNC_B2CMI_TAG"),        "dir",     "Directory"),
        (("startswith", "UNC_B2CMI_DIRECT2CORE"),"d2core",  "Direct2Core"),
        (("startswith", "UNC_B2CMI_DIRECT2UPI"), "d2upi",   "Direct2UPI"),
        (("startswith", "UNC_B2CMI_IMC_READS"),  "imc_traffic","IMC Read/Write Traffic"),
        (("startswith", "UNC_B2CMI_IMC_WRITES"), "imc_traffic","IMC Read/Write Traffic"),
        (("startswith", "UNC_B2CMI_PREFCAM"),    "prefcam", "Prefetch CAM / Tracker"),
        (("startswith", "UNC_B2CMI_TRACKER"),    "prefcam", "Prefetch CAM / Tracker"),
        (("startswith", "UNC_B2CMI_WR_TRACKER"), "prefcam", "Prefetch CAM / Tracker"),
        (("startswith", "UNC_B2CMI_CLOCKTICKS"), "clk",     "Clocks"),
    ],
    # ---- IIO split by traffic class ----
    ("pcie_io", "iio"): [
        (("startswith", "UNC_IIO_DATA_REQ_OF_CPU"),  "data",   "Data Traffic (CPU↔device)"),
        (("startswith", "UNC_IIO_DATA_REQ_BY_CPU"),  "data",   "Data Traffic (CPU↔device)"),
        (("startswith", "UNC_IIO_TXN_REQ_OF_CPU"),   "txn",    "Transaction Requests"),
        (("startswith", "UNC_IIO_TXN_REQ_BY_CPU"),   "txn",    "Transaction Requests"),
        (("startswith", "UNC_IIO_NUM_REQ_OF_CPU_BY_TGT"), "txn","Transaction Requests"),
        (("startswith", "UNC_IIO_NUM_OUTSTANDING_REQ"), "txn", "Transaction Requests"),
        (("startswith", "UNC_IIO_COMP_BUF"),         "compbuf","Completion Buffer"),
        (("startswith", "UNC_IIO_IOMMU"),            "iommu",  "IOMMU"),
        (("startswith", "UNC_IIO_CLOCKTICKS"),       "misc",   "Misc / Clocks"),
        (("startswith", "UNC_IIO_PWT_OCCUPANCY"),    "misc",   "Misc / Clocks"),
    ],
}


@dataclass
class SubComponent:
    id: str
    title: str
    events: list = field(default_factory=list)
    subcomponents: list = field(default_factory=list)  # list[SubComponent]

    @property
    def count(self) -> int:
        return len(self.events)

    @property
    def has_subs(self) -> bool:
        return bool(self.subcomponents)


@dataclass
class Cell:
    id: str
    title: str
    events: list = field(default_factory=list)  # list[EventDef]
    subcomponents: list = field(default_factory=list)  # list[SubComponent]

    @property
    def count(self) -> int:
        return len(self.events)

    @property
    def has_subs(self) -> bool:
        return bool(self.subcomponents)


@dataclass
class ArchMap:
    platform: str
    core_cells: list  # list[Cell] in display order
    uncore_cells: list
    total_core: int
    total_uncore: int

    @property
    def core_mapped(self) -> int:
        return sum(c.count for c in self.core_cells if c.id != "unclassified")

    @property
    def core_unmapped(self) -> int:
        for c in self.core_cells:
            if c.id == "unclassified":
                return c.count
        return 0

    @property
    def uncore_mapped(self) -> int:
        return sum(c.count for c in self.uncore_cells if c.id != "unclassified")

    @property
    def uncore_unmapped(self) -> int:
        for c in self.uncore_cells:
            if c.id == "unclassified":
                return c.count
        return 0


def _classify_core_event(event_name: str, rules: list) -> Optional[str]:
    """Return cell_id for a core event, or None if no rule matches."""
    # Try full first-token match (before the '.')
    head = event_name.split(".", 1)[0]
    for prefix, cell_id in rules:
        if head == prefix or event_name.startswith(prefix + "."):
            return cell_id
    return None


def _classify_uncore_event(unit: str) -> Optional[str]:
    entry = UNCORE_UNIT_TO_CELL.get(unit)
    return entry[0] if entry else None


def _event_suffix(event) -> str:
    """Return the part after the first '.', or '' if the event has no suffix."""
    _, _, tail = event.name.partition(".")
    return tail


def _match_sub_rule(matcher, event) -> bool:
    """Test a subcomponent matcher against an event.

    Matcher forms:
      "PREFIX"                     : name head == PREFIX or name starts with PREFIX + '.'
      ("unit", "CHA")              : event Unit field equals CHA
      ("contains", "TOR")          : substring appears in full event name
      ("startswith", "UNC_M_CAS")  : full event name starts with the given string
      ("contains_suffix", "DRD")   : suffix (after first '.') contains as whole token
      ("regex_suffix", pattern)    : suffix fully matches the regex
    """
    if isinstance(matcher, tuple):
        kind, arg = matcher
        if kind == "unit":
            return event.raw.get("Unit") == arg
        if kind == "contains":
            return arg in event.name
        if kind == "startswith":
            return event.name.startswith(arg)
        if kind == "contains_suffix":
            # Match if any suffix token equals or starts with arg. Lets a rule
            # for "LLCPREF" hit LLCPREFCODE / LLCPREFDATA / LLCPREFRFO tokens.
            return any(t == arg or t.startswith(arg) for t in _event_suffix(event).split("_"))
        if kind == "regex_suffix":
            import re as _re
            return _re.match(arg, _event_suffix(event)) is not None
        return False
    # string matcher: prefix on EventName
    head = event.name.split(".", 1)[0]
    return head == matcher or event.name.startswith(matcher + ".")


def _classify_subcomponent(event, sub_rules: list) -> Optional[tuple]:
    """Return (sub_id, sub_title) for the first matching rule, or None."""
    for matcher, sub_id, sub_title in sub_rules:
        if _match_sub_rule(matcher, event):
            return sub_id, sub_title
    return None


def _split_into_subs(events: list, rules: list) -> list:
    """Partition events into ordered SubComponents by first-matching rule.
    Unmatched events go into an 'other' bucket appended at the end."""
    sub_order = []
    sub_seen = {}
    for _, sub_id, sub_title in rules:
        if sub_id not in sub_seen:
            sub_seen[sub_id] = SubComponent(id=sub_id, title=sub_title)
            sub_order.append(sub_id)
    other = SubComponent(id="other", title="Other")
    for ev in events:
        match = _classify_subcomponent(ev, rules)
        if match is None:
            other.events.append(ev)
        else:
            sub_seen[match[0]].events.append(ev)
    subs = [sub_seen[sid] for sid in sub_order if sub_seen[sid].count > 0]
    if other.count > 0:
        subs.append(other)
    return subs


def _recurse_split(sub: SubComponent, path: tuple) -> None:
    """If DEEP_SUBCOMPONENTS has rules for this path, split further."""
    rules = DEEP_SUBCOMPONENTS.get(path)
    if not rules or sub.count == 0:
        return
    sub.subcomponents = _split_into_subs(sub.events, rules)
    for child in sub.subcomponents:
        _recurse_split(child, path + (child.id,))


def build_arch_map(catalog: PlatformCatalog) -> ArchMap:
    """Bucket every event in the catalog into an architectural cell."""
    platform = catalog.platform.shortname
    core_rules = CORE_RULES_BY_PLATFORM.get(platform)
    if core_rules is None:
        raise ValueError(
            f"No core classifier rules for platform '{platform}'. "
            f"Supported: {sorted(CORE_RULES_BY_PLATFORM)}"
        )

    # Preserve display order via lists of ids; look up title in CORE_CELL_TITLES.
    core_order = [
        "fe_fetch", "fe_decode", "bad_spec",
        "be_alloc", "be_execute",
        "mem_l1", "mem_l2", "mem_l3",
        "misc_pmu", "unclassified",
    ]
    core_cells = {cid: Cell(id=cid, title=CORE_CELL_TITLES[cid]) for cid in core_order}

    # Uncore cells built dynamically from Units actually seen, preserving a
    # canonical display order.
    uncore_order = [
        ("coherence_llc", "Coherence / LLC"),
        ("memory_ctrl",   "Memory Controller"),
        ("upi",           "UPI (socket interconnect)"),
        ("pcie_io",       "PCIe / IO"),
        ("cxl",           "CXL"),
        ("power_sys",     "Power / System"),
        ("unclassified",  "Unclassified"),
    ]
    uncore_cells = {cid: Cell(id=cid, title=title) for cid, title in uncore_order}

    total_core = 0
    total_uncore = 0

    for ev in catalog.events:
        if ev.deprecated:
            continue
        unit = ev.raw.get("Unit")
        if unit is None or unit == "":
            # Core event
            total_core += 1
            cell_id = _classify_core_event(ev.name, core_rules) or "unclassified"
            core_cells[cell_id].events.append(ev)
        else:
            total_uncore += 1
            cell_id = _classify_uncore_event(unit) or "unclassified"
            uncore_cells[cell_id].events.append(ev)

    # Sort events within each cell by name for stable output
    for c in core_cells.values():
        c.events.sort(key=lambda e: e.name)
    for c in uncore_cells.values():
        c.events.sort(key=lambda e: e.name)

    # Second pass: populate subcomponents per cell using platform-specific rules.
    # Then recursively split deeper for cells whose subcomponents have deep rules.
    sub_rules_by_cell = SUBCOMPONENTS_BY_PLATFORM.get(platform, {})
    for cells_dict in (core_cells, uncore_cells):
        for cell in cells_dict.values():
            rules = sub_rules_by_cell.get(cell.id)
            if not rules or cell.count == 0:
                continue
            cell.subcomponents = _split_into_subs(cell.events, rules)
            for sub in cell.subcomponents:
                _recurse_split(sub, (cell.id, sub.id))

    return ArchMap(
        platform=platform,
        core_cells=[core_cells[cid] for cid in core_order],
        uncore_cells=[uncore_cells[cid] for cid, _ in uncore_order],
        total_core=total_core,
        total_uncore=total_uncore,
    )
