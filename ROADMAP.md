# Implementation Roadmap for openclaw-proxmox-api-skill

This roadmap outlines the step-by-step implementation of all features from the Proxmox VE (PVE) and Proxmox Backup Server (PBS) APIs into the openclaw-proxmox-api-skill. The skill will provide classes and methods to interact with Proxmox infrastructure, including VMs, containers, backups, storage, pools, clusters, and PBS.

Prioritization is based on core functionality required for basic management (core), advanced operations (high), secondary features (medium), and specialized or less common features (low).

## Overview

The skill will be implemented as a Python module with classes for different Proxmox entities:
- `ProxmoxAPI`: Main client class for authentication and base API calls.
- `VM`: Class for KVM virtual machines.
- `Container`: Class for LXC containers.
- `Storage`: Class for storage management.
- `Pool`: Class for resource pools.
- `Cluster`: Class for cluster operations.
- `PBS`: Class for Proxmox Backup Server integration.
- `Node`: Class for node-specific operations.

All methods will wrap the REST API endpoints, handling authentication (tickets/tokens), error handling, and data parsing.

## Step-by-Step Roadmap

### Phase 1: Core Infrastructure (Core Priority)

1. **Implement Authentication** ✅
   - Methods for ticket-based authentication (`get_ticket`, `refresh_ticket`).
   - Methods for API token authentication.
   - CSRF token handling for write operations.
   - Base HTTP client setup with SSL verification options.

2. **Implement Cluster Operations** ✅
   - `cluster_status()`: Get cluster status.
   - `cluster_tasks()`: List cluster tasks.
   - `cluster_logs()`: Retrieve cluster logs.
   - `cluster_backup()`: Manage cluster backups.

3. **Implement Node Operations** ✅
   - `node_status(node)`: Get node status.
   - `node_tasks(node)`: List node tasks.
   - `node_services(node)`: Manage node services (start/stop/restart/status).
   - `node_storage(node)`: List node storage.

4. **Implement Basic VM Operations (QEMU)** ✅
   - `vm_list(node)`: List VMs on a node. ✅ (via VM.list())
   - `vm_status(vmid, node)`: Get VM status. ✅ (via VM.status())
   - `vm_start(vmid, node)`: Start a VM. ✅ (via VM.start())
   - `vm_stop(vmid, node)`: Stop a VM. ✅ (via VM.stop())
   - `vm_reboot(vmid, node)`: Reboot a VM. ✅ (via VM.reboot())
   - `vm_shutdown(vmid, node)`: Shutdown a VM. ✅ (via VM.shutdown())
   - `vm_create(node, config)`: Create a new VM. ✅ (via VM.create())
   - `vm_delete(vmid, node)`: Delete a VM. ✅ (via VM.delete())
   - `vm_config_get(vmid, node)`: Get VM configuration. ✅ (via VM.config_get())
   - `vm_config_set(vmid, node, config)`: Update VM configuration. ✅ (via VM.config_set())

5. **Implement Basic Storage Operations** ✅
   - `storage_list()`: List all storage. ✅ (via Storage.list())
   - `storage_status(storage)`: Get storage status. ✅ (via Storage.status())
   - `storage_content(storage)`: List storage content. ✅ (via Storage.content())
   - `storage_create(config)`: Create new storage. ✅ (via Storage.create())
   - `storage_delete(storage)`: Delete storage. ✅ (via Storage.delete())

6. **Implement Basic Pool Operations** ✅
   - `pool_list()`: List all pools. ✅ (via Pool.list())
   - `pool_members(pool)`: Get pool members. ✅ (via Pool.members())
   - `pool_create(pool)`: Create a new pool. ✅ (via Pool.create())
   - `pool_delete(pool)`: Delete a pool. ✅ (via Pool.delete())
   - `pool_update(pool, config)`: Update pool configuration. ✅ (via Pool.update())

   **Notes for Phase 1 Part 2:**
   - Added pydantic config validation (ProxmoxConfig model).
   - Refactored methods into separate VM, Storage, Pool wrapper classes for better organization.
   - Added task polling helper function `poll_task_until_complete`.
   - All methods support both QEMU and LXC where applicable.
   - Error handling and logging improved throughout.
   - Requires pydantic>=1.8.0 added to requirements.txt.

### Phase 2: Advanced VM and Container Features (High Priority) ✅

7. **Implement Advanced VM Operations** ✅
   - `vm_clone(vmid, node, newid, config)`: Clone a VM. ✅ (via VM.clone())
   - `vm_snapshot_create(vmid, node, snapname)`: Create VM snapshot. ✅ (via VM.snapshot_create())
   - `vm_snapshot_list(vmid, node)`: List VM snapshots. ✅ (via VM.snapshot_list())
   - `vm_snapshot_rollback(vmid, node, snapname)`: Rollback to snapshot. ✅ (via VM.snapshot_rollback())
   - `vm_snapshot_delete(vmid, node, snapname)`: Delete snapshot. ✅ (via VM.snapshot_delete())
   - `vm_migrate(vmid, node, target_node)`: Migrate VM to another node. ✅ (via VM.migrate())
   - `vm_resize(vmid, node, disk, size)`: Resize VM disk. ✅ (via VM.resize())
   - `vm_move_volume(vmid, node, volume, storage)`: Move VM volume to different storage. ✅ (via VM.move_volume())
   - `vm_template(vmid, node)`: Convert VM to template. ✅ (via VM.template())
   - `vm_vncproxy(vmid, node)`: Get VNC proxy for VM. ✅ (via VM.vncproxy())
   - `vm_spiceproxy(vmid, node)`: Get SPICE proxy for VM. ✅ (via VM.spiceproxy())
   - `vm_monitor(vmid, node, command)`: Send monitor command to VM. ✅ (via VM.monitor())
   - `vm_firewall(vmid, node)`: Manage VM firewall rules. ✅ (via VM.firewall())

