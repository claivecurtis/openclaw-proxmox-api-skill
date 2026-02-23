# OpenClaw Proxmox API Skill

## Overview
This skill provides integration with Proxmox Virtual Environment (PVE) API for managing virtual machines, containers, nodes, and cluster resources. It uses the REST API with token-based authentication for secure remote management.

## Triggers
Use this skill when the user mentions:
- "proxmox" or "pve"
- VM/cluster management tasks like "list VMs", "start VM", "stop VM", "migrate VM", "create VM", "snapshot VM", "backup VM"
- Monitoring cluster status or resources
- Power management for VMs/LXCs

## Usage
Load the skill by reading this file and the scripts/client.py. The main interface is through Python scripts in the `scripts/` directory.

### Prerequisites
1. Create API token in Proxmox for a user with appropriate permissions (VM.Audit, VM.PowerMgmt, etc.).
2. Set `OPENCLAW_WORKSPACE` environment variable to your OpenClaw workspace path (optional, defaults to relative path).
3. Store token in `workspace/secrets/pve-token.txt`.
4. `cp assets/config.proxmox.example.yaml workspace/secrets/config.proxmox.yaml && edit`

### Workflows

#### List VMs/Nodes
- **Script:** `scripts/client.py` `list_vms()`
- **Description:** Retrieves all VMs and LXCs in the cluster.
- **Output:** List of dicts with id, name, node, status, type, etc.

#### VM Power Management
- **Script:** `scripts/client.py` `vm_action(node, vmid, action)`
- **Actions:** start, stop, reboot, shutdown, suspend, resume
- **Description:** Performs power actions on a specific VM. Asynchronous actions return UPID and require polling.
- **Safety:** Destructive actions (stop, reset) require confirmation.

#### Task Polling
- **Script:** `scripts/client.py` `poll_task(node, upid)`
- **Description:** Monitors asynchronous tasks until completion.
- **Timeout:** Default 300s, poll every 5s.

#### Advanced Operations
- VM creation from templates
- Snapshots and backups (via `vm_backup`)
- Migration (via `vm_migrate`)
- Pool management (via `list_pools`)
- Cluster monitoring

### Error Handling
- `ProxmoxAuthError`: Authentication issues (check token/config)
- `ProxmoxAPIError`: API errors (permissions, invalid params)
- `TaskTimeoutError`: Async tasks exceed timeout

### Integration with OpenClaw
- All `exec` calls should set `workdir="/home/claw/.openclaw/workspace/skills/openclaw-proxmox-api-skill"` for proper module imports.
- Use `exec` to run Python scripts for API calls.
- Spawn `subagents` for long-running tasks (backups, migrations).
- Send notifications via `message` tool for monitoring alerts.

**Example (auth test):**
```
exec workdir="/home/claw/.openclaw/workspace/skills/openclaw-proxmox-api-skill" command="python3 -c 'from scripts.client import load_client; c=load_client(); print(\"Auth OK\")'"
```
Expected: `Auth OK` (no PII/hosts).

## Dependencies
See `requirements.txt` for Python packages.

## Testing
Run `pytest` in the skill directory for unit tests with mocks.

### PAM Authentication Notes
- **PAM users (@pam)** map to **Linux system users**—run `useradd username` on Proxmox host first (PVE UI alone insufficient).
- **403 Sys.Audit (/)**? Token lacks privs: UI → Datacenter → Permissions → API Tokens → Edit token → Add **Role `PVEAudit`** path `/` (or User ACL priv `Sys.Audit` /).
- **Multi-cluster/large env**: Prefer LDAP/external realms over PAM (better scaling/auth delegation)."
