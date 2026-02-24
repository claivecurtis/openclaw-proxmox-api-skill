from scripts.client import load_client
c = load_client()
vms = c.list_vms()
vm126 = [vm for vm in vms if vm.get('vmid') == 126]
if vm126:
  vm = vm126[0]
  node = vm['node']
  print("VM 126 found:", vm['name'], "on", node, vm['type'], vm['status'])
  print("Status:", c.get_vm_status(node, 126))
  print("Config:", c.vm_config_get(node, 126))
else:
  print("VM 126 not found")
