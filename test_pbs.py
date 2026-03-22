import yaml
from scripts.client import PBSClient, PBSProxyClient, ProxmoxClient

# Load config
with open('secrets/config.proxmox.yaml', 'r') as f:
    config = yaml.safe_load(f)

# Get cluster config
cluster = config['clusters'][0]
pbs_config = cluster['pbs']

print("Testing PBS connectivity post-firewall...")

# Test direct PBS
try:
    pbs_client = PBSClient(
        user=pbs_config['user'],
        token_id=pbs_config['token_id'],
        token_secret=pbs_config['token_secret'],
        endpoint=pbs_config['endpoint'],
        port=pbs_config['port'],
        verify_ssl=pbs_config['verify_ssl']
    )
    version = pbs_client._get('/version')
    print("Direct PBS version:", version)
except Exception as e:
    print("Direct PBS failed:", str(e))

# Test PVE proxy PBS
try:
    proxy_client = PBSProxyClient(
        pve_host=cluster['host'],
        pve_token=cluster['token'],
        pbs_name=pbs_config['name'],
        verify_ssl=cluster['verify_ssl']
    )
    version = proxy_client._get('/version')
    print("Proxy PBS version:", version)
except Exception as e:
    print("Proxy PBS failed:", str(e))

# List PBS storages from PVE
try:
    pve_client = ProxmoxClient(
        host=cluster['host'],
        token=cluster['token'],
        verify_ssl=cluster['verify_ssl'],
        port=cluster['port']
    )
    storages = pve_client.list_storage_pools()
    pbs_storages = [s for s in storages if s.get('type') == 'pbs']
    print("PBS storages:", pbs_storages)
except Exception as e:
    print("PVE storage list failed:", str(e))