# Proxmox Skill Requirements & Implementation Plan

This document outlines the requirements and initial implementation strategy for the Proxmox VE API skill in OpenClaw.

## 1. Authentication Requirements
- **Preferred Method:** API Tokens (PVEAPIToken).
- **Header Format:** `Authorization: PVEAPIToken=USER@REALM!TOKENID=UUID`
- **Storage:** Tokens must be stored in `workspace/secrets/pve-token.txt`.
- **User Config:** Hostname, Port (default 8006), and Token ID should be in `assets/config.yaml`.
- **Security:** Use `--insecure` or skip certificate validation only if explicitly configured (self-signed certs are common in homelabs).

## 2. Core API Endpoints (Initial Scope)
| Function | Method | Endpoint |
| :--- | :--- | :--- |
| **Cluster Status** | GET | `/cluster/resources` |
| **Node List** | GET | `/nodes` |
| **VM/LXC List** | GET | `/nodes/{node}/qemu` or `/nodes/{node}/lxc` |
| **VM Status** | GET | `/nodes/{node}/qemu/{vmid}/status/current` |
| **Power Actions** | POST | `/nodes/{node}/qemu/{vmid}/status/{start,stop,shutdown,reboot}` |
| **Task Status** | GET | `/nodes/{node}/tasks/{upid}/status` |

## 3. Workflow Logic
### Task Polling (Async)
Many Proxmox operations (start, stop, clone) return a `UPID`. The skill must include a polling mechanism:
1. Extract `UPID` from the initial API response.
2. Poll `/nodes/{node}/tasks/{upid}/status` every 2-5 seconds.
3. Terminate when `status` is `stopped`. Check `exitstatus` (should be `OK`).

### Safety & Confirmation
- **Destructive Actions:** Actions like `stop` (force), `delete`, or `bulk-shutdown` must require an explicit user confirmation if triggered via the main agent.
- **Resource Check:** Before starting a VM, check if the node has sufficient memory/CPU (optional but recommended for high-tier logic).

## 4. Implementation Components

### `scripts/client.py` (The Engine)
- **Class `ProxmoxClient`**:
    - `__init__`: Load config and secrets.
    - `request(method, path, params)`: Handles headers, URL construction, and error logging.
    - `poll_task(node, upid)`: The async waiting logic.

### `scripts/actions.py` (The Skill interface)
- Mapping between OpenClaw tool calls and `ProxmoxClient` methods.
- Logic for formatting output (e.g., Markdown tables for VM lists).

### `SKILL.md` (The Definition)
- **Triggers:** `proxmox`, `pve`, `virtual machine`, `vm`, `lxc`.
- **Tool Descriptions:** Clear instructions for the LLM on how to call list, status, and power actions.

## 5. Next Steps

1. **Environment Setup:**
   - Create `skills/proxmox/` directory structure.
   - Create a dummy `assets/config.yaml` for the user to fill.
2. **Phase 1: Read-Only (Safety First):**
   - Implement `list-vms` and `node-status`.
   - Test connectivity with a real Proxmox instance (if available in the environment) or mocks.
3. **Phase 2: Power Control:**
   - Implement `vm-start`, `vm-stop`.
   - Implement the `UPID` polling logic.
4. **Phase 3: Advanced Ops:**
   - Snapshots, backups, and subagent-based long-running task monitoring.

---
*Created by OpenClaw Subagent*
