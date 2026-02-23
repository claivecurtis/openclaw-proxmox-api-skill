#!/usr/bin/env python3
"""
Example script to clone a VM in Proxmox.

Usage: python vm_clone.py <node> <source_vmid> <new_vmid> [new_name]
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from client import load_client

def main():
    if len(sys.argv) < 4:
        print("Usage: python vm_clone.py <node> <source_vmid> <new_vmid> [new_name]")
        sys.exit(1)

    node = sys.argv[1]
    source_vmid = int(sys.argv[2])
    new_vmid = int(sys.argv[3])
    new_name = sys.argv[4] if len(sys.argv) > 4 else f"clone-{source_vmid}"

    try:
        client = load_client()

        config = {'name': new_name}

        print(f"Cloning VM {source_vmid} to {new_vmid} on node {node}...")
        upid = client.vm_clone(source_vmid, node, new_vmid, config)

        print(f"Task initiated, UPID: {upid}")
        # Poll for completion
        client.poll_task(node, upid)
        print("VM cloned successfully.")

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()