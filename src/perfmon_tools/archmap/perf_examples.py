"""Generate copy-paste-ready perf snippets for an EventDef.

Core events use the symbolic name that `perf list` exposes. Uncore events use
the PMU-prefixed form: `uncore_<unit>/event=0xNN,umask=0xNN/`. For PEBS-capable
core events, the `:ppp` modifier promotes to precise. For sampling, the JSON's
SampleAfterValue seeds `-c` so the recommended per-event sample period is used.

Pure function — no filesystem or network access. Returns a dict of ready-to-run
command strings.
"""

from typing import Dict, Optional


# Which uncore Unit values map to which perf PMU prefix. Kernel exposes them
# as /sys/bus/event_source/devices/uncore_<name>/, one per instance.
UNCORE_PMU_PREFIX = {
    "CHA":    "uncore_cha",
    "CHACMS": "uncore_cha",  # sideband multiplexed on the same PMU
    "IMC":    "uncore_imc",
    "B2CMI":  "uncore_b2cmi",
    "MDF":    "uncore_mdf",
    "UPI LL": "uncore_upi",
    "B2UPI":  "uncore_b2upi",
    "IIO":    "uncore_iio",
    "IRP":    "uncore_irp",
    "B2HOT":  "uncore_b2hot",
    "CXLCM":  "uncore_cxlcm",
    "CXLDP":  "uncore_cxldp",
    "B2CXL":  "uncore_b2cxl",
    "PCU":    "uncore_pcu",
    "UBOX":   "uncore_ubox",
}


def _default_sample_period(sample_after_value: str) -> int:
    """Return an integer sample period, falling back to 2003 (prime) if unset."""
    if not sample_after_value:
        return 2003
    try:
        # SampleAfterValue can be decimal or hex ("0x1000")
        return int(sample_after_value, 0)
    except (TypeError, ValueError):
        return 2003


def _int_or_none(s: str) -> Optional[int]:
    if not s:
        return None
    try:
        return int(s, 0)
    except (TypeError, ValueError):
        return None