8. **Implement Container Operations (LXC)** ✅
   - All basic operations similar to VMs: list, status, start, stop, reboot, shutdown, create, delete, config_get, config_set. ✅ (via Container class)
   - `container_clone(vmid, node, newid)`: Clone a container. ✅ (via Container.clone())
   - `container_snapshot_*`: Snapshot operations. ✅ (via Container.snapshot_*)
   - `container_migrate(vmid, node, target_node)`: Migrate container. ✅ (via Container.migrate())
   - `container_template(vmid, node)`: Convert to template. ✅ (via Container.template())
   - `container_firewall(vmid, node)`: Firewall management. ✅ (via Container.firewall())
   - `container_vncproxy`, `container_spiceproxy`: Proxy access. ✅ (via Container.vncproxy/spiceproxy)

   **Notes for Phase 2:**
   - Added Container class inheriting from VM for dedicated LXC operations.
   - All advanced operations support both QEMU (VM) and LXC (Container).
   - Maintained consistent API and error handling.

### Phase 3: Secondary Features (Medium Priority)

9. **Implement Access Control**
   - `user_list()`: List users.
   - `user_create(userid, config)`: Create user.
   - `user_delete(userid)`: Delete user.
   - `group_list()`: List groups.
   - `group_create(groupid)`: Create group.
   - `role_list()`: List roles.
   - `role_create(roleid, privs)`: Create role.
   - `permission_list()`: List permissions.
   - `domain_list()`: List authentication domains.
   - `token_create(user, tokenid)`: Create API token.
   - `token_delete(user, tokenid)`: Delete API token.

10. **Implement Advanced Storage Operations**
    - `storage_upload(storage, file, content)`: Upload file to storage.
    - `storage_download(storage, file)`: Download file from storage.
    - `storage_rrd(storage)`: Get storage RRD data.
    - `storage_scan(storage)`: Scan storage for content.

11. **Implement Advanced Cluster Operations**
    - `cluster_firewall()`: Cluster firewall management.
    - `cluster_ha()`: High availability management.
    - `cluster_resources()`: List cluster resources.
    - `cluster_nextid()`: Get next available VMID.

12. **Implement Node Advanced Operations**
    - `node_firewall(node)`: Node firewall.
    - `node_dns(node)`: DNS settings.
    - `node_time(node)`: Time settings.
    - `node_version(node)`: Software version.
    - `node_apt(node)`: Package management.
    - `node_subscription(node)`: Subscription management.
    - `node_syslog(node)`: Syslog access.
    - `node_rrd(node)`: RRD data.
    - `node_vncshell(node)`: VNC shell access.
    - `node_spiceshell(node)`: SPICE shell access.
    - `node_migrateall(node)`: Migrate all VMs/containers.
    - `node_startall(node)`: Start all VMs/containers.
    - `node_stopall(node)`: Stop all VMs/containers.
    - `node_ceph(node)`: Ceph management.

### Phase 4: Specialized Features (Low Priority)

13. **Implement Proxmox Backup Server (PBS) Integration**
    - `pbs_connect(endpoint, token)`: Connect to PBS.
    - `pbs_datastore_list()`: List datastores.
    - `pbs_datastore_create(name, config)`: Create datastore.
    - `pbs_backup_list(datastore)`: List backups.
    - `pbs_backup_create(datastore, backup_spec)`: Create backup.
    - `pbs_backup_restore(datastore, backup_id, target)`: Restore backup.
    - `pbs_backup_delete(datastore, backup_id)`: Delete backup.
    - `pbs_tasks()`: List PBS tasks.
    - `pbs_sync(datastore, remote)`: Sync datastore.
    - `pbs_tape_*`: Tape backup operations (if applicable).

14. **Implement Monitoring and Logging**
    - RRD data retrieval for all entities (VMs, nodes, storage, etc.).
    - Task monitoring and status polling.
    - Log retrieval for nodes and cluster.

15. **Implement Firewall Management**
    - Full firewall rule management for cluster, nodes, VMs, containers.

16. **Implement High Availability (HA)**
    - HA group management.
    - HA resource management.
    - HA status and failover operations.

17. **Implement Miscellaneous Features**
    - Version information retrieval.
    - Subscription status.
    - Certificate management.
    - Remote migration for VMs/containers.

## Implementation Notes

- Each phase builds on the previous; core features must be completed before advanced ones.
- Use asynchronous methods where appropriate for long-running operations (e.g., VM start/stop).
- Implement comprehensive error handling and validation.
- Provide both synchronous and asynchronous APIs.
- Include unit tests for each method.
- Document all classes and methods with docstrings.
- Ensure compatibility with latest PVE and PBS versions.
- Use the official API schema for parameter validation.

## Dependencies

- `requests` or `httpx` for HTTP client.
- `asyncio` for async operations (if needed).
- Optional: `proxmoxer` library for reference implementation.

This roadmap covers all major API endpoints based on the Proxmox VE and PBS API documentation.

## API References

### Proxmox VE (PVE)

- [Proxmox VE API Wiki](https://pve.proxmox.com/wiki/Proxmox_VE_API)
- [PVE API Viewer](https://pve.proxmox.com/pve-docs/api-viewer/)

### Proxmox Backup Server (PBS)

- [PBS Backup Protocol Documentation](https://pbs.proxmox.com/docs/backup-protocol.html)
- [PBS API Viewer](https://pbs.proxmox.com/docs/api-viewer/)