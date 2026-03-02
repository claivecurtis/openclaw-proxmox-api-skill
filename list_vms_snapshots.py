#!/usr/bin/env python3
from scripts.client import load_client

def main():
    c = load_client()
    vms = c.list_vms()
    vms_with_snaps = []
    for vm in vms:
        vmid = vm.get('vmid') or vm.get('id')
        node = vm.get('node')
        name = vm.get('name', 'None')
        status = vm.get('status', 'unknown')
        vm_type = vm.get('type', 'qemu')
        is_lxc = vm_type == 'lxc'
        try:
            snaps = c.vm_snapshot_list(node, vmid, is_lxc)
            if snaps:
                snap_names = [s['name'] for s in snaps]
                vms_with_snaps.append({
                    'VMID': vmid,
                    'Name': name,
                    'Node': node,
                    'Status': status,
                    'Snapshots': ', '.join(snap_names)
                })
        except Exception as e:
            print(f"Error getting snaps for {vmid}: {e}")
    
    print("VMs with snapshots:")
    print("VMID\tName\tNode\tStatus\tSnapshots")
    for vm in vms_with_snaps:
        print(f"{vm['VMID']}\t{vm['Name']}\t{vm['Node']}\t{vm['Status']}\t{vm['Snapshots']}")

if __name__ == '__main__':
    main()