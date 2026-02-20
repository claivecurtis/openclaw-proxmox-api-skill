#!/usr/bin/env python3
"""
Example script to list all VMs and LXCs in a Proxmox cluster.

Usage: python list_vms.py
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from client import load_client
import json

def main():
    try:
        client = load_client()
        vms = client.list_vms()

        print("VMs and LXCs in cluster:")
        print("-" * 50)
        for vm in vms:
            print(f"ID: {vm['vmid']}, Name: {vm.get('name', 'N/A')}, Node: {vm['node']}, Status: {vm['status']}, Type: {vm['type']}")

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()