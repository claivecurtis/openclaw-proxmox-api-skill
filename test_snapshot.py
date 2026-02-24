from scripts.client import load_client, ProxmoxAPIError

c = load_client()

# Test invalid name starting with number
try:
    result = c.vm_snapshot_create('example_node', 100, '123invalid')
    print("ERROR: Should have failed validation")
except ProxmoxAPIError as e:
    print("Correctly caught invalid name:", str(e))

# Test valid name
try:
    result = c.vm_snapshot_create('example_node', 100, 'valid_snapshot_123')
    print("Snapshot created, UPID:", result)
except ProxmoxAPIError as e:
    print("Failed to create valid snapshot:", str(e))