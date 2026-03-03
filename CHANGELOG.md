# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Multi-cluster and PBS support: config lists for clusters/pbs, client factories with cluster selection (PR #28)
- PBS backup API support (PR #27)
- AI execution reminder (PR #26)
- Live Verify policy to prevent stale memory reports (PR #25)
- Auto-update cluster and PBS names on client load (PR #30)

### Fixed
- Generic host in example.yaml (PR #23)
- Remove unnecessary local config.yaml (PR #22)

### Changed
- UPID review with auto_poll and snapshot config migration (PR #21)
- Fix snapshot name validation to prevent loops on invalid names (PR #19)
- Fix secrets path resolution to skill/secrets/ (PR #18, #17)
- README: Add output length and platform/model recommendations (PR #16)
- Roadmap: Rename phase 5 and add multi-cluster consideration (PR #15)
- SKILL.md: Self-contained Discord format (PR #14)
- SKILL.md: Add Discord output note (PR #13)
- Docs: PAM auth Linux useradd req + token ACL Sys.Audit + alt auth recs (PR #12)

## [0.4.0] - 2026-02-23

### Added
- **Proxmox Backup Server (PBS) Integration**
  - `pbs_connect(endpoint, token)`: Connect to PBS (PBSClient)
  - `pbs_datastore_list()`: List datastores (list_datastores)
  - `pbs_datastore_create(name, config)`: Create datastore (create_datastore)
  - `pbs_backup_list(datastore)`: List backups (list_backups)
  - `pbs_backup_create(datastore, backup_spec)`: Create backup (backup_vm)
  - `pbs_backup_restore(datastore, backup_id, target)`: Restore backup (restore_backup)
  - `pbs_backup_delete(datastore, backup_id)`: Delete backup (delete_backup)
  - `pbs_tasks()`: List PBS tasks (list_tasks)
  - `pbs_sync(datastore, remote)`: Sync datastore (sync_datastore)
  - `vm_backup(node, vmid, storage)`: Backup VM/container to storage using vzdump (via VM.backup())
  - `load_pbs_client()`: Load PBS client from config
- **Monitoring and Logging**
  - RRD data retrieval for all entities (VMs, nodes, storage, etc.) (rrd methods added)
  - Task monitoring and status polling (poll_task)
  - Log retrieval for nodes and cluster (cluster_logs, node_syslog)
- **Firewall Management**
  - Full firewall rule management for cluster, nodes, VMs, containers (firewall methods in phase 3)
- **High Availability (HA)**
  - HA group management (ha_groups)
  - HA resource management (ha_resources)
  - HA status and failover operations (cluster_ha)
- **Miscellaneous Features**
  - Version information retrieval (/version)
  - Subscription status (node_subscription)
  - Certificate management (node_certificates)
  - Remote migration for VMs/containers (vm_migrate with target_node)

## [0.3.0] - 2026-02-23

### Added
- **Access Control**
  - `user_list()`: List users
  - `user_create(userid, config)`: Create user
  - `user_delete(userid)`: Delete user
  - `group_list()`: List groups
  - `group_create(groupid)`: Create group
  - `role_list()`: List roles
  - `role_create(roleid, privs)`: Create role
  - `permission_list()`: List permissions
  - `domain_list()`: List authentication domains
  - `token_create(user, tokenid)`: Create API token
  - `token_delete(user, tokenid)`: Delete API token
- **Advanced Storage Operations**
  - `storage_upload(storage, file, content)`: Upload file to storage
  - `storage_download(storage, file)`: Download file from storage
  - `storage_rrd(storage)`: Get storage RRD data
  - `storage_scan(storage)`: Scan storage for content
- **Advanced Cluster Operations**
  - `cluster_firewall()`: Cluster firewall management
  - `cluster_ha()`: High availability management
  - `cluster_resources()`: List cluster resources
  - `cluster_nextid()`: Get next available VMID
- **Advanced Node Operations**
  - `node_firewall(node)`: Node firewall
  - `node_dns(node)`: DNS settings
  - `node_time(node)`: Time settings
  - `node_version(node)`: Software version
  - `node_apt(node)`: Package management
  - `node_subscription(node)`: Subscription management
  - `node_syslog(node)`: Syslog access
  - `node_rrd(node)`: RRD data
  - `node_vncshell(node)`: VNC shell access
  - `node_spiceshell(node)`: SPICE shell access
  - `node_migrateall(node)`: Migrate all VMs/containers
  - `node_startall(node)`: Start all VMs/containers
  - `node_stopall(node)`: Stop all VMs/containers
  - `node_ceph(node)`: Ceph management

## [0.2.0] - 2026-02-23

### Added
- **Advanced VM Operations**
  - `vm_clone(vmid, node, newid, config)`: Clone a VM (via VM.clone())
  - `vm_snapshot_create(vmid, node, snapname)`: Create VM snapshot (via VM.snapshot_create())
  - `vm_snapshot_list(vmid, node)`: List VM snapshots (via VM.snapshot_list())
  - `vm_snapshot_rollback(vmid, node, snapname)`: Rollback to snapshot (via VM.snapshot_rollback())
  - `vm_snapshot_delete(vmid, node, snapname)`: Delete snapshot (via VM.snapshot_delete())
  - `vm_migrate(vmid, node, target_node)`: Migrate VM to another node (via VM.migrate())
  - `vm_resize(vmid, node, disk, size)`: Resize VM disk (via VM.resize())
  - `vm_move_volume(vmid, node, volume, storage)`: Move VM volume to different storage (via VM.move_volume())
  - `vm_template(vmid, node)`: Convert VM to template (via VM.template())
  - `vm_vncproxy(vmid, node)`: Get VNC proxy for VM (via VM.vncproxy())
  - `vm_spiceproxy(vmid, node)`: Get SPICE proxy for VM (via VM.spiceproxy())
  - `vm_monitor(vmid, node, command)`: Send monitor command to VM (via VM.monitor())
  - `vm_firewall(vmid, node)`: Manage VM firewall rules (via VM.firewall())
- **Container Operations (LXC)**
  - All basic operations similar to VMs: list, status, start, stop, reboot, shutdown, create, delete, config_get, config_set (via Container class)
  - `container_clone(vmid, node, newid)`: Clone a container (via Container.clone())
  - `container_snapshot_*`: Snapshot operations (via Container.snapshot_*)
  - `container_migrate(vmid, node, target_node)`: Migrate container (via Container.migrate())
  - `container_template(vmid, node)`: Convert to template (via Container.template())
  - `container_firewall(vmid, node)`: Firewall management (via Container.firewall())
  - `container_vncproxy`, `container_spiceproxy`: Proxy access (via Container.vncproxy/spiceproxy)

## [0.1.0] - 2026-02-22

### Added
- **Authentication**
  - Methods for ticket-based authentication (`get_ticket`, `refresh_ticket`)
  - Methods for API token authentication
  - CSRF token handling for write operations
  - Base HTTP client setup with SSL verification options
- **Cluster Operations**
  - `cluster_status()`: Get cluster status
  - `cluster_tasks()`: List cluster tasks
  - `cluster_logs()`: Retrieve cluster logs
  - `cluster_backup()`: Manage cluster backups
- **Node Operations**
  - `node_status(node)`: Get node status
  - `node_tasks(node)`: List node tasks
  - `node_services(node)`: Manage node services (start/stop/restart/status)
  - `node_storage(node)`: List node storage
- **Basic VM Operations (QEMU)**
  - `vm_list(node)`: List VMs on a node (via VM.list())
  - `vm_status(vmid, node)`: Get VM status (via VM.status())
  - `vm_start(vmid, node)`: Start a VM (via VM.start())
  - `vm_stop(vmid, node)`: Stop a VM (via VM.stop())
  - `vm_reboot(vmid, node)`: Reboot a VM (via VM.reboot())
  - `vm_shutdown(vmid, node)`: Shutdown a VM (via VM.shutdown())
  - `vm_create(node, config)`: Create a new VM (via VM.create())
  - `vm_delete(vmid, node)`: Delete a VM (via VM.delete())
  - `vm_config_get(vmid, node)`: Get VM configuration (via VM.config_get())
  - `vm_config_set(vmid, node, config)`: Update VM configuration (via VM.config_set())
- **Basic Storage Operations**
  - `storage_list()`: List all storage (via Storage.list())
  - `storage_status(storage)`: Get storage status (via Storage.status())
  - `storage_content(storage)`: List storage content (via Storage.content())
  - `storage_create(config)`: Create new storage (via Storage.create())
  - `storage_delete(storage)`: Delete storage (via Storage.delete())
- **Basic Pool Operations**
  - `pool_list()`: List all pools (via Pool.list())
  - `pool_members(pool)`: Get pool members (via Pool.members())
  - `pool_create(pool)`: Create a new pool (via Pool.create())
  - `pool_delete(pool)`: Delete a pool (via Pool.delete())
  - `pool_update(pool, config)`: Update pool configuration (via Pool.update())
- **Configuration and Validation**
  - Pydantic config validation (ProxmoxConfig model)
  - Task polling helper function `poll_task_until_complete`
  - Input validation for vmid/node and idempotency pre-checks

### Changed
- Generic secrets paths for any OpenClaw install (PR #7)
- Absolute paths for config/token to ensure compatibility across exec contexts (main/Discord)

### Fixed
- Sanitize auth example, no host/VM PII (skills security)

## [0.0.1] - 2026-02-19

### Added
- Initial commit: OpenClaw Proxmox API Skill
- PBS client and resource pools management
- Comprehensive tests with pytest mocks
- Examples and scripts
- Consolidated documentation
- Requirements.txt
- GitHub CI lint/test workflow
- Best practices files: LICENSE, CONTRIBUTING.md, CODE_OF_CONDUCT.md, SECURITY.md, .github templates
- README.md
- Dependabot configuration
- .gitignore