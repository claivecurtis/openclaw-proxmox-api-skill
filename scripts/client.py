import requests
import json
import time
import logging
import os
from typing import Dict, List, Optional, Any
try:
    from pydantic import BaseModel, ValidationError
    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False
    BaseModel = object
    ValidationError = Exception

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Config validation
class ProxmoxConfig(BaseModel):
    host: str
    verify_ssl: bool = True
    token_path: Optional[str] = None
    timeout: int = 30

class ProxmoxAuthError(Exception):
    pass

class ProxmoxAPIError(Exception):
    pass

class TaskTimeoutError(Exception):
    pass

class ProxmoxClient:
    def __init__(self, host, token, verify_ssl=True):
        """
        Initialize the Proxmox API client.

        :param host: Proxmox host (e.g., 'pve.example.com')
        :param token: API token in 'user@realm!tokenid=secret' format
        :param verify_ssl: Whether to verify SSL certificates
        """
        self.host = host
        self.token = token
        self.verify_ssl = verify_ssl
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'PVEAPIToken={token}',
            'Content-Type': 'application/json'
        })
        # Test authentication
        try:
            self._get('/version')
            logger.info("Authentication successful")
        except requests.exceptions.RequestException as e:
            raise ProxmoxAuthError(f"Authentication failed: {e}")

    def _get(self, path, params=None):
        """
        Perform a GET request to the API.

        :param path: API path (e.g., '/cluster/resources')
        :param params: Optional query parameters
        :return: JSON response data
        """
        url = f"https://{self.host}:8006/api2/json{path}"
        try:
            resp = self.session.get(url, params=params, verify=self.verify_ssl, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout:
            raise ProxmoxAPIError("Request timed out")
        except requests.exceptions.SSLError:
            raise ProxmoxAPIError("SSL verification failed")
        except requests.exceptions.HTTPError as e:
            raise ProxmoxAPIError(f"HTTP {e.response.status_code}: {e.response.text}")
        except requests.exceptions.RequestException as e:
            raise ProxmoxAPIError(f"Request failed: {e}")

    def _post(self, path, data=None):
        """
        Perform a POST request to the API.

        :param path: API path
        :param data: JSON data to send
        :return: JSON response data
        """
        url = f"https://{self.host}:8006/api2/json{path}"
        try:
            resp = self.session.post(url, json=data, verify=self.verify_ssl, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout:
            raise ProxmoxAPIError("Request timed out")
        except requests.exceptions.SSLError:
            raise ProxmoxAPIError("SSL verification failed")
        except requests.exceptions.HTTPError as e:
            raise ProxmoxAPIError(f"HTTP {e.response.status_code}: {e.response.text}")
        except requests.exceptions.RequestException as e:
            raise ProxmoxAPIError(f"Request failed: {e}")

    def list_vms(self):
        """
        List all VMs (QEMU and LXC) in the cluster with pool information.

        :return: List of VM dictionaries
        """
        try:
            resources = self._get('/cluster/resources')
            vms = [r for r in resources['data'] if r['type'] in ('qemu', 'lxc')]
            # Add pool information
            pools = self.list_pools_with_members()
            pool_members = {}
            for pool in pools:
                for member in pool.get('members', []):
                    pool_members[f"{member['type']}/{member['vmid']}"] = pool['poolid']
            for vm in vms:
                vm['pool'] = pool_members.get(f"{vm['type']}/{vm['vmid']}", None)
            logger.info(f"Retrieved {len(vms)} VMs with pool info")
            return vms
        except ProxmoxAPIError as e:
            logger.error(f"Failed to list VMs: {e}")
            raise

    def vm_action(self, node, vmid, action, **kwargs):
        """
        Perform an action on a VM (e.g., start, stop, reboot).

        :param node: Node name
        :param vmid: VM ID
        :param action: Action (start, stop, reboot, etc.)
        :param kwargs: Additional parameters (e.g., timeout for shutdown)
        :return: UPID if asynchronous, None if synchronous
        """
        path = f'/nodes/{node}/qemu/{vmid}/status/{action}'
        try:
            result = self._post(path, kwargs)
            if 'data' in result and result['data']:
                upid = result['data']
                logger.info(f"VM {vmid} action '{action}' initiated, UPID: {upid}")
                return upid
            else:
                logger.info(f"VM {vmid} action '{action}' completed synchronously")
                return None
        except ProxmoxAPIError as e:
            logger.error(f"Failed to perform VM action '{action}' on {vmid}: {e}")
            raise

    def list_storage_pools(self):
        """
        List storage pools in the cluster.

        :return: List of storage pool dictionaries
        """
        try:
            resources = self._get('/cluster/resources')
            pools = [r for r in resources['data'] if r['type'] == 'storage']
            logger.info(f"Retrieved {len(pools)} storage pools")
            return pools
        except ProxmoxAPIError as e:
            logger.error(f"Failed to list storage pools: {e}")
            raise

    def storage_status(self, storage):
        """
        Get storage status.

        :param storage: Storage ID
        :return: Storage status dictionary
        """
        path = f'/storage/{storage}/status'
        try:
            status = self._get(path)
            logger.info(f"Retrieved status for storage {storage}")
            return status['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to get status for storage {storage}: {e}")
            raise

    def storage_content(self, storage, content_type=None):
        """
        List storage content.

        :param storage: Storage ID
        :param content_type: Optional content type filter (e.g., 'iso', 'vztmpl')
        :return: List of content items
        """
        path = f'/storage/{storage}/content'
        params = {}
        if content_type:
            params['content'] = content_type
        try:
            content = self._get(path, params)
            logger.info(f"Retrieved {len(content['data'])} content items from storage {storage}")
            return content['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to list content for storage {storage}: {e}")
            raise

    def storage_create(self, storage_id, config):
        """
        Create a new storage.

        :param storage_id: Storage ID
        :param config: Storage configuration dictionary
        :return: None
        """
        path = '/storage'
        data = {'id': storage_id, **config}
        try:
            self._post(path, data)
            logger.info(f"Storage {storage_id} created successfully")
        except ProxmoxAPIError as e:
            logger.error(f"Failed to create storage {storage_id}: {e}")
            raise

    def storage_delete(self, storage):
        """
        Delete a storage.

        :param storage: Storage ID
        :return: None
        """
        path = f'/storage/{storage}'
        try:
            self._post(path, {})  # DELETE is POST with empty data
            logger.info(f"Storage {storage} deleted successfully")
        except ProxmoxAPIError as e:
            logger.error(f"Failed to delete storage {storage}: {e}")
            raise

    def list_resource_pools(self):
        """
        List resource pools in the cluster.

        :return: List of resource pool dictionaries
        """
        try:
            pools = self._get('/pools')
            logger.info(f"Retrieved {len(pools['data'])} resource pools")
            return pools['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to list resource pools: {e}")
            raise

    def list_pools_with_members(self):
        """
        List resource pools with their members.

        :return: List of resource pool dictionaries with members
        """
        try:
            pools_summary = self._get('/pools')['data']
            pools = []
            for pool in pools_summary:
                pool_details = self._get(f'/pools/{pool["poolid"]}')['data']
                pools.append(pool_details)
            logger.info(f"Retrieved {len(pools)} resource pools with members")
            return pools
        except ProxmoxAPIError as e:
            logger.error(f"Failed to list resource pools with members: {e}")
            raise

    def create_resource_pool(self, poolid, comment=''):
        """
        Create a new resource pool.

        :param poolid: Pool ID
        :param comment: Optional comment
        :return: None
        """
        path = f'/pools'
        data = {'poolid': poolid}
        if comment:
            data['comment'] = comment
        try:
            self._post(path, data)
            logger.info(f"Resource pool '{poolid}' created successfully")
        except ProxmoxAPIError as e:
            logger.error(f"Failed to create resource pool '{poolid}': {e}")
            raise

    def pool_members(self, pool):
        """
        Get members of a resource pool.

        :param pool: Pool ID
        :return: List of pool members
        """
        try:
            pool_details = self._get(f'/pools/{pool}')
            members = pool_details['data'].get('members', [])
            logger.info(f"Retrieved {len(members)} members for pool '{pool}'")
            return members
        except ProxmoxAPIError as e:
            logger.error(f"Failed to get members for pool '{pool}': {e}")
            raise

    def pool_update(self, pool, config):
        """
        Update a resource pool.

        :param pool: Pool ID
        :param config: Configuration updates dictionary
        :return: None
        """
        path = f'/pools/{pool}'
        try:
            self._post(path, config)
            logger.info(f"Resource pool '{pool}' updated successfully")
        except ProxmoxAPIError as e:
            logger.error(f"Failed to update resource pool '{pool}': {e}")
            raise

    def pool_delete(self, pool):
        """
        Delete a resource pool.

        :param pool: Pool ID
        :return: None
        """
        path = f'/pools/{pool}'
        try:
            self._post(path, {})  # DELETE is POST with empty data
            logger.info(f"Resource pool '{pool}' deleted successfully")
        except ProxmoxAPIError as e:
            logger.error(f"Failed to delete resource pool '{pool}': {e}")
            raise

    # Cluster operations
    def cluster_status(self):
        """
        Get cluster status.

        :return: Cluster status data
        """
        return self._get('/cluster/status')

    def cluster_tasks(self):
        """
        Get cluster tasks.

        :return: List of cluster tasks
        """
        return self._get('/cluster/tasks')

    def cluster_logs(self, limit=None):
        """
        Get cluster logs.

        :param limit: Maximum number of log entries to return
        :return: Cluster log entries
        """
        params = {}
        if limit:
            params['limit'] = limit
        return self._get('/cluster/log', params)

    def cluster_backup(self):
        """
        Get cluster backup status.

        :return: Cluster backup information
        """
        return self._get('/cluster/backup')

    # Node operations
    def node_status(self, node):
        """
        Get node status.

        :param node: Node name
        :return: Node status data
        """
        return self._get(f'/nodes/{node}/status')

    def node_tasks(self, node):
        """
        Get node tasks.

        :param node: Node name
        :return: List of node tasks
        """
        return self._get(f'/nodes/{node}/tasks')

    def node_services(self, node):
        """
        Get node services.

        :param node: Node name
        :return: List of node services
        """
        return self._get(f'/nodes/{node}/services')

    def node_storage(self, node):
        """
        Get node storage.

        :param node: Node name
        :return: List of node storage
        """
        return self._get(f'/nodes/{node}/storage')

    def get_vm_status(self, node, vmid, is_lxc=False):
        """
        Get full status of a VM.

        :param node: Node name
        :param vmid: VM ID
        :param is_lxc: True if LXC, False for QEMU
        :return: VM status dictionary
        """
        vm_type = 'lxc' if is_lxc else 'qemu'
        path = f'/nodes/{node}/{vm_type}/{vmid}/status/current'
        try:
            status = self._get(path)
            logger.info(f"Retrieved status for {vm_type} {vmid}")
            return status['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to get status for {vm_type} {vmid}: {e}")
            raise

    def vm_create(self, node, vmid, config, is_lxc=False):
        """
        Create a new VM.

        :param node: Node name
        :param vmid: VM ID
        :param config: VM configuration dictionary
        :param is_lxc: True if LXC, False for QEMU
        :return: UPID of the creation task
        """
        vm_type = 'lxc' if is_lxc else 'qemu'
        path = f'/nodes/{node}/{vm_type}'
        data = {'vmid': vmid, **config}
        try:
            result = self._post(path, data)
            upid = result['data']
            logger.info(f"VM {vmid} creation initiated on node {node}, UPID: {upid}")
            return upid
        except ProxmoxAPIError as e:
            logger.error(f"Failed to create VM {vmid}: {e}")
            raise

    def vm_delete(self, node, vmid, is_lxc=False):
        """
        Delete a VM.

        :param node: Node name
        :param vmid: VM ID
        :param is_lxc: True if LXC, False for QEMU
        :return: UPID of the deletion task
        """
        vm_type = 'lxc' if is_lxc else 'qemu'
        path = f'/nodes/{node}/{vm_type}/{vmid}'
        try:
            result = self._post(path, {})  # DELETE is POST with empty data
            if 'data' in result:
                upid = result['data']
                logger.info(f"VM {vmid} deletion initiated on node {node}, UPID: {upid}")
                return upid
            else:
                logger.info(f"VM {vmid} deleted synchronously")
                return None
        except ProxmoxAPIError as e:
            logger.error(f"Failed to delete VM {vmid}: {e}")
            raise

    def vm_config_get(self, node, vmid, is_lxc=False):
        """
        Get VM configuration.

        :param node: Node name
        :param vmid: VM ID
        :param is_lxc: True if LXC, False for QEMU
        :return: VM configuration dictionary
        """
        vm_type = 'lxc' if is_lxc else 'qemu'
        path = f'/nodes/{node}/{vm_type}/{vmid}/config'
        try:
            config = self._get(path)
            logger.info(f"Retrieved config for {vm_type} {vmid}")
            return config['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to get config for {vm_type} {vmid}: {e}")
            raise

    def vm_config_set(self, node, vmid, config, is_lxc=False):
        """
        Update VM configuration.

        :param node: Node name
        :param vmid: VM ID
        :param config: Configuration updates dictionary
        :param is_lxc: True if LXC, False for QEMU
        :return: None
        """
        vm_type = 'lxc' if is_lxc else 'qemu'
        path = f'/nodes/{node}/{vm_type}/{vmid}/config'
        try:
            self._post(path, config)
            logger.info(f"Updated config for {vm_type} {vmid}")
        except ProxmoxAPIError as e:
            logger.error(f"Failed to update config for {vm_type} {vmid}: {e}")
            raise

    def poll_task(self, node, upid, timeout=300, poll_interval=5):
        """
        Poll a task until completion.

        :param node: Node name
        :param upid: Unique Process ID
        :param timeout: Timeout in seconds
        :param poll_interval: Polling interval in seconds
        :return: True if successful, raises exception otherwise
        """
        path = f'/nodes/{node}/tasks/{upid}/status'
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                status = self._get(path)
                task_status = status['data']['status']
                if task_status == 'stopped':
                    exitstatus = status['data'].get('exitstatus', 'OK')
                    if exitstatus == 'OK':
                        logger.info(f"Task {upid} completed successfully")
                        return True
                    else:
                        error_msg = f"Task {upid} failed with exitstatus: {exitstatus}"
                        logger.error(error_msg)
                        raise ProxmoxAPIError(error_msg)
                elif task_status == 'running':
                    logger.debug(f"Task {upid} still running...")
                else:
                    logger.warning(f"Task {upid} in unknown status: {task_status}")
                time.sleep(poll_interval)
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 404:
                    raise ProxmoxAPIError(f"Task {upid} not found")
                else:
                    raise
            except ProxmoxAPIError:
                raise
        raise TaskTimeoutError(f"Task {upid} timed out after {timeout} seconds")

class PBSClient(ProxmoxClient):
    """
    Client for Proxmox Backup Server (PBS) API.
    Inherits from ProxmoxClient but uses port 8007.
    """
    def __init__(self, host, token, verify_ssl=True):
        """
        Initialize the PBS API client.

        :param host: PBS host (e.g., 'pbs.example.com')
        :param token: API token
        :param verify_ssl: Whether to verify SSL certificates
        """
        self.host = host
        self.token = token
        self.verify_ssl = verify_ssl
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'PVEAPIToken={token}',
            'Content-Type': 'application/json'
        })
        # Test authentication
        try:
            self._get('/version')
            logger.info("PBS Authentication successful")
        except requests.exceptions.RequestException as e:
            raise ProxmoxAuthError(f"PBS Authentication failed: {e}")

    def _get(self, path, params=None):
        """
        Perform a GET request to the PBS API.

        :param path: API path
        :param params: Optional query parameters
        :return: JSON response data
        """
        url = f"https://{self.host}:8007/api2/json{path}"
        try:
            resp = self.session.get(url, params=params, verify=self.verify_ssl, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout:
            raise ProxmoxAPIError("PBS Request timed out")
        except requests.exceptions.SSLError:
            raise ProxmoxAPIError("PBS SSL verification failed")
        except requests.exceptions.HTTPError as e:
            raise ProxmoxAPIError(f"PBS HTTP {e.response.status_code}: {e.response.text}")
        except requests.exceptions.RequestException as e:
            raise ProxmoxAPIError(f"PBS Request failed: {e}")

    def _post(self, path, data=None):
        """
        Perform a POST request to the PBS API.

        :param path: API path
        :param data: JSON data to send
        :return: JSON response data
        """
        url = f"https://{self.host}:8007/api2/json{path}"
        try:
            resp = self.session.post(url, json=data, verify=self.verify_ssl, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout:
            raise ProxmoxAPIError("PBS Request timed out")
        except requests.exceptions.SSLError:
            raise ProxmoxAPIError("PBS SSL verification failed")
        except requests.exceptions.HTTPError as e:
            raise ProxmoxAPIError(f"PBS HTTP {e.response.status_code}: {e.response.text}")
        except requests.exceptions.RequestException as e:
            raise ProxmoxAPIError(f"PBS Request failed: {e}")

    def list_datastores(self):
        """
        List datastores on the PBS server.

        :return: List of datastore dictionaries
        """
        try:
            datastores = self._get('/config/datastore')
            logger.info(f"Retrieved {len(datastores['data'])} datastores")
            return datastores['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to list datastores: {e}")
            raise

    def backup_vm(self, datastore, vmid, node, backup_type='vm', **kwargs):
        """
        Initiate a backup of a VM to PBS.

        :param datastore: PBS datastore
        :param vmid: VM ID
        :param node: Node name
        :param backup_type: Backup type ('vm', 'ct')
        :param kwargs: Additional parameters
        :return: UPID of the backup task
        """
        path = f'/datastore/{datastore}/backup'
        data = {
            'id': f'{node}/{vmid}',
            'type': backup_type,
            **kwargs
        }
        try:
            result = self._post(path, data)
            upid = result['data']
            logger.info(f"Backup of {backup_type} {vmid} to datastore {datastore} initiated, UPID: {upid}")
            return upid
        except ProxmoxAPIError as e:
            logger.error(f"Failed to backup {backup_type} {vmid}: {e}")
            raise


class VM:
    """
    Wrapper class for VM operations.
    """
    def __init__(self, client: ProxmoxClient):
        self.client = client

    def list(self, node=None):
        """
        List VMs. If node is specified, list VMs on that node.
        """
        if node:
            # For specific node, get from node resources
            resources = self.client._get(f'/nodes/{node}/qemu')
            vms = resources['data']
            for vm in vms:
                vm['node'] = node
            return vms
        else:
            return self.client.list_vms()

    def status(self, vmid, node, is_lxc=False):
        return self.client.get_vm_status(node, vmid, is_lxc)

    def start(self, vmid, node, is_lxc=False):
        return self.client.vm_action(node, vmid, 'start', is_lxc=is_lxc)

    def stop(self, vmid, node, is_lxc=False):
        return self.client.vm_action(node, vmid, 'stop', is_lxc=is_lxc)

    def reboot(self, vmid, node, is_lxc=False):
        return self.client.vm_action(node, vmid, 'reboot', is_lxc=is_lxc)

    def shutdown(self, vmid, node, is_lxc=False, timeout=None):
        kwargs = {}
        if timeout:
            kwargs['timeout'] = timeout
        return self.client.vm_action(node, vmid, 'shutdown', **kwargs, is_lxc=is_lxc)

    def create(self, node, vmid, config, is_lxc=False):
        return self.client.vm_create(node, vmid, config, is_lxc)

    def delete(self, node, vmid, is_lxc=False):
        return self.client.vm_delete(node, vmid, is_lxc)

    def config_get(self, node, vmid, is_lxc=False):
        return self.client.vm_config_get(node, vmid, is_lxc)

    def config_set(self, node, vmid, config, is_lxc=False):
        return self.client.vm_config_set(node, vmid, config, is_lxc)


class Storage:
    """
    Wrapper class for Storage operations.
    """
    def __init__(self, client: ProxmoxClient):
        self.client = client

    def list(self):
        return self.client.list_storage_pools()

    def status(self, storage):
        return self.client.storage_status(storage)

    def content(self, storage, content_type=None):
        return self.client.storage_content(storage, content_type)

    def create(self, storage_id, config):
        return self.client.storage_create(storage_id, config)

    def delete(self, storage):
        return self.client.storage_delete(storage)


class Pool:
    """
    Wrapper class for Pool operations.
    """
    def __init__(self, client: ProxmoxClient):
        self.client = client

    def list(self):
        return self.client.list_resource_pools()

    def members(self, pool):
        return self.client.pool_members(pool)

    def create(self, poolid, comment=''):
        return self.client.create_resource_pool(poolid, comment)

    def update(self, pool, config):
        return self.client.pool_update(pool, config)

    def delete(self, pool):
        return self.client.pool_delete(pool)


class Cluster:
    """
    Wrapper class for Cluster operations.
    """
    def __init__(self, client: ProxmoxClient):
        self.client = client

    def status(self):
        return self.client.cluster_status()

    def tasks(self):
        return self.client.cluster_tasks()

    def logs(self, limit=None):
        return self.client.cluster_logs(limit)

    def backup(self):
        return self.client.cluster_backup()


class Node:
    """
    Wrapper class for Node operations.
    """
    def __init__(self, client: ProxmoxClient):
        self.client = client

    def status(self, node):
        return self.client.node_status(node)

    def tasks(self, node):
        return self.client.node_tasks(node)

    def services(self, node):
        return self.client.node_services(node)

    def storage(self, node):
        return self.client.node_storage(node)


# Task polling helper
def poll_task_until_complete(client: ProxmoxClient, node: str, upid: str, timeout: int = 300, poll_interval: int = 5) -> bool:
    """
    Poll a task until completion and return success status.

    :param client: ProxmoxClient instance
    :param node: Node name
    :param upid: Unique Process ID
    :param timeout: Timeout in seconds
    :param poll_interval: Polling interval in seconds
    :return: True if successful, raises exception otherwise
    """
    return client.poll_task(node, upid, timeout, poll_interval)

# Utility function to load client from config
def load_client():
    workspace = os.getenv('OPENCLAW_WORKSPACE', os.path.dirname(os.path.dirname(__file__)))
    config_path = os.path.join(workspace, 'secrets', 'config.proxmox.yaml')
    token_path = os.path.join(workspace, 'secrets', 'pve-token.txt')

    # Load config
    import yaml
    with open(config_path, 'r') as f:
        raw_config = yaml.safe_load(f)

    # Validate config
    if PYDANTIC_AVAILABLE:
        try:
            config = ProxmoxConfig(**raw_config['proxmox'])
        except ValidationError as e:
            raise ValueError(f"Invalid config: {e}")
    else:
        config = ProxmoxConfig()
        config.host = raw_config['proxmox'].get('host')
        config.verify_ssl = raw_config['proxmox'].get('verify_ssl', True)

    # Load token
    with open(token_path, 'r') as f:
        token = f.read().strip()

    return ProxmoxClient(config.host, token, config.verify_ssl)