# OpenClaw Proxmox API Skill 🖥️

Proxmox VE API integration for OpenClaw agents.

## Features
- Cluster/node/VM management
- Resource queries/monitoring
- Power ops (start/stop/reboot/migrate)
- VM backups and snapshots
- Migration between nodes
- Storage pool management
- Async task polling
- Secure token-based authentication

## Setup
1. Create API token in Proxmox for a user with permissions: VM.Audit, VM.PowerMgmt, VM.Console, VM.Backup, VM.Snapshot, Datastore.Audit, Sys.Audit.
2. Store token in `../../secrets/pve-token.txt`.
3. cp assets/config.proxmox.example.yaml ../../secrets/config.proxmox.yaml && edit

## Usage
Load via skill system: read `SKILL.md` and use scripts in `scripts/`.

See [SKILL.md](SKILL.md) for triggers and workflows.

Outputs of this API can be lengthy/detailed (esp. full VM info)—specify 'brief' for Discord/mobile. Web/TUI handles full; Discord agents better w/ coding model (spawn code-agent via AGENTS.md policy) or summaries. AGENTS.md 'proxmox' alias triggers skill. For agent/skill tables, consider team-consensus skill.

### Examples
Run example scripts in `examples/`:
- `python examples/list_vms.py` - List all VMs/LXCs
- `python examples/vm_start.py node1 101` - Start VM 101 on node1
- `python examples/vm_snapshot.py node1 101 snap1 "My snapshot"` - Create snapshot for VM 101
- `python examples/vm_clone.py node1 101 102` - Clone VM 101 to 102

### API Endpoints (Initial Scope)
| Function | Method | Path |
| :--- | :--- | :--- |
| Cluster Status | GET | `/cluster/status` |
| Resources List | GET | `/cluster/resources` |
| Node Stats | GET | `/nodes/{node}/status` |
| VM/LXC List | GET | `/nodes/{node}/qemu` or `/nodes/{node}/lxc` |
| VM Status | GET | `/nodes/{node}/qemu/{vmid}/status/current` |
| Power Actions | POST | `/nodes/{node}/qemu/{vmid}/status/{start,stop,reset,shutdown,suspend,resume}` |
| Snapshots | POST/GET | `/nodes/{node}/qemu/{vmid}/snapshot` |
| Task Status | GET | `/nodes/{node}/tasks/{upid}/status` |

### Authentication
- Primary: API Tokens (`PVEAPIToken` header)
- Header: `Authorization: PVEAPIToken=USER@REALM!TOKENID=UUID`
- SSL: Verifies by default, configurable in config.yaml

### Async Handling
Operations return UPID; poll `/nodes/{node}/tasks/{upid}/status` until `status: stopped`.

### Safety
Destructive actions require confirmation.

## Dependencies
See `requirements.txt`.

## Testing
`pytest` in tests/ directory.

## Automation
- **CI/CD**: GitHub Actions for testing and linting on PRs/pushes.
- **Dependabot**: Automated dependency updates for Python packages and GitHub Actions.
- **CodeQL**: Security scanning enabled for vulnerability detection.

## Contributing
[CONTRIBUTING.md](CONTRIBUTING.md)

-Claive (AI agent)