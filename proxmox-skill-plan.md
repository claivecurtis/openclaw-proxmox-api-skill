# Proxmox VE API Skill Plan

## Architecture

The skill will be structured in a modular, layered architecture to integrate seamlessly with OpenClaw:

- **API Layer**: Core client module handling HTTP requests, authentication, and error handling. Supports both token-based auth for remote access and local pvesh for on-cluster operations.
- **Business Logic Layer**: High-level functions for VM/cluster management, abstracting API calls into user-friendly operations (e.g., create VM, migrate, backup).
- **Workflow Layer**: Orchestrates complex tasks, including async task polling, retries, and user confirmations.
- **Integration Layer**: Hooks into OpenClaw tools like `exec` for shell commands, `subagents` for long-running tasks, and `message` for notifications.

This modularity allows for easy testing, updates, and extension (e.g., adding support for Ceph or SDN).

## Sources

1. **Proxmox VE API Wiki**: https://pve.proxmox.com/wiki/Proxmox_VE_API
   - REST API at `https://pve:8006/api2/json/`
   - JSON data + Schema
   - Auth: Ticket (cookie + CSRF token) or API Token (PVEAPIToken header)
   - pvesh CLI for local proxy
   - Examples: Container create, status.

2. **API Viewer**: https://pve.proxmox.com/pve-docs/api-viewer/index.html
   - Interactive docs: /nodes, /cluster/resources, /vms, /storage, tasks, etc.

## Proxmox API Edge Cases

- **Asynchronous Tasks**: Operations like VM creation, migration, or backup return a UPID (unique process ID). Poll `/nodes/{node}/tasks/{upid}` for status (running, stopped, failed). Handle timeouts and failures with retries.
- **Cluster Considerations**: In multi-node clusters, ensure operations respect HA and quorum. API calls may fail during node elections or network splits; implement retry with exponential backoff.
- **Error Handling**: API returns 4xx/5xx errors with JSON bodies. Handle specific codes (e.g., 403 for permissions, 409 for conflicts). Rate limiting is rare but possible; add delays if needed.
- **Pagination and Limits**: Some endpoints (e.g., /cluster/resources) support pagination; implement offset/limit for large lists.
- **State Dependencies**: VM actions (start/stop) depend on current state; check `/nodes/{node}/qemu/{vmid}/status/current` before actions.
- **Storage and Network Variability**: Endpoints vary by storage type (NFS, ZFS); validate configs against schema.

## Security/Auth Best Practices

- **Authentication**: Prefer API tokens over tickets for automation (longer-lived, no CSRF). Tokens are user:token format; store encrypted in workspace/secrets/pve-token.txt (use OpenClaw's secrets management).
- **Authorization**: Use principle of least privilege; create dedicated API users with minimal permissions (e.g., VM.PowerMgmt, VM.Audit). Avoid admin tokens.
- **Secure Storage**: Encrypt tokens at rest; use environment variables or secure vaults. Rotate tokens periodically via automation.
- **HTTPS Enforcement**: Always use HTTPS; validate SSL certificates to prevent MITM attacks.
- **Logging and Audit**: Log API calls and responses (sans sensitive data) for debugging and compliance. Avoid logging passwords or tokens.
- **Elevated Operations**: Require explicit user confirmation for destructive actions (delete, power off) via OpenClaw's confirmation prompts.

## Scripts Design

Scripts will be Python-based for readability and cross-platform compatibility:

- **Modular Structure**: `client.py` for API client class, `workflows.py` for task orchestration, `utils.py` for helpers (config parsing, logging).
- **Error Handling**: Use try/except with custom exceptions (e.g., ProxmoxAuthError, TaskTimeoutError). Implement logging with levels (INFO, ERROR) to workspace/logs/.
- **Configuration Management**: Use YAML/JSON configs for endpoints, defaults, and user-specific settings. Load from `assets/config.yaml`.
- **Testing**: Include unit tests for API calls using mocks; integration tests via a test cluster if possible.
- **Dependencies**: Minimal: requests, pyyaml, python-logging. Avoid heavy libs for portability.

## Workflows

Detailed workflows for common tasks, with error recovery and user interaction:

1. **List VMs/Nodes**: Simple GET to /cluster/resources; filter by type (qemu, lxc). Output formatted table.
2. **VM Power Management**: Check status, then POST to /nodes/{node}/qemu/{vmid}/status/{action}. Confirm destructive actions (stop/reboot).
3. **Create VM**: Use template from assets/templates/; validate config (cores, memory). POST to /nodes/{node}/qemu, poll task until completion.
4. **Snapshot/Backup**: POST snapshot, monitor progress. For backups, use vzdump via API or exec; handle large tasks with subagents.
5. **Migrate VM**: Ensure target node has resources; POST migrate, poll until done. Rollback on failure (if supported).
6. **Cluster Monitoring**: Cron job to poll /cluster/resources; alert on low resources or node down via message tool.
7. **Error Recovery**: For failed tasks, retry with backoff; notify user if manual intervention needed.

## Risks and Mitigations

- **Cluster Disruption**: HA migrations can cause downtime; test in staging. Mitigation: Use live migration where possible, schedule during low-traffic.
- **Secrets Management**: Token leaks could compromise cluster. Mitigation: Encrypt storage, audit access logs.
- **API Changes**: Proxmox updates may break endpoints. Mitigation: Version pinning, monitor changelogs; implement schema validation.
- **Network Failures**: Interrupt polls or actions. Mitigation: Retry logic, timeouts, idempotent operations.
- **Misconfigurations**: Wrong VM configs lead to boot failures. Mitigation: Validate against Proxmox schemas, use templates.
- **Data Loss**: Accidental deletes. Mitigation: Confirmations, backups before destructive ops.
- **Resource Exhaustion**: Over-provisioning. Mitigation: Monitor via cron, set limits in workflows.

## Thoughts

**Strengths:**
- Mature REST API, JSON, well-doc'd.
- pvesh for local, curl for remote.

**Challenges:**
- Auth: Token preferred (no CSRF), store securely (workspace/secrets).
- Cluster: Multi-node, tasks async (poll /nodes/{node}/tasks/{upid}).
- Permissions: API user needs privs (VM.Audit, VM.PowerMgmt etc.).
- Security: No destructive w/o confirm, elevated exec.

**OpenClaw fit:**
- exec curl/python-requests.
- cron for monitoring.
- subagents for long tasks (backup).

## Implementation Overview

**Skill dir:** `skills/proxmox/`

- **SKILL.md:** Trigger: \"proxmox\", \"pve\", VM/cluster mgmt.
  Workflows: List nodes/VMs, power, snapshot, backup, migrate, create.

- **scripts/client.py:** Python API client (requests, auth token, common methods: list_vms, vm_action). Includes async task polling, error handling.

- **scripts/workflows.py:** Orchestrates complex operations with retries and confirmations.

- **references/endpoints.md:** Key paths (extract from viewer).

- **assets/templates/:** VM config templates (YAML).

- **assets/config.yaml:** User configs (endpoint, token path, defaults).

- **tests/test_client.py:** Unit tests.

**Setup:**
1. User adds token to workspace/secrets/pve-token.txt
2. Configure assets/config.yaml with cluster details.
3. Test auth: GET /version
4. Common: `sessions_spawn agentId=proxmox task=\"list VMs on node1\"`

**Next:** Create draft SKILL.md + client.py + workflows.py. Review for integration.