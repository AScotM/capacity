#!/usr/bin/env python3

import psutil
import argparse
import logging
import sys
import json
from datetime import datetime
from typing import List, Tuple, Dict, Optional
from rich.console import Console
from rich.table import Table
from rich.json import JSON

# ------------------------
# Configuration
# ------------------------

console = Console()  # Define console at the top level

class Config:
    WARNING_THRESHOLD = 85
    CRITICAL_THRESHOLD = 95
    PSEUDO_FS_TYPES = {
        'proc', 'sysfs', 'tmpfs', 'devtmpfs', 'devpts', 'cgroup', 'cgroup2',
        'pstore', 'bpf', 'securityfs', 'mqueue', 'hugetlbfs', 'tracefs'
    }

# ------------------------
# Logging Setup
# ------------------------

def setup_logging(verbose: bool = False) -> logging.Logger:
    """Configure logging for the application."""
    logger = logging.getLogger("DiskUsageMonitor")
    if not logger.handlers:  # More robust handler check
        level = logging.DEBUG if verbose else logging.INFO
        logger.setLevel(level)

        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        ))
        logger.addHandler(handler)
    return logger

# ------------------------
# Utility Functions
# ------------------------

def bytes_to_human(bytes_val: int, unit: str = 'GB') -> float:
    """Convert bytes to specified unit (default: GB)."""
    units = {
        'KB': 1024,
        'MB': 1024**2,
        'GB': 1024**3,
        'TB': 1024**4
    }
    divisor = units.get(unit.upper(), 1024**3)  # Default to GB
    return round(bytes_val / divisor, 1)

def get_color_for_usage(percent: float) -> str:
    """Return rich color style based on usage percentage."""
    if percent >= Config.CRITICAL_THRESHOLD:
        return "bold red"
    elif percent >= Config.WARNING_THRESHOLD:
        return "yellow"
    return "white"

def collect_storage_info(include_all: bool = False, sort_key: str = "percent", 
                        physical_only: bool = False) -> List[Tuple]:
    """Collect info about mounted file systems."""
    logger = logging.getLogger("DiskUsageMonitor")
    logger.debug(f"Collecting storage info (include_all={include_all}, physical_only={physical_only})")
    partitions = psutil.disk_partitions(all=include_all)
    rows = []

    for part in partitions:
        if not part.mountpoint:
            continue

        if physical_only and (part.fstype in Config.PSEUDO_FS_TYPES or part.device.startswith('/dev/loop')):
            continue

        try:
            usage = psutil.disk_usage(part.mountpoint)
            fs_type = part.fstype or "unknown"
            percent = float(usage.percent)

            row = (
                part.device,
                part.mountpoint,
                bytes_to_human(usage.total),
                bytes_to_human(usage.used),
                bytes_to_human(usage.free),
                percent,
                fs_type
            )
            rows.append(row)

        except PermissionError:
            logger.warning(f"Permission denied for mountpoint: {part.mountpoint}")
            continue
        except (OSError, ValueError) as e:
            logger.error(f"Error accessing {part.mountpoint}: {e}", exc_info=logger.level == logging.DEBUG)
            continue

    sort_indices = {
        "mount": 1, "total": 2, "used": 3, "free": 4, "percent": 5
    }
    return sorted(rows, key=lambda x: x[sort_indices[sort_key]], reverse=(sort_key != "mount"))

def check_thresholds(rows: List[Tuple]) -> Tuple[bool, bool]:
    """Check if any partitions exceed warning or critical thresholds."""
    has_warning = any(row[5] >= Config.WARNING_THRESHOLD for row in rows)
    has_critical = any(row[5] >= Config.CRITICAL_THRESHOLD for row in rows)
    return has_warning, has_critical

# ------------------------
# Output Functions
# ------------------------

