#!/usr/bin/env python3

import psutil
import argparse
import logging
import sys
import json
from datetime import datetime
from prettytable import PrettyTable
from typing import List, Tuple

# ------------------------
# Constants
# ------------------------

WARNING_THRESHOLD = 85  # Percentage for warning color
CRITICAL_THRESHOLD = 95  # Percentage for critical color

# ------------------------
# Logging Setup
# ------------------------

def setup_logging(verbose: bool = False) -> logging.Logger:
    """Configure logging for the application."""
    logger = logging.getLogger("DiskUsageMonitor")
    level = logging.DEBUG if verbose else logging.INFO
    logger.setLevel(level)

    handler = logging.StreamHandler(sys.stderr)
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger

# ------------------------
# Utility Functions
# ------------------------

def bytes_to_gb(bytes_val: int) -> float:
    """Convert bytes to gigabytes (1 decimal place)."""
    return round(bytes_val / (1024 ** 3), 1)

def get_color_for_usage(percent: float) -> str:
    """Return color code based on usage percentage."""
    logger = logging.getLogger("DiskUsageMonitor")
    if not isinstance(percent, (int, float)):
        logger.error(f"Invalid percent type: expected float, got {type(percent)}")
        return ""  # Fallback to no color

    if percent >= CRITICAL_THRESHOLD:
        return "\033[91m"  # Red
    elif percent >= WARNING_THRESHOLD:
        return "\033[93m"  # Yellow
    return ""  # No color

def collect_storage_info(include_all: bool = False, sort_key: str = "percent", physical_only: bool = False) -> List[Tuple]:
    """Collect info about mounted file systems."""
    logger = logging.getLogger("DiskUsageMonitor")
    logger.debug(f"Collecting storage info (include_all={include_all}, physical_only={physical_only})")
    partitions = psutil.disk_partitions(all=include_all)
    rows = []

    pseudo_fs_types = {'proc', 'sysfs', 'tmpfs', 'devtmpfs', 'devpts', 'cgroup', 'cgroup2', 'pstore', 'bpf', 'securityfs'}

    for part in partitions:
        logger.debug(f"Checking partition: {part.device} mounted on {part.mountpoint}")
        if not part.mountpoint:
            logger.debug(f"Skipping {part.device}: empty mountpoint")
            continue

        if physical_only and (part.fstype in pseudo_fs_types or part.device.startswith('/dev/loop')):
            logger.debug(f"Skipping {part.device}: pseudo-filesystem or loop device")
            continue

        try:
            usage = psutil.disk_usage(part.mountpoint)
            fs_type = part.fstype or "unknown"

            # Ensure percent is a float
            try:
                percent = float(usage.percent)
            except (TypeError, ValueError) as e:
                logger.error(f"Invalid percent value for {part.mountpoint}: {usage.percent}, skipping")
                continue

            # Correct tuple order to match table columns
            row = (
                part.device,             # Device
                part.mountpoint,         # Mount Point
                bytes_to_gb(usage.total),  # Total (GB)
                bytes_to_gb(usage.used),   # Used (GB)
                bytes_to_gb(usage.free),   # Free (GB)
                percent,                 # Use %
                fs_type                  # Filesystem
            )
            logger.debug(f"Adding row: {row}")
            rows.append(row)

        except PermissionError:
            logger.warning(f"Permission denied for mountpoint: {part.mountpoint}")
            continue
        except OSError as e:
            logger.error(f"OS error accessing {part.mountpoint}: {str(e)}", exc_info=logger.level == logging.DEBUG)
            continue
        except ValueError as e:
            logger.error(f"Value error for {part.mountpoint}: {str(e)}", exc_info=logger.level == logging.DEBUG)
            continue

    sort_indices = {
        "mount": 1,   # part.mountpoint
        "total": 2,   # total_gb
        "used": 3,    # used_gb
        "free": 4,    # free_gb
        "percent": 5  # usage_percent
    }
    return sorted(rows, key=lambda x: x[sort_indices[sort_key]], reverse=(sort_key != "mount"))

