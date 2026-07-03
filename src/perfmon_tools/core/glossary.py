"""Human-friendly glossary and category notes for perfmon events.

Two dicts:
  - ACRONYMS: hardware acronyms → {expansion, gloss}. Detected inside a raw
    event description so we can annotate them for a reader who isn't fluent
    in Intel-speak.
  - CATEGORY_NOTES: keyed by classifier path tuple (matches the arch_map
    hierarchy) → engineer-oriented "what this means" summary. Inherited by
    any event whose sub-path starts with the key, longest-prefix wins.

Neither dict claims completeness. Missing entries are fine — the detail pane
still shows the raw Intel description as authoritative.
"""

from typing import Optional


ACRONYMS = {
    # Frontend
    "BPU":     ("Branch Prediction Unit",           "Predicts branch direction/target so fetch stays ahead of execution."),
    "BACLEARS":("Branch Address Calculator clears", "Frontend restarted because BAC predicted a different target than the BTB."),
    "ITLB":    ("Instruction TLB",                  "Cache of instruction-page virtual→physical translations."),
    "STLB":    ("Second-level TLB",                 "Unified 2nd-level TLB backing L1 iTLB/dTLB misses."),
    "DTLB":    ("Data TLB",                         "Cache of load/store page translations."),
    "IDQ":     ("Instruction Decode Queue",         "Queue between the decoders (or uop cache) and rename."),
    "DSB":     ("Decoded Stream Buffer",            "The uop cache — decoded uops kept for hot loops."),
    "MITE":    ("Micro-Instruction Translation Engine", "Legacy in-order path from x86 bytes to uops."),
    "MS":      ("Microcode Sequencer",              "Emits uop streams for complex instructions (e.g. gather, cpuid)."),
    "LSD":     ("Loop Stream Detector",             "Recirculates uops of a small hot loop, bypassing decode."),
    "MSROM":   ("Microcode ROM",                    "Where MS reads uop sequences from."),

    # Backend
    "RS":      ("Reservation Station",              "Scheduler queue that holds uops waiting for their operands."),
    "ROB":     ("Reorder Buffer",                   "In-flight uop tracker used for in-order retirement."),
    "PORT_0":  ("Execution Port 0",                 "One of the dispatch ports (P0/1/5/6 typically ALU/vector, P2/3 loads, P4 stores)."),
    "UOP":     ("Micro-operation",                  "Internal RISC-like op the pipeline actually executes."),
    "ASSISTS": ("Microcode assists",                "Slow-path uops (e.g. denormal FP, page-fault handling)."),

    # Memory
    "L1D":     ("Level-1 Data cache",               "First-level per-core data cache (~32-48KB, few-cycle latency)."),
    "L2":      ("Level-2 cache",                    "Per-core private L2 (~1-2MB, ~10-15 cycles)."),
    "L3":      ("Level-3 / LLC",                    "Last-level shared cache across cores (~30-100MB, ~40-60 cycles)."),
    "LLC":     ("Last-Level Cache",                 "Same as L3 on modern Intel: shared, sliced across the mesh."),
    "DRAM":    ("Main memory",                      "Off-chip DDR. ~100-300 cycles depending on locality/contention."),
    "PMM":     ("Persistent Memory (Optane)",       "Byte-addressable NVDIMM tier; deprecated but still in some event names."),
    "OCR":     ("Off-Core Response",                "Programmable matrix counting requests leaving the core by opcode × response type."),
    "OFFCORE": ("Off-core requests",                "Any load/store/prefetch that missed private caches and left the core."),

    # Coherence / uncore
    "CHA":     ("Caching / Home Agent",             "Mesh slice managing LLC coherence and directory for a range of addresses."),
    "CHACMS":  ("CHA Common Mesh Stop",             "Sideband for CHA mesh telemetry."),
    "TOR":     ("Table of Requests",                "Per-CHA queue of in-flight coherence requests. INSERTS = arrivals, OCCUPANCY = residency×cycles."),
    "SF":      ("Snoop Filter",                     "Tracks which cores may cache a line; avoids broadcast snoops."),
    "IMC":     ("Integrated Memory Controller",     "On-chip DDR controller (per-channel)."),
    "B2CMI":   ("Block-to-CMI bridge",              "Ingress from the mesh into the memory-controller side; also owns directory lookups."),
    "MDF":     ("Mesh Data Fabric",                 "Cross-die mesh interconnect (multi-tile chips like GNR)."),
    "UPI":     ("Ultra Path Interconnect",          "Inter-socket coherence link (successor to QPI)."),
    "B2UPI":   ("Block-to-UPI bridge",              "Mesh↔UPI adapter."),
    "UBOX":    ("System configuration box",         "Handles interrupts / MSR access from the uncore side."),
    "PCU":     ("Power Control Unit",               "Runs P/C-state firmware; owns turbo and thermal throttling."),
    "IIO":     ("Integrated I/O",                   "PCIe root complex counters."),
    "IRP":     ("I/O Coherency Point",              "Cache on the IIO side used by DMA traffic."),
    "B2HOT":   ("Block-to-HOT bridge",              "Ingress for hot-plug / management traffic."),
    "CXL":     ("Compute Express Link",             "Coherent PCIe-based accelerator/memory link."),
    "CXLCM":   ("CXL Cache/Mem channel",            "CXL type-2/3 device channel telemetry."),
    "CXLDP":   ("CXL Data Path",                    "Data-plane counters for a CXL device."),

    # Coherence opcodes (TOR / OCR)
    "DRD":     ("Demand Data Read",                 "Regular load that missed L1/L2 and reached the LLC/mesh."),
    "DRDPTE":  ("Demand data read (page-table entry)", "Data read from a page-walk (used by the STLB fill path)."),
    "CRD":     ("Code Read",                        "Instruction fetch that missed the L1I/L2."),
    "RFO":     ("Read-For-Ownership",               "Store to a shared line — pulls it exclusive so it can be modified."),
    "ITOM":    ("Invalidate-To-Modified",           "Store that already has the line but needs to invalidate other copies."),
    "SPECITOM":("Speculative ItoM",                 "ItoM issued speculatively before the store is known to retire."),
    "WCIL":    ("Write-Combining Invalidate-Line",  "Streaming store (movnt / write-combining) — invalidate any copy."),
    "WCILF":   ("Write-Combining Invalidate-Line-Full", "Full-line variant of WCIL (no partial byte-enables)."),
    "WBMTOI":  ("Writeback M→I",                    "Evict a modified line and drop it."),
    "WBMTOE":  ("Writeback M→E",                    "Evict a modified line but keep it exclusive elsewhere."),
    "WBEFTOI": ("Writeback E/F→I",                  "Evict an exclusive/forward line and drop it."),
    "WBEFTOE": ("Writeback E/F→E",                  "Evict an exclusive/forward line, keep exclusive."),
    "WBSTOI":  ("Writeback S→I",                    "Evict a shared line."),
    "LLCPREF": ("LLC-targeted prefetch",            "HW/SW prefetch aimed at the L3."),
    "CLFLUSH": ("Cache Line Flush",                 "The x86 CLFLUSH/CLFLUSHOPT instruction — invalidates the line everywhere."),
    "UCRDF":   ("Uncacheable Read (Full)",          "Read to uncacheable / write-combining MMIO."),

    # Memory controller
    "CAS":     ("Column Address Strobe",            "One DDR read or write burst on a subchannel."),
    "RPQ":     ("Read Pending Queue",               "Per-channel queue of not-yet-issued reads."),
    "WPQ":     ("Write Pending Queue",              "Per-channel queue of not-yet-issued writes."),
    "RDB":     ("Read Data Buffer",                 "Holds returned DDR data on its way back to the mesh."),
    "PCH":     ("Physical Channel",                 "DDR sub-channel (each channel splits into PCH0/PCH1 on GNR)."),
    "PDC":     ("Power Down Control",               "Handles rank/bank power-down state."),
    "PPD":     ("Precharge Power-Down",             "DRAM low-power state (banks precharged)."),
    "MR4":     ("Mode Register 4",                  "DDR5 temp-tracking MR — drives 2x refresh."),

    # Misc
    "PEBS":    ("Precise Event-Based Sampling",     "Records the exact retiring IP + regs in a hardware record."),
    "PDIST":   ("PEBS Distributed",                 "PEBS format that also records LBRs / call stack (GNR)."),
    "TMA":     ("Top-down Microarchitecture Analysis", "Intel's structured methodology — slot classification into Retiring / Bad-Spec / FE / BE."),
    "TSX":     ("Transactional Sync Extensions",    "Hardware transactional memory (RTM/HLE) — mostly disabled on current parts."),
    "RTM":     ("Restricted Transactional Memory",  "TSX's explicit variant (XBEGIN/XEND)."),
    "SMC":     ("Self-Modifying Code",              "Code page written to while executing — triggers pipeline clears."),
    "LFENCE":  ("Load fence",                       "Serialising instruction — waits for older loads / speculation."),
    "VEX":     ("Vector Extensions prefix",         "AVX/AVX2 instruction encoding."),
    "IOMMU":   ("I/O Memory Management Unit",       "Translates DMA addresses (VT-d)."),
    "COMP_BUF":("Completion Buffer",                "IIO buffer tracking outstanding non-posted PCIe transactions."),
    "PWT":     ("Posted Write Tracker",             "IIO structure tracking in-flight posted writes."),
}