def build_examples(event) -> Dict[str, str]:
    """Return {'stat': str, 'record': str, 'raw': str, 'notes': list[str]}.

    'stat'   — counter-mode command (fast, whole-run aggregate)
    'record' — sampling-mode command that produces call stacks
    'raw'    — the same event but written with the raw event=/umask= encoding
    'notes'  — sentences worth showing under the code blocks
    """
    unit = (event.raw.get("Unit") or "").strip()
    is_uncore = bool(unit)
    is_pebs = str(event.precise) not in ("", "0", "None")
    sample_period = _default_sample_period(event.sample_after_value)

    notes = []

    if is_uncore:
        pmu = UNCORE_PMU_PREFIX.get(unit)
        if pmu is None:
            # Unknown uncore Unit → fall back to raw encoding only
            pmu = "uncore_?"
            notes.append(
                f"Unknown uncore PMU for Unit={unit!r}; "
                "check /sys/bus/event_source/devices/ for the right prefix."
            )

        # Uncore events don't do PEBS; -a is needed (system-wide) since uncore
        # PMUs aren't per-CPU.
        raw_spec = _uncore_raw_spec(event)
        symbolic = f"{pmu}/{raw_spec}/"
        stat = f"perf stat -a -e '{symbolic}' -- sleep 5"
        # Uncore events are counters, not samplers — perf record on uncore is
        # rarely useful; still emit but flag it.
        record = (
            f"perf record -a -e '{symbolic}' -- sleep 5   "
            "# uncore events count only; -a is required (not per-CPU)"
        )
        raw = f"perf stat -a -e '{pmu}/{raw_spec}/' -- sleep 5"
        notes.append(
            "Uncore PMUs are one per instance (e.g. uncore_cha_0, uncore_cha_1, …). "
            "Use `perf list uncore` to see which instances exist on your box."
        )
        return {"stat": stat, "record": record, "raw": raw, "notes": notes}

    # ----- Core event -----
    name = event.name
    precise_mod = ":ppp" if is_pebs else ""
    stat = f"perf stat -e {name} -- ./yourapp"
    if is_pebs:
        record = f"perf record -e {name}:ppp -g -c {sample_period} -- ./yourapp"
        notes.append(
            "This event supports PEBS (precise sampling). `:ppp` records the exact retiring IP "
            "and register state, giving you accurate blame with `perf report`."
        )
    else:
        record = f"perf record -e {name} -g -c {sample_period} -- ./yourapp"
        notes.append(
            "Not a precise (PEBS) event. Sampled IPs may skid ~10-30 instructions — "
            "profile with grain of salt or pair with a PEBS-capable sibling event."
        )

    # Raw encoding fallback (works even if perf doesn't know the symbolic name yet)
    code = _int_or_none(event.event_code)
    umask = _int_or_none(event.umask)
    if code is not None and umask is not None:
        terms = [f"event=0x{code:x}", f"umask=0x{umask:x}"]

        umask_ext = _int_or_none((event.raw or {}).get("UMaskExt"))
        if umask_ext:
            terms.append(f"umask=0x{(umask_ext << 8) | umask:x}")
            # Overwrite the plain umask with the widened one; drop the
            # narrow term to avoid duplication.
            terms[1] = terms.pop()

        msr_index = _int_or_none((event.raw or {}).get("MSRIndex"))
        msr_value = _int_or_none((event.raw or {}).get("MSRValue"))
        if msr_index and msr_value is not None:
            # perf exposes the secondary MSR under different alias names
            # depending on the PMU / event family. FRONTEND_RETIRED uses
            # `frontend=`; OFFCORE_RESPONSE uses `offcore_rsp=`. Emit both
            # candidates as a comment so the user can pick.
            alias = "frontend" if msr_index == 0x3F7 else "config1"
            terms.append(f"{alias}=0x{msr_value:x}")

        counter_mask = _int_or_none((event.raw or {}).get("CounterMask"))
        if counter_mask:
            terms.append(f"cmask=0x{counter_mask:x}")

        raw = f"perf stat -e 'cpu/{','.join(terms)}/' -- ./yourapp"
    else:
        raw = "# raw encoding unavailable (missing EventCode/UMask)"

    if _int_or_none((event.raw or {}).get("MSRIndex")):
        notes.append(
            "This event shares its EventCode+UMask with sibling events. The disambiguator "
            "is an MSR value (MSR 0x3F7 for FRONTEND_RETIRED, or an offcore-response MSR "
            "for OCR events). perf sets this automatically when you use the symbolic name; "
            "with a raw encoding you need the appropriate `frontend=` / `offcore_rsp=` / "
            "`config1=` term (see the raw fallback above)."
        )

    counter = (event.counter or "").strip()
    if counter and counter.lower() != "fixed":
        notes.append(
            f"Programmable counter — schedules on general-purpose counters {counter}. "
            "Combine at most ~4 events per group before perf starts multiplexing."
        )
    elif "fixed" in counter.lower():
        notes.append(
            "Fixed-function counter — always available, doesn't compete for general-purpose counters."
        )

    return {"stat": stat, "record": record, "raw": raw, "notes": notes}


def _uncore_raw_spec(event) -> str:
    """Compose the event=,umask=[,umask_ext=] spec for an uncore event."""
    code = _int_or_none(event.event_code)
    umask = _int_or_none(event.umask)
    parts = []
    if code is not None:
        parts.append(f"event=0x{code:x}")
    if umask is not None:
        parts.append(f"umask=0x{umask:x}")
    # UMaskExt appears on some uncore units (GNR/CWF)
    umask_ext = event.raw.get("UMaskExt")
    if umask_ext and umask_ext not in ("0x00", "0", "0x0"):
        parts.append(f"umask_ext={umask_ext}")
    return ",".join(parts) if parts else "event=0x00"
