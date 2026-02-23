#!/usr/bin/env python3
"""
Example script to create a snapshot of a VM in Proxmox.

Usage: python vm_snapshot.py <node> <vmid> <snapname> [description]
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from client import load_client

def main():
    if len(sys.argv) < 4:
        print("Usage: python vm_snapshot.py <node> <vmid> <snapname> [description]")
        sys.exit(1)

    node = sys.argv[1]
    vmid = int(sys.argv[2])
    snapname = sys.argv[3]
    description = sys.argv[4] if len(sys.argv) > 4 else None

    try:
        client = load_client()

        print(f"Creating snapshot '{snapname}' for VM {vmid} on node {node}...")
        upid = client.vm_snapshot_create(vmid, node, snapname, description)

        print(f"Task initiated, UPID: {upid}")
        # Poll for completion
        client.poll_task(node, upid)
        print("Snapshot created successfully.")

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()