# ---------------------------------------------------------------------------
# Engineer-oriented "what this means" notes, keyed by the arch_map path tuple.
# The renderer picks the longest matching prefix, so a leaf inherits from its
# nearest ancestor if a specific entry doesn't exist.
# ---------------------------------------------------------------------------

CATEGORY_NOTES = {
    # --- Frontend ---
    ("fe_fetch",): (
        "Frontend Fetch/Predict — measures how well the CPU is keeping the pipeline fed with instructions. "
        "High branch-miss / iTLB-miss / iCache-miss values usually manifest as TMA Frontend-Bound."
    ),
    ("fe_fetch", "bpu"): (
        "Branch predictor telemetry. A high MISP-RETIRED rate relative to BR_INST_RETIRED means the "
        "predictor is losing — usually indirect branches, data-dependent conditions, or short-lived call sites. "
        "Try profile-guided-optimisation, __builtin_expect, or converting indirect calls to direct."
    ),
    ("fe_fetch", "itlb"): (
        "Instruction-side TLB pressure. Common causes: huge working sets of code across many .so files, "
        "randomly-laid-out JITed code, or tiny 4K pages for a hot hot-loop. Consider hugepages for .text "
        "or grouping hot functions."
    ),
    ("fe_fetch", "icache"): (
        "L1 instruction cache activity. High miss rates point at working-set > L1I (~32KB) or "
        "instruction footprint spread across many callees. Look at code layout / LTO / PGO."
    ),
    ("fe_fetch", "fe_sample"): (
        "PEBS-precise frontend stall samples. Use these to pinpoint the *exact instruction* where "
        "the frontend stalled — much more useful than raw counters for finding root cause."
    ),

    ("fe_decode",): (
        "Frontend Decode/Deliver — the stage between fetch and rename. High values here usually mean "
        "the uop cache (DSB) missed and the pipeline fell back to slower legacy decode (MITE)."
    ),
    ("fe_decode", "idq"): (
        "IDQ = the delivery queue feeding rename. High IDQ_BUBBLES means rename is starved despite fetch "
        "delivering — often paired with high frontend-bound in TMA."
    ),
    ("fe_decode", "lsd"): (
        "Loop Stream Detector — small loops recirculate here, bypassing decode. If a hot loop "
        "*isn't* running from LSD it may be too large (>64-ish uops) or contain unsupported instructions."
    ),
    ("fe_decode", "dsb"): (
        "Uop-cache health. DSB2MITE_SWITCHES means the pipeline dropped out of the uop cache — costly. "
        "Reduce loop body size, avoid rarely-used instruction forms, ensure 32-byte alignment on hot targets."
    ),
    ("fe_decode", "mite"): (
        "Legacy decode path — slower and lower-bandwidth than DSB. Elevated traffic here is a hint "
        "your hot code isn't fitting in the uop cache."
    ),

    ("bad_spec",): (
        "Speculation-recovery cost. High values = many pipeline flushes from branch mispredicts, "
        "machine clears (SMC, memory ordering), or TSX aborts."
    ),

    ("be_alloc",): (
        "Backend allocation / retirement. TMA slot accounting lives here. Elevated stalls point at "
        "downstream resource pressure — scheduler, load buffer, store buffer, physical register file."
    ),
    ("be_alloc", "slots"): (
        "TMA slot buckets — Intel's methodology for classifying every pipeline slot into "
        "Retiring / Bad-Spec / Frontend-Bound / Backend-Bound. These are the L1 TMA nodes."
    ),
    ("be_alloc", "rename"): (
        "Rename / allocation stalls. If RESOURCE_STALLS.RS or .SB is high, the scheduler or "
        "store-buffer is full — usually a downstream execution-latency problem, not a rename problem."
    ),
    ("be_alloc", "retire"): (
        "Retirement telemetry. INST_RETIRED and UOPS_RETIRED are your bedrock IPC/UPC counters."
    ),

    ("be_execute",): (
        "Backend execution — the ALUs and their scheduling. High core-bound in TMA usually shows "
        "up as pressure on a specific port or execution unit."
    ),
    ("be_execute", "ports"): (
        "Per-port dispatch counters. Uneven traffic across ports (e.g. everything on P0/1/5/6) "
        "indicates instruction-mix imbalance; try to spread int/vector work if you can."
    ),
    ("be_execute", "stalls"): (
        "Execution stall counters. CYCLE_ACTIVITY.STALLS_* tell you which pipeline stage the "
        "critical path is waiting on. Correlate with EXE_ACTIVITY.{1,2,3,4}_PORTS_UTIL to see how many "
        "ports are firing per cycle."
    ),
    ("be_execute", "int_alu"): (
        "Integer ALU work. Distinguishes scalar-int vs vector-int (INT_VEC_RETIRED)."
    ),
    ("be_execute", "fp_vec"): (
        "FP / vector work classified by width (128/256/512) and precision (SP/DP). Use "
        "FP_ARITH_INST_RETIRED.*_PACKED events to see if your kernel actually vectorised."
    ),

    ("mem_l1",): (
        "L1 / LSU / TLB — the load-store side of the core. Where memory bandwidth *and* latency "
        "problems both first appear as stalls."
    ),
    ("mem_l1", "l1d"): (
        "L1 data-cache telemetry. L1D_PEND_MISS.PENDING / cycles is the effective outstanding-miss "
        "count and is the go-to indicator for L1D bandwidth saturation."
    ),
    ("mem_l1", "dtlb"): (
        "Data TLB pressure. STLB_HIT costs ~7 cycles; STLB_MISS triggers a page walk (30-100+ cycles). "
        "Common culprits: pointer-chasing across huge heaps, sparse hash tables. Try hugepages."
    ),
    ("mem_l1", "lsu"): (
        "Load-store unit events including memory ordering (LD_BLOCKS.STORE_FORWARD is a classic sign "
        "of a partial-overlap load stalling on an older store) and atomic-op cost (LOCK_CYCLES)."
    ),

    ("mem_l2",): (
        "L2 traffic and hit/miss breakdown. Elevated MISS-side counters usually correlate with "
        "TMA L2-bound."
    ),

    ("mem_l3",): (
        "L3 / off-core requests — where NUMA, DRAM, and inter-core sharing show up."
    ),
    ("mem_l3", "ocr"): (
        "Off-Core Response is a programmable matrix: rows are request types (DEMAND_DATA_RD, RFO, "
        "PREFETCH_*), columns are where the response came from (L3_HIT, L3_MISS_LOCAL_DRAM, "
        "L3_MISS_REMOTE_HITM, SNOOP_HITM, …). Very powerful for NUMA / false-sharing diagnosis."
    ),
    ("mem_l3", "l3_hit"): (
        "L3 hits — retired-load-based. Elevated with high MEM_LOAD_RETIRED.L3_HIT means the working "
        "set fits in LLC but not in L2 — bandwidth-limited by L3."
    ),
    ("mem_l3", "l3_miss"): (
        "L3 misses — the request went to DRAM (or CXL). LOCAL vs REMOTE variants tell you NUMA locality; "
        "MEM_LOAD_L3_MISS_RETIRED.REMOTE_HITM is the smoking gun for cross-socket cache-line ping-pong."
    ),
    ("mem_l3", "offcore"): (
        "OFFCORE_REQUESTS_OUTSTANDING.* / clocks approximates memory-level parallelism. "
        "If it saturates at the fill-buffer count (10-16), you're bandwidth-limited."
    ),
    ("mem_l3", "prefetch"): (
        "Software-issued prefetches (PREFETCHT0/T1/T2/NTA). Track whether your prefetches are "
        "actually landing early enough to help — if the retired load still misses L3, they're not."
    ),

    # --- Coherence / LLC ---
    ("coherence_llc",): (
        "Uncore LLC / coherence — mesh-wide counters. These are per-CHA-slice; multiply by slice count "
        "for socket totals. Great for observing shared-line contention and NUMA."
    ),
    ("coherence_llc", "tor"): (
        "TOR = the CHA's outstanding-request table. INSERTS.* = arrival rate of coherence requests; "
        "OCCUPANCY.* = residency (integrate over time = queue depth). "
        "OCCUPANCY / INSERTS ≈ average request latency in mesh cycles."
    ),
    ("coherence_llc", "tor", "ia"): (
        "IA_* = requests from CPU cores. This is the primary telemetry for LLC access patterns and "
        "DRAM traffic caused by core work."
    ),
    ("coherence_llc", "tor", "ia", "drd"): (
        "Demand data reads from cores. Compare IA_MISS_DRD to IA_HIT_DRD to see LLC hit rate for loads. "
        "A big gap between OCCUPANCY.IA_MISS_DRD and INSERTS.IA_MISS_DRD indicates high DRAM latency."
    ),
    ("coherence_llc", "tor", "ia", "own"): (
        "Store-to-shared-line traffic. High IA_MISS_RFO/ITOM typically indicates false sharing or "
        "cross-core producer-consumer patterns — look for hot cache lines with contention."
    ),
    ("coherence_llc", "tor", "ia", "crd"): (
        "Instruction-fetch misses. High values ⇒ code working-set exceeds L1I+L2 for at least one core."
    ),
    ("coherence_llc", "tor", "ia", "pref"): (
        "LLC-targeted prefetches. Compare against demand DRD to gauge prefetch effectiveness — "
        "if demand miss count doesn't drop when prefetches rise, they're not helping."
    ),
    ("coherence_llc", "tor", "ia", "wb"): (
        "Writebacks and streaming stores. High WCIL/WCILF from cores usually means intentional "
        "non-temporal stores (movnt); high WB*TOI/E is normal LLC/L2 eviction traffic."
    ),
    ("coherence_llc", "tor", "io"): (
        "Device-generated coherence traffic. High values ⇒ heavy DMA / PCIe device activity. "
        "Compare with IIO counters for the causing device."
    ),
    ("coherence_llc", "tor", "cxl"): (
        "CXL-accessed traffic. Only lights up if you have CXL memory / accelerators plugged in."
    ),
    ("coherence_llc", "sf"): (
        "Snoop filter activity. SF evictions ⇒ SF is undersized for the sharing pattern → results "
        "in extra broadcast snoops. Rare, but shows up in shared read-mostly datasets."
    ),
    ("coherence_llc", "requests"): (
        "Aggregate CHA request-type breakdown (reads vs writes vs InvItoE)."
    ),
    ("coherence_llc", "remote"): (
        "Remote-socket snoop / access telemetry. Non-zero remote traffic → NUMA locality issues."
    ),

    # --- Memory controller ---
    ("memory_ctrl",): (
        "DDR side of the SoC. Split into IMC (direct DRAM), B2CMI (mesh↔IMC bridge, holds the directory), "
        "MDF (mesh fabric)."
    ),
    ("memory_ctrl", "imc"): (
        "Integrated Memory Controller. CAS_COUNT is your bandwidth proxy; queues (RPQ/WPQ) show "
        "back-pressure; throttling events indicate the memory subsystem is thermally / electrically capped."
    ),
    ("memory_ctrl", "imc", "cas"): (
        "One CAS_COUNT = one 64B burst. Total bytes/sec ≈ CAS_COUNT × 64. Split by SubChannel × RD/WR."
    ),
    ("memory_ctrl", "imc", "queues"): (
        "RPQ_INSERTS ≈ demand-read arrival rate, WPQ_INSERTS ≈ writeback arrival rate. "
        "Occupancy events give queue depth; if they hit their max, the memory controller is the bottleneck."
    ),
    ("memory_ctrl", "imc", "pwr"): (
        "Powerdown / refresh telemetry. If POWERDOWN_CYCLES is high, DRAM is spending a lot of time idle — "
        "either the workload is memory-quiet or there's a scheduling issue."
    ),
    ("memory_ctrl", "imc", "thr"): (
        "Memory-throttle cycles. If non-zero, the memory subsystem is running at reduced bandwidth "
        "for thermal or power reasons. Check DIMM cooling and RAPL power caps."
    ),
    ("memory_ctrl", "b2cmi"): (
        "B2CMI sits between the mesh and the IMC. Owns the memory-side directory that eliminates "
        "cross-socket snoops on remote-owned lines."
    ),
    ("memory_ctrl", "b2cmi", "dir"): (
        "Directory lookups/updates. DIRECTORY_HIT means the directory told us where the line is "
        "and avoided a broadcast snoop — good. HIGH miss/update rates → lots of ownership changes."
    ),
    ("memory_ctrl", "b2cmi", "d2core"): (
        "Direct2Core — data returned from DRAM steered straight to the requesting core, "
        "bypassing LLC insertion. Reduces LLC pollution for streaming reads."
    ),
    ("memory_ctrl", "b2cmi", "d2upi"): (
        "Direct2UPI — DRAM data streamed straight over UPI to the remote-socket requester. "
        "Signals inter-socket streaming traffic."
    ),

    # --- PCIe / IO ---
    ("pcie_io",): (
        "PCIe root-complex telemetry. Great for correlating device-DMA with core stalls."
    ),
    ("pcie_io", "iio"): (
        "Integrated I/O. DATA_REQ counts DMA bytes; TXN_REQ counts non-posted PCIe transactions "
        "(reads, config writes, MSI). NUM_OUTSTANDING approximates in-flight PCIe latency-bandwidth product."
    ),
    ("pcie_io", "iio", "data"): (
        "DMA payload traffic. DATA_REQ_OF_CPU = MMIO reads/writes the CPU issued toward devices; "
        "DATA_REQ_BY_CPU = the reverse — device DMA landing in coherent memory."
    ),
    ("pcie_io", "iio", "txn"): (
        "Non-posted PCIe transactions. Elevated NUM_OUTSTANDING relative to DATA_REQ suggests "
        "high PCIe round-trip latency (small transfers, or long device response times)."
    ),
    ("pcie_io", "iio", "iommu"): (
        "IOMMU (VT-d) translation activity. High miss rate ⇒ many device-side page-walks → try "
        "hugepages for DMA buffers or scatter-gather-list reuse."
    ),

    # --- UPI ---
    ("upi",): (
        "Inter-socket link. UPI bandwidth is the bottleneck for cross-socket workloads. "
        "TXL_INSERTS × 64 ≈ bytes/s per direction."
    ),
}


