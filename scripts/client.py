import requests
import json
import time
import logging
import os

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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
        List all VMs (QEMU and LXC) in the cluster.

        :return: List of VM dictionaries
        """
        try:
            resources = self._get('/cluster/resources')
            vms = [r for r in resources['data'] if r['type'] in ('qemu', 'lxc')]
            logger.info(f"Retrieved {len(vms)} VMs")
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

# Utility function to load client from config (assumes assets/config.yaml and secrets/pve-token.txt exist)
def load_client():
    config_path = os.path.join(os.path.dirname(__file__), '..', 'assets', 'config.yaml')
    token_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'secrets', 'pve-token.txt')
    
    # Load config
    import yaml
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    # Load token
    with open(token_path, 'r') as f:
        token = f.read().strip()
    
    host = config['proxmox'].get('host')
    verify_ssl = config['proxmox'].get('verify_ssl', True)
    
    return ProxmoxClient(host, token, verify_ssl)