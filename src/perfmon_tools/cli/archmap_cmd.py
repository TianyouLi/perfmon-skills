"""CLI: `perfmon-skills arch-map` — render a uarch event map."""

import argparse
import sys
from pathlib import Path


def add_parser(subparsers):
    parser = subparsers.add_parser(
        "arch-map",
        help="Render a per-uarch component diagram with event drill-down",
    )
    parser.add_argument(
        "--platform", "-p", required=True,
        help="Platform shortname (e.g. GNR, CWF)",
    )
    parser.add_argument(
        "--out", "-o", default="-",
        help="Output file path, or '-' for stdout (default: -)",
    )
    parser.add_argument(
        "--format", "-f", choices=["html", "text"], default="html",
        help="Output format (default: html)",
    )
    parser.set_defaults(func=run)


def _resolve_platform_by_shortname(shortname: str):
    from ..core.platform import list_platforms, resolve_platform, CpuInfo

    plats = list_platforms()
    match = next((p for p in plats if p.shortname == shortname), None)
    if match is None:
        raise SystemExit(
            f"Unknown platform '{shortname}'. Available: "
            f"{', '.join(p.shortname for p in plats)}"
        )
    # Fake a CpuInfo so we can reuse resolve_platform to load event files.
    fm = match.family_model
    model_hex = fm.split("-")[-1]
    try:
        model_int = int(model_hex.split("[")[0], 16)
    except ValueError:
        model_int = 0
    cpu = CpuInfo(
        vendor="GenuineIntel", family=6, model=model_int, stepping=0,
        model_name="", family_model=fm,
    )
    return resolve_platform(cpu)


def run(args):
    from ..core.catalog import PlatformCatalog
    from ..core.arch_map import build_arch_map
    from ..archmap.render import render_page

    pinfo = _resolve_platform_by_shortname(args.platform)
    catalog = PlatformCatalog(pinfo)
    arch_map = build_arch_map(catalog)

    if args.format == "text":
        _print_text(arch_map, pinfo.name)
        return

    html = render_page(arch_map, platform_display=f"{pinfo.name} ({pinfo.shortname})")
    if args.out == "-":
        sys.stdout.write(html)
    else:
        out_path = Path(args.out)
        out_path.write_text(html)
        print(f"Wrote {out_path} ({len(html):,} bytes)")


def _print_text(arch_map, display_name):
    total = arch_map.total_core + arch_map.total_uncore
    mapped = arch_map.core_mapped + arch_map.uncore_mapped
    unmapped = arch_map.core_unmapped + arch_map.uncore_unmapped
    print(f"{display_name} ({arch_map.platform}) — arch map")
    print(f"  total={total}  mapped={mapped}  unmapped={unmapped}")
    print(f"  core={arch_map.total_core}  uncore={arch_map.total_uncore}")
    print()
    print("Core cells:")
    for c in arch_map.core_cells:
        marker = "  " if c.id != "unclassified" else "! "
        print(f"  {marker}{c.count:5d}  {c.title}")
    print()
    print("Uncore cells:")
    for c in arch_map.uncore_cells:
        marker = "  " if c.id != "unclassified" else "! "
        print(f"  {marker}{c.count:5d}  {c.title}")
    if unmapped:
        print()
        print(f"Unmapped events ({unmapped}):")
        for c in list(arch_map.core_cells) + list(arch_map.uncore_cells):
            if c.id == "unclassified":
                for ev in c.events:
                    unit = ev.raw.get("Unit") or "cpu"
                    print(f"  [{unit}] {ev.name}")
