# Proxmox API Connector - Requirements & Technical Plan

## 1. Overview
The Proxmox API Connector (skill) will enable OpenClaw to manage Proxmox Virtual Environment (PVE) clusters. It focuses on automation, monitoring, and administrative tasks using the REST API or `pvesh` CLI.

## 2. Authentication & Authorization
### 2.1 Methods
- **Primary (Remote):** API Token Authentication. Format: `USER@REALM!TOKENID=UUID`.
    - Sent via HTTP Header: `Authorization: PVEAPIToken=USER@REALM!TOKENID=UUID`.
    - Avoids CSRF requirements of the Ticket-based system.
- **Secondary (Local/Proxy):** `pvesh` CLI. Used if running on a Proxmox node or via SSH jump host.

### 2.2 Security
- Tokens MUST be stored in the OpenClaw workspace secrets directory (e.g., `workspace/secrets/pve-token.txt`).
- The Proxmox user should be restricted to a custom role (e.g., `OpenClawManager`) with necessary permissions only:
    - `VM.Audit`, `VM.Monitor`, `VM.PowerMgmt`, `VM.Console`, `VM.Backup`, `VM.Snapshot`.
    - `Datastore.Audit`, `Sys.Audit`.

## 3. API Endpoints (Initial Scope)
| Function | Method | Path |
| :--- | :--- | :--- |
| **Cluster Status** | GET | `/cluster/status` |
| **Resources List** | GET | `/cluster/resources` (filter by `type`) |
| **Node Stats** | GET | `/nodes/{node}/status` |
| **VM/LXC List** | GET | `/nodes/{node}/qemu` or `/nodes/{node}/lxc` |
| **VM Status** | GET | `/nodes/{node}/qemu/{vmid}/status/current` |
| **Power Actions** | POST | `/nodes/{node}/qemu/{vmid}/status/{start,stop,reset,shutdown,suspend,resume}` |
| **Snapshots** | POST/GET | `/nodes/{node}/qemu/{vmid}/snapshot` |
| **Task Status** | GET | `/nodes/{node}/tasks/{upid}/status` |

## 4. Workflows & Async Handling
### 4.1 Task Polling
Most write operations (start, backup, migrate) return a **UPID** (Unique Process ID).
1. **Initiate:** Call the action endpoint.
2. **Poll:** Periodically check `/nodes/{node}/tasks/{upid}/status`.
3. **Finish:** Return success or failure based on the `exitstatus` field.

### 4.2 Destructive Actions
- `stop`, `reset`, and `delete` actions MUST require explicit user confirmation via the OpenClaw `message` tool or `subagents` steering before execution.

### 4.3 Monitoring
- A cron-driven workflow to check for high resource usage (CPU/RAM) or node downtime.
- Alerts delivered via the `message` tool.

## 5. Technical Stack
- **Language:** Python 3.
- **Dependencies:** `requests` (HTTP), `pyyaml` (Config), `tabulate` (Formatting lists).
- **Module Structure:**
    - `client.py`: Low-level wrapper for HTTP requests, auth, and UPID polling.
    - `manager.py`: Business logic (e.g., "Safe Shutdown" which waits for task completion).
    - `cli_adapter.py`: Optional wrapper for `pvesh` if API access is restricted.

## 6. Implementation Plan
### Phase 1: Core Client & Auth
- [ ] Create `assets/config.yaml` template.
- [ ] Implement `client.py` with Token Auth.
- [ ] Implement basic `list-vms` and `node-status` commands.

### Phase 2: Action Workflows
- [ ] Implement Power Management (Start/Stop).
- [ ] Implement UPID polling logic.
- [ ] Add confirmation logic for destructive actions.

### Phase 3: Advanced Operations
- [ ] Snapshot management.
- [ ] Basic VM/LXC creation from templates.
- [ ] Monitoring cron jobs.

### Phase 4: OpenClaw Integration
- [ ] Finalize `SKILL.md` for tool registration.
- [ ] Test with `subagents` for long-running backup/migration tasks.