def print_storage_table(rows: List[Tuple]) -> None:
    """Display disk usage in a rich table."""
    table = Table(title="Current Storage Status", show_lines=True)
    table.add_column("Device", justify="left", style="cyan", no_wrap=True)
    table.add_column("Mount Point", justify="left", style="magenta")
    table.add_column("Total (GB)", justify="right")
    table.add_column("Used (GB)", justify="right")
    table.add_column("Free (GB)", justify="right")
    table.add_column("Use %", justify="right")
    table.add_column("Filesystem", justify="left")

    for device, mount, total, used, free, percent, fs_type in rows:
        color = get_color_for_usage(percent)
        table.add_row(
            device,
            mount,
            f"{total:.1f}",
            f"{used:.1f}",
            f"{free:.1f}",
            f"[{color}]{percent:.1f}%[/{color}]",
            fs_type
        )

    console.print(table)

def generate_json_output(rows: List[Tuple], rich_format: bool = True) -> None:
    """Print JSON output with optional rich formatting."""
    output = [
        {
            "device": device,
            "mountpoint": mount,
            "total_gb": total,
            "used_gb": used,
            "free_gb": free,
            "usage_percent": percent,
            "filesystem": fs_type,
            "status": (
                "CRITICAL" if percent >= Config.CRITICAL_THRESHOLD else
                "WARNING" if percent >= Config.WARNING_THRESHOLD else
                "OK"
            )
        }
        for device, mount, total, used, free, percent, fs_type in rows
    ]

    if rich_format:
        console.print(JSON.from_data(output))
    else:
        print(json.dumps(output, indent=2))

# ------------------------
# Argument Parsing
# ------------------------

def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Display disk usage for mounted filesystems.",
        epilog="Example: %(prog)s -a --sort total --json | jq ."
    )
    parser.add_argument("-a", "--all", action="store_true", help="Include all mountpoints")
    parser.add_argument("--physical", action="store_true", help="Only physical filesystems")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument("--json", action="store_true", help="Output in JSON format")
    parser.add_argument("--raw-json", action="store_true", help="Output in raw JSON (no rich formatting)")
    parser.add_argument("--warning-threshold", type=int, default=Config.WARNING_THRESHOLD, 
                       help="Warning threshold in percent")
    parser.add_argument("--critical-threshold", type=int, default=Config.CRITICAL_THRESHOLD, 
                       help="Critical threshold in percent")
    parser.add_argument("--sort", choices=["mount", "total", "used", "free", "percent"], 
                       default="percent", help="Sort table by field")
    parser.add_argument("--no-timestamp", action="store_true", help="Suppress timestamp in output")
    parser.add_argument("--unit", choices=["KB", "MB", "GB", "TB"], default="GB", 
                       help="Display unit for sizes")

    args = parser.parse_args()

    if not (0 <= args.warning_threshold <= 100):
        parser.error("--warning-threshold must be 0-100")
    if not (0 <= args.critical_threshold <= 100):
        parser.error("--critical-threshold must be 0-100")
    if args.warning_threshold > args.critical_threshold:
        parser.error("--warning-threshold cannot be greater than --critical-threshold")
    if args.json and args.raw_json:
        parser.error("Cannot use both --json and --raw-json")

    return args

# ------------------------
# Main
# ------------------------

def main():
    args = parse_arguments()
    logger = setup_logging(args.verbose)

    # Update config from arguments
    Config.WARNING_THRESHOLD = args.warning_threshold
    Config.CRITICAL_THRESHOLD = args.critical_threshold

    logger.info("Starting DiskUsageMonitor")
    rows = collect_storage_info(
        include_all=args.all,
        sort_key=args.sort,
        physical_only=args.physical
    )

    has_warning, has_critical = check_thresholds(rows)
    
    if args.raw_json:
        generate_json_output(rows, rich_format=False)
    elif args.json:
        generate_json_output(rows)
    else:
        print_storage_table(rows)

    if not args.no_timestamp:
        console.print(f"[dim]Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/dim]")

    logger.info("DiskUsageMonitor completed")

    # Exit with appropriate status code
    if has_critical:
        sys.exit(2)
    elif has_warning:
        sys.exit(1)
    sys.exit(0)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("[bold red]Operation cancelled by user[/bold red]", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        logging.getLogger("DiskUsageMonitor").critical(f"Unexpected error: {e}", exc_info=True)
        sys.exit(3)
