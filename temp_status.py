from scripts.client import load_client
c = load_client()
print("Cluster Status:")
import pprint
pprint.pprint(c.cluster_status())
print("\nVMs:")
pprint.pprint(c.list_vms())
