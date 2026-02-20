#!/usr/bin/env python3
"""
Example script to start a VM in Proxmox.

Usage: python vm_start.py <node> <vmid>
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from client import load_client

def main():
    if len(sys.argv) != 3:
        print("Usage: python vm_start.py <node> <vmid>")
        sys.exit(1)

    node = sys.argv[1]
    vmid = int(sys.argv[2])

    try:
        client = load_client()

        print(f"Starting VM {vmid} on node {node}...")
        upid = client.vm_action(node, vmid, 'start')

        if upid:
            print(f"Task initiated, UPID: {upid}")
            # Poll for completion
            client.poll_task(node, upid)
            print("VM started successfully.")
        else:
            print("VM started synchronously.")

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()