def print_storage_table(rows: List[Tuple], show_colors: bool = True) -> None:
    """Display disk usage in a formatted table."""
    logger = logging.getLogger("DiskUsageMonitor")
    logger.debug("Preparing output table")
    table = PrettyTable()
    table.field_names = [
        "Device",
        "Mount Point",
        "Total (GB)",
        "Used (GB)",
        "Free (GB)",
        "Use %",
        "Filesystem"
    ]
    table.align["Mount Point"] = "l"
    table.align["Device"] = "l"
    table.float_format = ".1"

    for row in rows:
        device, mount, total, used, free, percent, fs_type = row
        logger.debug(f"Processing row: device={device}, mount={mount}, percent={percent}, type={type(percent)}")
        
        # Ensure percent is a float for color calculation
        try:
            percent_float = float(percent)
        except (TypeError, ValueError):
            logger.error(f"Invalid percent value for {mount}: {percent}, using 0 for color calculation")
            percent_float = 0.0
        
        percent_str = f"{percent_float}%"
        
        if show_colors and sys.stdout.isatty():
            color = get_color_for_usage(percent_float)
            percent_str = f"{color}{percent_str}\033[0m" if color else percent_str
        
        table.add_row([
            device,
            mount,
            total,
            used,
            free,
            percent_str,
            fs_type
        ])

    print("\nCurrent Storage Status:")
    print(table)

def generate_json_output(rows: List[Tuple]) -> str:
    """Generate JSON output for machine consumption."""
    output = []
    for row in rows:
        device, mount, total, used, free, percent, fs_type = row
        output.append({
            "device": device,
            "mountpoint": mount,
            "total_gb": total,
            "used_gb": used,
            "free_gb": free,
            "usage_percent": percent,
            "filesystem": fs_type
        })
    return json.dumps(output, indent=2)

def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Display disk usage for mounted filesystems in a table or JSON format.",
        epilog="Example: %(prog)s -a --sort total --json | jq ."
    )
    parser.add_argument(
        "-a", "--all", action="store_true",
        help="Include all mountpoints, including system and pseudo-filesystems (e.g., /proc, /sys)"
    )
    parser.add_argument(
        "--physical", action="store_true",
        help="Include only physical filesystems, excluding pseudo-filesystems like /proc, /sys"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable verbose debug logging"
    )
    parser.add_argument(
        "--no-color", action="store_true",
        help="Disable colored output for usage percentage"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output in JSON format instead of a table"
    )
    parser.add_argument(
        "--warning-threshold", type=int, default=WARNING_THRESHOLD,
        help=f"Set warning threshold percentage for colored output (default: {WARNING_THRESHOLD}%)"
    )
    parser.add_argument(
        "--critical-threshold", type=int, default=CRITICAL_THRESHOLD,
        help=f"Set critical threshold percentage for colored output (default: {CRITICAL_THRESHOLD}%)"
    )
    parser.add_argument(
        "--sort", choices=["mount", "total", "used", "free", "percent"], default="percent",
        help="Sort table by field: mount (mountpoint), total (total size), used (used space), "
             "free (free space), percent (usage percentage, default)"
    )
    parser.add_argument(
        "--no-timestamp", action="store_true",
        help="Suppress the 'Generated at' timestamp in output"
    )
    args = parser.parse_args()

    if not (0 <= args.warning_threshold <= 100):
        parser.error(f"--warning-threshold must be between 0 and 100, got {args.warning_threshold}")
    if not (0 <= args.critical_threshold <= 100):
        parser.error(f"--critical-threshold must be between 0 and 100, got {args.critical_threshold}")
    if args.warning_threshold > args.critical_threshold:
        parser.error(f"--warning_threshold ({args.warning_threshold}) cannot be greater than --critical_threshold ({args.critical_threshold})")

    return args

def main() -> None:
    """Main entry point for the script."""
    args = parse_arguments()
    logger = setup_logging(args.verbose)

    global WARNING_THRESHOLD, CRITICAL_THRESHOLD
    WARNING_THRESHOLD = args.warning_threshold
    CRITICAL_THRESHOLD = args.critical_threshold

    logger.info("Disk usage monitor started")
    rows = collect_storage_info(include_all=args.all, sort_key=args.sort, physical_only=args.physical)

    if args.json:
        print(generate_json_output(rows))
    else:
        print_storage_table(rows, show_colors=not args.no_color)

    if not args.no_timestamp:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"\nGenerated at: {timestamp}")
    logger.info("Disk usage monitor completed")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nOperation cancelled by user", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        logging.getLogger("DiskUsageMonitor").critical(f"Unexpected error: {str(e)}", exc_info=True)
        sys.exit(1)
