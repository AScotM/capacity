#!/usr/bin/env python3

import psutil
import argparse
import logging
import sys
from datetime import datetime
from prettytable import PrettyTable

# ------------------------
# Logging Setup
# ------------------------
logger = logging.getLogger("DiskUsageMonitor")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stderr)
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)

# ------------------------
# Utility Functions
# ------------------------

def bytes_to_gb(bytes_val):
    """Convert bytes to gigabytes (1 decimal)"""
    return round(bytes_val / (1024 ** 3), 1)

def collect_storage_info(include_all=False):
    """Collect info about mounted file systems"""
    logger.debug(f"Collecting storage info (include_all={include_all})")
    partitions = psutil.disk_partitions(all=include_all)
    rows = []

    for part in partitions:
        logger.debug(f"Checking partition: {part.device} mounted on {part.mountpoint}")

        if not part.mountpoint:
            logger.debug(f"Skipping {part.device}: empty mountpoint")
            continue

        try:
            usage = psutil.disk_usage(part.mountpoint)
            fs_type = part.fstype or "unknown"

            row = [
                part.mountpoint,
                bytes_to_gb(usage.total),
                bytes_to_gb(usage.used),
                bytes_to_gb(usage.free),
                usage.percent,
                fs_type
            ]
            logger.debug(f"Adding row: {row}")
            rows.append(row)

        except PermissionError:
            logger.warning(f"Permission denied for mountpoint: {part.mountpoint}")
            continue
        except Exception as e:
            logger.error(f"Failed to access {part.mountpoint}: {e}")
            continue

    return sorted(rows, key=lambda x: x[4], reverse=True)

def print_storage_table(rows):
    """Display disk usage in a formatted table"""
    logger.debug("Preparing output table")
    table = PrettyTable()
    table.field_names = [
        "Mount Point", 
        "Total (GB)", 
        "Used (GB)", 
        "Free (GB)", 
        "Use %", 
        "Filesystem"
    ]
    table.align["Mount Point"] = "l"
    table.float_format = ".1"

    for row in rows:
        table.add_row(row)

    print("\nCurrent Storage Status:")
    print(table)

def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Show disk usage per mounted filesystem."
    )
    parser.add_argument(
        "-a", "--all",
        action="store_true",
        help="Include all mountpoints (system and pseudo filesystems)"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose debug logging"
    )
    return parser.parse_args()

def main():
    args = parse_arguments()

    if args.verbose:
        logger.setLevel(logging.DEBUG)
        logger.debug("Verbose logging enabled")

    logger.info("Disk usage monitor started")
    rows = collect_storage_info(include_all=args.all)
    print_storage_table(rows)
    timestamp = datetime.fromtimestamp(psutil.boot_time()).strftime('%Y-%m-%d %H:%M:%S')
    print(f"\nGenerated at: {timestamp}")
    logger.info("Disk usage monitor completed")

if __name__ == "__main__":
    main()
