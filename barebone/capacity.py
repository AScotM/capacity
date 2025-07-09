#!/usr/bin/env python3

import os
import psutil
import subprocess
from prettytable import PrettyTable

def get_filesystem_type(mountpoint):
    """Determine filesystem type using df command"""
    try:
        df_output = subprocess.check_output(
            ["df", "-T", mountpoint], 
            stderr=subprocess.DEVNULL
        ).decode()
        # Example output: "/dev/sda1 ext4  ..."
        return df_output.splitlines()[1].split()[1]  # 2nd line, 2nd column
    except:
        return "unknown"

def get_storage_info():
    """Collect all mounted filesystems with capacity info"""
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

    for part in psutil.disk_partitions(all=False):
        if not part.mountpoint:
            continue
            
        try:
            usage = psutil.disk_usage(part.mountpoint)
            fs_type = get_filesystem_type(part.mountpoint)
            
            table.add_row([
                part.mountpoint,
                usage.total / (1024**3),
                usage.used / (1024**3),
                usage.free / (1024**3),
                usage.percent,
                fs_type
            ])
        except PermissionError:
            continue  # Skip inaccessible filesystems
            
    return table

if __name__ == "__main__":
    print("\nCurrent Storage Status:")
    print(get_storage_info())
    print(f"\nGenerated at: {psutil.boot_time()}")