# ---------------------------------------------------------------------------
# Pseudo-events referenced by metric formulas but not present in the perfmon
# events JSON. These are typically kernel-exposed synthetic counters (like
# PERF_METRICS.*), free-running energy MSRs, or the timestamp counter. Each
# entry is a dict:
#   brief   — one-line summary
#   detail  — a paragraph of context
#   source  — how the kernel exposes it / perf command to read it
#   formula — conceptual definition or reconstruction recipe (may be None
#             when the concept is a direct hardware reading)
# ---------------------------------------------------------------------------

PSEUDO_EVENTS = {
    "PERF_METRICS.FRONTEND_BOUND": {
        "brief": "Fraction of pipeline slots stalled on the frontend.",
        "detail": (
            "One of the four TMA L1 buckets. Reads a dedicated fixed-function "
            "counter that Intel added in Icelake so software doesn't have to "
            "compute the top-level TMA breakdown from raw events."
        ),
        "source": (
            "perf reports as `topdown-fe-bound`. Program together with `slots` "
            "and the other three PERF_METRICS.* buckets."
        ),
        "formula": (
            "PERF_METRICS.FRONTEND_BOUND / TOPDOWN.SLOTS\n"
            "\n"
            "Conceptually, each pipeline slot per cycle is classified into one of "
            "four buckets by the retirement microarchitecture:\n"
            "  slot is stalled because the frontend didn't deliver a uop\n"
            "The four PERF_METRICS.* buckets sum to 1.0 exactly (modulo counter\n"
            "overflow and multiplexing).\n"
            "\n"
            "Pre-Icelake recipe (no PERF_METRICS hardware):\n"
            "  IDQ_UOPS_NOT_DELIVERED.CORE / (4 * CPU_CLK_UNHALTED.THREAD)"
        ),
    },
    "PERF_METRICS.BACKEND_BOUND": {
        "brief": "Fraction of pipeline slots stalled on the backend.",
        "detail": (
            "TMA L1 bucket. High when execution units, memory, or scheduling "
            "resources are the bottleneck. Split further into Memory_Bound and "
            "Core_Bound at L2 (which use different formulas, not PERF_METRICS.*)."
        ),
        "source": "perf reports as `topdown-be-bound`.",
        "formula": (
            "PERF_METRICS.BACKEND_BOUND / TOPDOWN.SLOTS\n"
            "\n"
            "Pre-Icelake recipe:\n"
            "  1 - (Frontend_Bound + Bad_Speculation + Retiring)\n"
            "or equivalently:\n"
            "  CYCLE_ACTIVITY.STALLS_TOTAL / CPU_CLK_UNHALTED.THREAD "
            "(with adjustments for retiring uops)"
        ),
    },
    "PERF_METRICS.BAD_SPECULATION": {
        "brief": "Fraction of pipeline slots wasted on mis-speculated work.",
        "detail": (
            "TMA L1 bucket. Includes branch-mispredict recovery and machine "
            "clears (SMC, memory ordering, TSX aborts)."
        ),
        "source": "perf reports as `topdown-bad-spec`.",
        "formula": (
            "PERF_METRICS.BAD_SPECULATION / TOPDOWN.SLOTS\n"
            "\n"
            "Pre-Icelake recipe:\n"
            "  ( UOPS_ISSUED.ANY - UOPS_RETIRED.RETIRE_SLOTS\n"
            "    + N * INT_MISC.RECOVERY_CYCLES )\n"
            "  / (4 * CPU_CLK_UNHALTED.THREAD)"
        ),
    },
    "PERF_METRICS.RETIRING": {
        "brief": "Fraction of pipeline slots that successfully retired.",
        "detail": (
            "TMA L1 bucket. Higher is generally better (more useful work per "
            "cycle) — but high values combined with low IPC can indicate "
            "microcode-heavy code (e.g. gathers, denormal FP)."
        ),
        "source": "perf reports as `topdown-retiring`.",
        "formula": (
            "PERF_METRICS.RETIRING / TOPDOWN.SLOTS\n"
            "\n"
            "Pre-Icelake recipe:\n"
            "  UOPS_RETIRED.RETIRE_SLOTS / (4 * CPU_CLK_UNHALTED.THREAD)"
        ),
    },
    "PERF_METRICS.BRANCH_MISPREDICTS": {
        "brief": "L2 refinement of Bad_Speculation — fraction from branch mispredicts.",
        "detail": (
            "Only the mispredict portion; complement is Machine_Clears. Available "
            "on newer parts as an L2 PERF_METRICS extension."
        ),
        "source": "perf reports as `topdown-br-mispredict`.",
        "formula": (
            "PERF_METRICS.BRANCH_MISPREDICTS / TOPDOWN.SLOTS\n"
            "\n"
            "Approximately:\n"
            "  BR_MISP_RETIRED.ALL_BRANCHES / (BR_MISP_RETIRED.ALL_BRANCHES\n"
            "                                  + MACHINE_CLEARS.COUNT)\n"
            "  * PERF_METRICS.BAD_SPECULATION"
        ),
    },
    "PERF_METRICS.FETCH_LATENCY": {
        "brief": "L2 refinement of Frontend_Bound — fraction spent waiting for fetch.",
        "detail": (
            "Distinguishes latency-bound frontend stalls (iCache/iTLB misses, "
            "branch mispredict recovery) from bandwidth-bound frontend stalls "
            "(decode throughput)."
        ),
        "source": "perf reports as `topdown-fetch-lat`.",
        "formula": (
            "PERF_METRICS.FETCH_LATENCY / TOPDOWN.SLOTS\n"
            "\n"
            "Pre-Icelake recipe:\n"
            "  IDQ_UOPS_NOT_DELIVERED.CYCLES_0_UOPS_DELIV.CORE\n"
            "  / CPU_CLK_UNHALTED.THREAD"
        ),
    },
    "PERF_METRICS.HEAVY_OPERATIONS": {
        "brief": "L2 refinement of Retiring — fraction from complex instructions.",
        "detail": (
            "Includes microcode-sequenced uops (gathers, string ops, page-walks, "
            "denormal FP). Sibling Light_Operations = simple retiring uops."
        ),
        "source": "perf reports as `topdown-heavy-ops`.",
        "formula": (
            "PERF_METRICS.HEAVY_OPERATIONS / TOPDOWN.SLOTS\n"
            "\n"
            "Approximately (varies by uarch):\n"
            "  UOPS_RETIRED.MS / (4 * CPU_CLK_UNHALTED.THREAD)"
        ),
    },
    "PERF_METRICS.MEMORY_BOUND": {
        "brief": "L2 refinement of Backend_Bound — fraction stalled on memory.",
        "detail": (
            "Available on some newer parts. Sibling Core_Bound (=BE-MEM) "
            "captures execution-resource stalls."
        ),
        "source": "perf reports as `topdown-mem-bound`.",
        "formula": (
            "PERF_METRICS.MEMORY_BOUND / TOPDOWN.SLOTS\n"
            "\n"
            "Pre-Icelake recipe:\n"
            "  (CYCLE_ACTIVITY.STALLS_MEM_ANY + RESOURCE_STALLS.SB)\n"
            "  / CPU_CLK_UNHALTED.THREAD"
        ),
    },
    "FREERUN_PKG_ENERGY_STATUS": {
        "brief": "Package-wide energy consumed since boot, in RAPL units.",
        "detail": (
            "Free-running MSR read via the RAPL PMU. Delta over a measurement "
            "window gives package power. Used by metrics like Info_PKG_Energy or "
            "PowerLicense computations."
        ),
        "source": "Use `perf stat -e power/energy-pkg/` (or `-e msr/package_energy/`).",
        "formula": (
            "Direct MSR read: IA32_PKG_ENERGY_STATUS (MSR 0x611).\n"
            "\n"
            "Value is monotonically increasing; energy consumed over an\n"
            "interval = (end - start) * energy_units, where energy_units\n"
            "comes from MSR_RAPL_POWER_UNIT (0x606). Typical unit is 2^-14 J\n"
            "on server SKUs.\n"
            "\n"
            "Power in watts = delta_energy_joules / interval_seconds."
        ),
    },
    "FREERUN_DRAM_ENERGY_STATUS": {
        "brief": "DRAM energy consumed since boot, in RAPL units.",
        "detail": (
            "Same mechanism as PKG_ENERGY but for the DIMMs. Not always exposed "
            "— depends on RAPL domain support on the SKU."
        ),
        "source": "Use `perf stat -e power/energy-ram/` when present.",
        "formula": (
            "Direct MSR read: MSR_DRAM_ENERGY_STATUS (0x619).\n"
            "\n"
            "Same delta-and-scale calculation as PKG_ENERGY."
        ),
    },
    "TSC": {
        "brief": "Time Stamp Counter — wall-clock reference in CPU cycles.",
        "detail": (
            "Read via `rdtsc`. On modern Intel it ticks at the platform "
            "reference frequency, independent of DVFS. Used as a denominator "
            "when converting event counts to per-time-unit rates."
        ),
        "source": (
            "perf exposes as `cycles` with `--user-regs` on some kernels; "
            "otherwise `cpu/event=0x3c,umask=0x0/` reads CPU_CLK_UNHALTED.REF_TSC."
        ),
        "formula": (
            "Direct instruction: RDTSC (or RDTSCP).\n"
            "\n"
            "Ticks at the invariant platform reference frequency (usually the\n"
            "nominal / base clock — check CPUID leaf 0x15 for TSC frequency).\n"
            "Does NOT scale with turbo / P-state. To convert cycles to seconds:\n"
            "  seconds = tsc_delta / tsc_freq_hz\n"
        ),
    },
    "TOPDOWN.SLOTS": {
        "brief": "Total pipeline slots issued (the TMA denominator).",
        "detail": (
            "One fixed-function counter that ticks every issue slot per cycle "
            "× slot-width. All TMA L1 fractions are counts divided by this. "
            "Exposed as `slots` in perf."
        ),
        "source": "perf: `-e slots` (must appear in the same group as the PERF_METRICS.* events).",
        "formula": (
            "TOPDOWN.SLOTS = CPU_CLK_UNHALTED.THREAD * pipeline_width\n"
            "\n"
            "Pipeline width is uarch-specific:\n"
            "  Icelake / Sapphire Rapids / Granite Rapids: 6 slots/cycle\n"
            "  Skylake-X / earlier Xeon:                    4 slots/cycle\n"
            "\n"
            "This is why raw slot counts scale with core count and elapsed\n"
            "cycles — always divide by SLOTS when comparing across runs."
        ),
    },
}


def get_pseudo_event(name: str):
    """Return the pseudo-event dict for `name`, or None."""
    return PSEUDO_EVENTS.get(name)


def find_acronyms(text: str) -> list:
    """Return list of (acronym, expansion, gloss) found in the description text.

    Only surfaces acronyms that appear as whole tokens (not substrings) so
    'CAS' doesn't match 'because'. Case-insensitive match against the keys.
    """
    if not text:
        return []
    import re as _re
    # Tokens: alphanumeric runs, allowing embedded underscores
    tokens = set()
    for tok in _re.findall(r"[A-Za-z][A-Za-z0-9_]*", text):
        tokens.add(tok.upper())
    hits = []
    seen = set()
    for tok in tokens:
        entry = ACRONYMS.get(tok)
        if entry and tok not in seen:
            seen.add(tok)
            hits.append((tok, entry[0], entry[1]))
    hits.sort()
    return hits


def note_for_path(path: tuple) -> Optional[str]:
    """Return the longest-prefix-matching note for a path tuple, or None."""
    for i in range(len(path), 0, -1):
        entry = CATEGORY_NOTES.get(tuple(path[:i]))
        if entry:
            return entry
    return None
