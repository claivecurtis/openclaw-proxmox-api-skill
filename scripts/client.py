import requests
import json
import time
import logging
import os
import re
import threading
from typing import Dict, List, Optional, Any
try:
    from pydantic import BaseModel, ValidationError
    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False
    BaseModel = object
    ValidationError = Exception

# Global settings lock for thread safety
settings_lock = threading.Lock()

# Default settings
DEFAULT_SETTINGS = {
    "naming_convention": "aiagent-snap-{number:04d}",
    "next_snap_number": 1
}

# Load settings with thread lock and global defaults
def load_settings(interactive=False):
    settings_path = os.path.join(os.path.dirname(__file__), '..', 'settings.json')
    with settings_lock:
        if os.path.exists(settings_path):
            with open(settings_path, 'r') as f:
                return json.load(f)
        else:
            if interactive:
                default = DEFAULT_SETTINGS["naming_convention"]
                user_input = input(f"Naming convention? (default {default}) [input] ").strip()
                convention = user_input if user_input else default
                settings = {"naming_convention": convention, "next_snap_number": DEFAULT_SETTINGS["next_snap_number"]}
                with open(settings_path, 'w') as f:
                    json.dump(settings, f, indent=2)
                return settings
            else:
                settings = DEFAULT_SETTINGS.copy()
                with open(settings_path, 'w') as f:
                    json.dump(settings, f, indent=2)
                return settings

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Validation regexes
NAME_REGEX = re.compile(r'^[a-zA-Z][a-zA-Z0-9_-]*$')  # snapshot names
VMID_REGEX = re.compile(r'^\d+$')  # VMID: digits only
NODE_REGEX = re.compile(r'^[a-zA-Z0-9_-]+$')  # node names: alphanumeric, hyphens, underscores
STORAGE_REGEX = re.compile(r'^[a-zA-Z0-9_-]+$')  # storage names: alphanumeric, hyphens, underscores

def validate_vmid(vmid):
    """Validate VMID: must be digits, >0"""
    if not VMID_REGEX.match(str(vmid)):
        raise ValueError(f"Invalid VMID '{vmid}': must be a positive integer")
    vmid_int = int(vmid)
    if vmid_int <= 0:
        raise ValueError(f"Invalid VMID '{vmid}': must be > 0")

def validate_node(node):
    """Validate node name"""
    if not NODE_REGEX.match(node):
        raise ValueError(f"Invalid node name '{node}': must contain only letters, numbers, hyphens, underscores")

def validate_storage(storage):
    """Validate storage name"""
    if not STORAGE_REGEX.match(storage):
        raise ValueError(f"Invalid storage name '{storage}': must contain only letters, numbers, hyphens, underscores")

# Config validation
class ProxmoxConfig(BaseModel):
    host: str
    verify_ssl: bool = True
    token_path: Optional[str] = None
    timeout: int = 30
    auto_poll: bool = True

class ProxmoxAuthError(Exception):
    pass

class ProxmoxAPIError(Exception):
    pass

class TaskTimeoutError(Exception):
    pass

class ProxmoxClient:
    def __init__(self, host, token, verify_ssl=True, timeout=30, auto_poll=True):
        """
        Initialize the Proxmox API client.

        :param host: Proxmox host (e.g., 'pve.example.com')
        :param token: API token in 'user@realm!tokenid=secret' format
        :param verify_ssl: Whether to verify SSL certificates
        :param timeout: Request timeout in seconds
        :param auto_poll: Default auto-polling for async tasks
        """
        self.host = host
        self.token = token
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self.auto_poll = auto_poll
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'PVEAPIToken={token}',
            'Content-Type': 'application/json'
        })
        # Test authentication
        try:
            self._get('/version')
            logger.info("Authentication successful")
        except Exception as e:
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
            resp = self.session.get(url, params=params, verify=self.verify_ssl, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout:
            raise ProxmoxAPIError("Request timed out")
        except requests.exceptions.SSLError:
            raise ProxmoxAPIError("SSL verification failed")
        except requests.exceptions.HTTPError as e:
            raise ProxmoxAPIError(f"HTTP {e.response.status_code}: {e.response.text}")
        except Exception as e:
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
            resp = self.session.post(url, json=data, verify=self.verify_ssl, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout:
            raise ProxmoxAPIError("Request timed out")
        except requests.exceptions.SSLError:
            raise ProxmoxAPIError("SSL verification failed")
        except requests.exceptions.HTTPError as e:
            raise ProxmoxAPIError(f"HTTP {e.response.status_code}: {e.response.text}")
        except Exception as e:
            raise ProxmoxAPIError(f"Request failed: {e}")

    def _delete(self, path):
        """
        Perform a DELETE request to the API.

        :param path: API path
        :return: JSON response data
        """
        url = f"https://{self.host}:8006/api2/json{path}"
        try:
            resp = self.session.delete(url, verify=self.verify_ssl, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout:
            raise ProxmoxAPIError("Request timed out")
        except requests.exceptions.SSLError:
            raise ProxmoxAPIError("SSL verification failed")
        except requests.exceptions.HTTPError as e:
            raise ProxmoxAPIError(f"HTTP {e.response.status_code}: {e.response.text}")
        except Exception as e:
            raise ProxmoxAPIError(f"Request failed: {e}")

    def list_vms(self):
        """
        List all VMs (QEMU and LXC) in the cluster with pool information.

        :return: List of VM dictionaries
        """
        try:
            # First, try cluster-level resources
            resources = self._get('/cluster/resources')
            nodes = [r for r in resources['data'] if r['type'] == 'node']
            vms = [r for r in resources['data'] if r['type'] in ('qemu', 'lxc')]
            # If no VMs from cluster, fall back to node-specific queries
            if not vms:
                logger.info("No VMs found via /cluster/resources, trying node-specific endpoints")
                vms = []
                for node in nodes:
                    node_name = node['node']
                    try:
                        qemu_resources = self._get(f'/nodes/{node_name}/qemu')
                        for vm in qemu_resources['data']:
                            vm['node'] = node_name
                            vm['type'] = 'qemu'
                            vms.append(vm)
                    except ProxmoxAPIError:
                        logger.debug(f"No permission to list QEMU on node {node_name}")
                    try:
                        lxc_resources = self._get(f'/nodes/{node_name}/lxc')
                        for vm in lxc_resources['data']:
                            vm['node'] = node_name
                            vm['type'] = 'lxc'
                            vms.append(vm)
                    except ProxmoxAPIError:
                        logger.debug(f"No permission to list LXC on node {node_name}")
            # Add pool information
            try:
                pools = self.list_pools_with_members()
                pool_members = {}
                for pool in pools:
                    for member in pool.get('members', []):
                        pool_members[f"{member['type']}/{member['vmid']}"] = pool['poolid']
                for vm in vms:
                    vmid = vm.get('vmid', vm.get('id'))
                    vm['pool'] = pool_members.get(f"{vm['type']}/{vmid}", None)
            except ProxmoxAPIError:
                logger.debug("Failed to get pool information")
            logger.info(f"Retrieved {len(vms)} VMs with pool info")
            return vms
        except ProxmoxAPIError as e:
            logger.error(f"Failed to list VMs: {e}")
            raise

    def vm_action(self, node, vmid, action, vm_type='qemu', auto_poll=None, **kwargs):
        """
        Perform an action on a VM or LXC (e.g., start, stop, reboot).

        :param node: Node name
        :param vmid: VM ID
        :param action: Action (start, stop, reboot, etc.)
        :param vm_type: 'qemu' or 'lxc'
        :param auto_poll: If True, poll the task until completion and return status dict. Defaults to config value.
        :param kwargs: Additional parameters (e.g., timeout for shutdown)
        :return: UPID if asynchronous and not auto_poll, status dict if auto_poll, None if synchronous
        """
        if auto_poll is None:
            auto_poll = self.auto_poll
        path = f'/nodes/{node}/{vm_type}/{vmid}/status/{action}'
        try:
            result = self._post(path, kwargs)
            if 'data' in result and result['data']:
                upid = result['data']
                logger.info(f"{vm_type.upper()} {vmid} action '{action}' initiated, UPID: {upid}")
                if auto_poll:
                    poll_result = self.poll_task(node, upid)
                    return {'upid': upid, **poll_result}
                return upid
            else:
                logger.info(f"{vm_type.upper()} {vmid} action '{action}' completed synchronously")
                return None
        except ProxmoxAPIError as e:
            logger.error(f"Failed to perform {vm_type.upper()} action '{action}' on {vmid}: {e}")
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
        validate_storage(storage_id)
        # Idempotency check: ensure storage does not already exist
        try:
            self._get(f'/storage/{storage_id}')
            raise ProxmoxAPIError(f"Storage '{storage_id}' already exists")
        except ProxmoxAPIError as e:
            if 'HTTP 404' not in str(e):
                raise
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

    # Advanced storage operations
    def storage_upload(self, storage, file_path, content):
        """
        Upload file to storage.

        :param storage: Storage ID
        :param file_path: File path in storage
        :param content: File content (bytes or string)
        :return: Upload result
        """
        path = f'/storage/{storage}/upload'
        # Note: This might require multipart/form-data, adjust if needed
        data = {'content': content, 'filename': file_path}
        try:
            result = self._post(path, data)
            logger.info(f"Uploaded file {file_path} to storage {storage}")
            return result['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to upload file to storage {storage}: {e}")
            raise

    def storage_download(self, storage, file_path):
        """
        Download file from storage.

        :param storage: Storage ID
        :param file_path: File path in storage
        :return: File content
        """
        path = f'/storage/{storage}/content/{file_path}'
        try:
            content = self._get(path)
            logger.info(f"Downloaded file {file_path} from storage {storage}")
            return content['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to download file from storage {storage}: {e}")
            raise

    def storage_rrd(self, storage, **kwargs):
        """
        Get storage RRD data.

        :param storage: Storage ID
        :param kwargs: Additional parameters (e.g., timeframe='hour')
        :return: RRD data
        """
        path = f'/storage/{storage}/rrd'
        try:
            rrd = self._get(path, kwargs)
            logger.info(f"Retrieved RRD data for storage {storage}")
            return rrd['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to get RRD data for storage {storage}: {e}")
            raise

    def storage_scan(self, storage, auto_poll=None):
        """
        Scan storage for content.

        :param storage: Storage ID
        :param auto_poll: If True, poll the task until completion and return status dict. Defaults to config value.
        :return: UPID if not auto_poll, status dict if auto_poll
        """
        if auto_poll is None:
            auto_poll = self.auto_poll
        path = f'/storage/{storage}/scan'
        try:
            result = self._post(path, {})
            upid = result['data']
            logger.info(f"Scanned storage {storage}, UPID: {upid}")
            if auto_poll:
                poll_result = self.poll_cluster_task(upid)
                return {'upid': upid, **poll_result}
            return upid
        except ProxmoxAPIError as e:
            logger.error(f"Failed to scan storage {storage}: {e}")
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
                if not isinstance(pool, dict) or 'poolid' not in pool:
                    continue
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
        # Idempotency check: ensure pool does not already exist
        try:
            self._get(f'/pools/{poolid}')
            raise ProxmoxAPIError(f"Resource pool '{poolid}' already exists")
        except ProxmoxAPIError as e:
            if 'HTTP 404' not in str(e):
                raise
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

    def cluster_backup(self):
        """
        Get cluster backup status.

        :return: Cluster backup information
        """
        return self._get('/cluster/backup')

    # Advanced cluster operations
    def cluster_firewall(self):
        """
        Get cluster firewall rules.

        :return: Cluster firewall rules
        """
        path = '/cluster/firewall/rules'
        try:
            rules = self._get(path)
            logger.info("Retrieved cluster firewall rules")
            return rules['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to get cluster firewall rules: {e}")
            raise

    def cluster_ha(self, **kwargs):
        """
        Manage cluster HA.

        :param kwargs: Additional parameters (e.g., command='status')
        :return: HA information
        """
        path = '/cluster/ha'
        try:
            ha = self._get(path, kwargs)
            logger.info("Retrieved cluster HA status")
            return ha['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to get cluster HA status: {e}")
            raise

    def cluster_ha_groups(self):
        """
        List HA groups.

        :return: HA groups
        """
        path = '/cluster/ha/groups'
        try:
            groups = self._get(path)
            logger.info(f"Retrieved {len(groups['data'])} HA groups")
            return groups['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to get HA groups: {e}")
            raise

    def cluster_ha_resources(self):
        """
        List HA resources.

        :return: HA resources
        """
        path = '/cluster/ha/resources'
        try:
            resources = self._get(path)
            logger.info(f"Retrieved {len(resources['data'])} HA resources")
            return resources['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to get HA resources: {e}")
            raise

    def cluster_resources(self, **kwargs):
        """
        Get cluster resources.

        :param kwargs: Additional parameters (e.g., type='vm')
        :return: Cluster resources
        """
        path = '/cluster/resources'
        try:
            resources = self._get(path, kwargs)
            logger.info("Retrieved cluster resources")
            return resources['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to get cluster resources: {e}")
            raise

    def cluster_nextid(self):
        """
        Get next available VMID.

        :return: Next VMID
        """
        path = '/cluster/nextid'
        try:
            nextid = self._get(path)
            logger.info("Retrieved next VMID")
            return nextid['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to get next VMID: {e}")
            raise

    def cluster_rrd(self, timeframe='hour'):
        """
        Get RRD data for cluster.

        :param timeframe: Timeframe
        :return: RRD data
        """
        path = '/cluster/rrd'
        params = {'timeframe': timeframe}
        try:
            rrd = self._get(path, params)
            logger.info("Retrieved cluster RRD data")
            return rrd['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to get cluster RRD data: {e}")
            raise

    def cluster_logs(self, limit=50):
        """
        Get cluster logs.

        :param limit: Number of log entries
        :return: Log entries
        """
        path = '/cluster/log'
        params = {}
        if limit is not None:
            params['limit'] = limit
        try:
            logs = self._get(path, params)
            logger.info(f"Retrieved {len(logs['data'])} cluster log entries")
            return logs['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to get cluster logs: {e}")
            raise

    # Access control operations
    def user_list(self):
        """
        List users.

        :return: List of users
        """
        path = '/access/users'
        try:
            users = self._get(path)
            logger.info("Retrieved list of users")
            return users['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to list users: {e}")
            raise

    def user_create(self, userid, config):
        """
        Create a user.

        :param userid: User ID (e.g., 'user@pve')
        :param config: User configuration dictionary
        :return: None
        """
        path = '/access/users'
        data = {'userid': userid, **config}
        try:
            self._post(path, data)
            logger.info(f"User {userid} created successfully")
        except ProxmoxAPIError as e:
            logger.error(f"Failed to create user {userid}: {e}")
            raise

    def user_delete(self, userid):
        """
        Delete a user.

        :param userid: User ID
        :return: None
        """
        path = f'/access/users/{userid}'
        try:
            self._post(path, {})  # DELETE via POST
            logger.info(f"User {userid} deleted successfully")
        except ProxmoxAPIError as e:
            logger.error(f"Failed to delete user {userid}: {e}")
            raise

    def group_list(self):
        """
        List groups.

        :return: List of groups
        """
        path = '/access/groups'
        try:
            groups = self._get(path)
            logger.info("Retrieved list of groups")
            return groups['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to list groups: {e}")
            raise

    def group_create(self, groupid):
        """
        Create a group.

        :param groupid: Group ID
        :return: None
        """
        path = '/access/groups'
        data = {'groupid': groupid}
        try:
            self._post(path, data)
            logger.info(f"Group {groupid} created successfully")
        except ProxmoxAPIError as e:
            logger.error(f"Failed to create group {groupid}: {e}")
            raise

    def role_list(self):
        """
        List roles.

        :return: List of roles
        """
        path = '/access/roles'
        try:
            roles = self._get(path)
            logger.info("Retrieved list of roles")
            return roles['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to list roles: {e}")
            raise

    def role_create(self, roleid, privs):
        """
        Create a role.

        :param roleid: Role ID
        :param privs: Privileges list or string
        :return: None
        """
        path = '/access/roles'
        data = {'roleid': roleid, 'privs': privs}
        try:
            self._post(path, data)
            logger.info(f"Role {roleid} created successfully")
        except ProxmoxAPIError as e:
            logger.error(f"Failed to create role {roleid}: {e}")
            raise

    def permission_list(self):
        """
        List permissions.

        :return: List of permissions
        """
        path = '/access/permissions'
        try:
            perms = self._get(path)
            logger.info("Retrieved list of permissions")
            return perms['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to list permissions: {e}")
            raise

    def domain_list(self):
        """
        List authentication domains.

        :return: List of domains
        """
        path = '/access/domains'
        try:
            domains = self._get(path)
            logger.info("Retrieved list of domains")
            return domains['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to list domains: {e}")
            raise

    def token_create(self, user, tokenid):
        """
        Create an API token.

        :param user: User ID
        :param tokenid: Token ID
        :return: Token info
        """
        path = f'/access/users/{user}/token/{tokenid}'
        try:
            token = self._post(path, {})
            logger.info(f"Token {tokenid} created for user {user}")
            return token['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to create token {tokenid} for user {user}: {e}")
            raise

    def token_delete(self, user, tokenid):
        """
        Delete an API token.

        :param user: User ID
        :param tokenid: Token ID
        :return: None
        """
        path = f'/access/users/{user}/token/{tokenid}'
        try:
            self._post(path, {})  # DELETE via POST
            logger.info(f"Token {tokenid} deleted for user {user}")
        except ProxmoxAPIError as e:
            logger.error(f"Failed to delete token {tokenid} for user {user}: {e}")
            raise

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

    # Node advanced operations
    def node_firewall(self, node):
        """
        Get node firewall rules.

        :param node: Node name
        :return: Firewall rules
        """
        path = f'/nodes/{node}/firewall/rules'
        try:
            rules = self._get(path)
            logger.info(f"Retrieved firewall rules for node {node}")
            return rules['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to get firewall rules for node {node}: {e}")
            raise

    def node_dns(self, node):
        """
        Get node DNS settings.

        :param node: Node name
        :return: DNS settings
        """
        path = f'/nodes/{node}/dns'
        try:
            dns = self._get(path)
            logger.info(f"Retrieved DNS settings for node {node}")
            return dns['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to get DNS settings for node {node}: {e}")
            raise

    def node_time(self, node):
        """
        Get node time.

        :param node: Node name
        :return: Node time
        """
        path = f'/nodes/{node}/time'
        try:
            time_info = self._get(path)
            logger.info(f"Retrieved time for node {node}")
            return time_info['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to get time for node {node}: {e}")
            raise

    def node_version(self, node):
        """
        Get node version.

        :param node: Node name
        :return: Node version
        """
        path = f'/nodes/{node}/version'
        try:
            version = self._get(path)
            logger.info(f"Retrieved version for node {node}")
            return version['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to get version for node {node}: {e}")
            raise

    def node_apt(self, node, **kwargs):
        """
        Manage node APT packages.

        :param node: Node name
        :param kwargs: Additional parameters (e.g., command='update')
        :return: APT operation result
        """
        path = f'/nodes/{node}/apt'
        try:
            result = self._get(path, kwargs)
            logger.info(f"APT operation on node {node}")
            return result['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed APT operation on node {node}: {e}")
            raise

    def node_subscription(self, node):
        """
        Get node subscription.

        :param node: Node name
        :return: Subscription info
        """
        path = f'/nodes/{node}/subscription'
        try:
            sub = self._get(path)
            logger.info(f"Retrieved subscription for node {node}")
            return sub['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to get subscription for node {node}: {e}")
            raise

    def node_certificates(self, node):
        """
        Get node certificates.

        :param node: Node name
        :return: Certificate info
        """
        path = f'/nodes/{node}/certificates'
        try:
            certs = self._get(path)
            logger.info(f"Retrieved certificates for node {node}")
            return certs['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to get certificates for node {node}: {e}")
            raise

    def node_syslog(self, node, **kwargs):
        """
        Get node syslog.

        :param node: Node name
        :param kwargs: Additional parameters (e.g., limit=50)
        :return: Syslog entries
        """
        path = f'/nodes/{node}/syslog'
        try:
            syslog = self._get(path, kwargs)
            logger.info(f"Retrieved syslog for node {node}")
            return syslog['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to get syslog for node {node}: {e}")
            raise

    def node_vncshell(self, node):
        """
        Get VNC shell for node.

        :param node: Node name
        :return: VNC shell data
        """
        path = f'/nodes/{node}/vncshell'
        try:
            shell = self._post(path, {})
            logger.info(f"VNC shell created for node {node}")
            return shell['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to create VNC shell for node {node}: {e}")
            raise

    def node_spiceshell(self, node):
        """
        Get SPICE shell for node.

        :param node: Node name
        :return: SPICE shell data
        """
        path = f'/nodes/{node}/spiceshell'
        try:
            shell = self._post(path, {})
            logger.info(f"SPICE shell created for node {node}")
            return shell['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to create SPICE shell for node {node}: {e}")
            raise

    def node_migrateall(self, node, target, auto_poll=True):
        """
        Migrate all VMs/containers from node.

        :param node: Source node name
        :param target: Target node name
        :param auto_poll: If True, poll the task until completion and return status dict
        :return: UPID if not auto_poll, status dict if auto_poll
        """
        path = f'/nodes/{node}/migrateall'
        data = {'target': target}
        try:
            result = self._post(path, data)
            upid = result['data']
            logger.info(f"Migrate all from node {node} to {target} initiated, UPID: {upid}")
            if auto_poll:
                poll_result = self.poll_task(node, upid)
                return {'upid': upid, **poll_result}
            return upid
        except ProxmoxAPIError as e:
            logger.error(f"Failed to migrate all from node {node}: {e}")
            raise

    def node_startall(self, node, auto_poll=True):
        """
        Start all VMs/containers on node.

        :param node: Node name
        :param auto_poll: If True, poll the task until completion and return status dict
        :return: UPID if not auto_poll, status dict if auto_poll
        """
        path = f'/nodes/{node}/startall'
        try:
            result = self._post(path, {})
            upid = result['data']
            logger.info(f"Start all on node {node} initiated, UPID: {upid}")
            if auto_poll:
                poll_result = self.poll_task(node, upid)
                return {'upid': upid, **poll_result}
            return upid
        except ProxmoxAPIError as e:
            logger.error(f"Failed to start all on node {node}: {e}")
            raise

    def node_stopall(self, node, auto_poll=True):
        """
        Stop all VMs/containers on node.

        :param node: Node name
        :param auto_poll: If True, poll the task until completion and return status dict
        :return: UPID if not auto_poll, status dict if auto_poll
        """
        path = f'/nodes/{node}/stopall'
        try:
            result = self._post(path, {})
            upid = result['data']
            logger.info(f"Stop all on node {node} initiated, UPID: {upid}")
            if auto_poll:
                poll_result = self.poll_task(node, upid)
                return {'upid': upid, **poll_result}
            return upid
        except ProxmoxAPIError as e:
            logger.error(f"Failed to stop all on node {node}: {e}")
            raise

    def node_ceph(self, node, **kwargs):
        """
        Manage Ceph on node.

        :param node: Node name
        :param kwargs: Additional parameters (e.g., command='status')
        :return: Ceph operation result
        """
        path = f'/nodes/{node}/ceph'
        try:
            result = self._get(path, kwargs)
            logger.info(f"Ceph operation on node {node}")
            return result['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed Ceph operation on node {node}: {e}")
            raise

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

    def vm_create(self, node, vmid, config, is_lxc=False, auto_poll=None):
        """
        Create a new VM.

        :param node: Node name
        :param vmid: VM ID
        :param config: VM configuration dictionary
        :param is_lxc: True if LXC, False for QEMU
        :param auto_poll: If True, poll the task until completion and return status dict. Defaults to config value.
        :return: UPID if not auto_poll, status dict if auto_poll
        """
        if auto_poll is None:
            auto_poll = self.auto_poll
        validate_node(node)
        validate_vmid(vmid)
        # Idempotency check: ensure VM does not already exist
        try:
            self.get_vm_status(node, vmid, is_lxc)
            raise ProxmoxAPIError(f"VM {vmid} already exists on node {node}")
        except Exception as e:
            if 'HTTP 404' not in str(e):
                raise  # re-raise if not "not found"
        vm_type = 'lxc' if is_lxc else 'qemu'
        path = f'/nodes/{node}/{vm_type}'
        data = {'vmid': vmid, **config}
        try:
            result = self._post(path, data)
            upid = result['data']
            logger.info(f"VM {vmid} creation initiated on node {node}, UPID: {upid}")
            if auto_poll:
                poll_result = self.poll_task(node, upid)
                return {'upid': upid, **poll_result}
            return upid
        except ProxmoxAPIError as e:
            logger.error(f"Failed to create VM {vmid}: {e}")
            raise

    def vm_delete(self, node, vmid, is_lxc=False, auto_poll=None):
        """
        Delete a VM.

        :param node: Node name
        :param vmid: VM ID
        :param is_lxc: True if LXC, False for QEMU
        :param auto_poll: If True, poll the task until completion and return status dict. Defaults to config value.
        :return: UPID if not auto_poll and async, status dict if auto_poll, None if sync or not exists
        """
        if auto_poll is None:
            auto_poll = self.auto_poll
        validate_node(node)
        validate_vmid(vmid)
        # Idempotency check: ensure VM exists
        try:
            self.get_vm_status(node, vmid, is_lxc)
        except Exception as e:
            if 'HTTP 404' in str(e):
                logger.info(f"VM {vmid} does not exist on node {node}, skipping delete")
                return None
            else:
                raise
        vm_type = 'lxc' if is_lxc else 'qemu'
        path = f'/nodes/{node}/{vm_type}/{vmid}'
        try:
            result = self._post(path, {})  # DELETE is POST with empty data
            if 'data' in result:
                upid = result['data']
                logger.info(f"VM {vmid} deletion initiated on node {node}, UPID: {upid}")
                if auto_poll:
                    poll_result = self.poll_task(node, upid)
                    return {'upid': upid, **poll_result}
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

    # Advanced VM operations
    def vm_clone(self, node, vmid, newid, config=None, is_lxc=False, auto_poll=None):
        """
        Clone a VM.

        :param node: Source node name
        :param vmid: Source VM ID
        :param newid: New VM ID
        :param config: Optional configuration overrides
        :param is_lxc: True if LXC, False for QEMU
        :param auto_poll: If True, poll the task until completion and return status dict. Defaults to config value.
        :return: UPID if not auto_poll, status dict if auto_poll
        """
        if auto_poll is None:
            auto_poll = self.auto_poll
        vm_type = 'lxc' if is_lxc else 'qemu'
        path = f'/nodes/{node}/{vm_type}/{vmid}/clone'
        data = {'newid': newid}
        if config:
            data.update(config)
        try:
            result = self._post(path, data)
            upid = result['data']
            logger.info(f"Clone of {vm_type} {vmid} to {newid} initiated, UPID: {upid}")
            if auto_poll:
                poll_result = self.poll_task(node, upid)
                return {'upid': upid, **poll_result}
            return upid
        except ProxmoxAPIError as e:
            logger.error(f"Failed to clone {vm_type} {vmid}: {e}")
            raise

    def vm_snapshot_create(self, node, vmid, snapname=None, description=None, is_lxc=False, change_number=None, interactive=False, auto_poll=None):
        """
        Create a VM snapshot.

        :param node: Node name
        :param vmid: VM ID
        :param snapname: Snapshot name (if provided, validated: starts with letter, only letters/numbers/hyphens/underscores)
        :param description: Optional description
        :param is_lxc: True if LXC, False for QEMU
        :param change_number: Optional change number for custom naming
        :param interactive: If True, prompt for confirmation of generated name
        :param auto_poll: If True, poll the task until completion and return status dict. Defaults to config value.
        :return: UPID if not auto_poll, status dict if auto_poll
        """
        if auto_poll is None:
            auto_poll = self.auto_poll
        validate_node(node)
        validate_vmid(vmid)
        settings = load_settings(interactive=interactive)
        if snapname is None:
            if change_number is not None:
                snapname = f"aiagent-snap-{change_number}"
            else:
                number = settings['next_snap_number']
                snapname = settings['naming_convention'].format(number=number)
                # Increment next number
                settings['next_snap_number'] = number + 1
                settings_path = os.path.join(os.path.dirname(__file__), '..', 'settings.json')
                with open(settings_path, 'w') as f:
                    json.dump(settings, f, indent=2)
                if interactive:
                    logger.info(f"Generated snapshot name: {snapname}. Proceeding with creation.")
        # Pre-validate snapshot name
        if not NAME_REGEX.match(snapname):
            raise ProxmoxAPIError(f"Invalid snapshot name '{snapname}': must start with a letter and contain only letters, numbers, hyphens, and underscores.")
        # Idempotency check: ensure snapshot does not already exist
        try:
            existing_snaps = self.vm_snapshot_list(node, vmid, is_lxc)
        except Exception:
            existing_snaps = []
        existing_names = [s['name'] for s in existing_snaps]
        if snapname in existing_names:
            raise ProxmoxAPIError(f"Snapshot '{snapname}' already exists for VM {vmid}")
        vm_type = 'lxc' if is_lxc else 'qemu'
        path = f'/nodes/{node}/{vm_type}/{vmid}/snapshot'
        data = {'snapname': snapname}
        if description:
            data['description'] = description
        try:
            result = self._post(path, data)
            upid = result['data']
            logger.info(f"Snapshot '{snapname}' for {vm_type} {vmid} initiated, UPID: {upid}")
            if auto_poll:
                poll_result = self.poll_task(node, upid)
                return {'upid': upid, **poll_result}
            return upid
        except ProxmoxAPIError as e:
            logger.error(f"Failed to create snapshot for {vm_type} {vmid}: {e}")
            raise

    def vm_snapshot_list(self, node, vmid, is_lxc=False):
        """
        List VM snapshots.

        :param node: Node name
        :param vmid: VM ID
        :param is_lxc: True if LXC, False for QEMU
        :return: List of snapshots
        """
        vm_type = 'lxc' if is_lxc else 'qemu'
        path = f'/nodes/{node}/{vm_type}/{vmid}/snapshot'
        try:
            snapshots = self._get(path)
            logger.info(f"Retrieved {len(snapshots['data'])} snapshots for {vm_type} {vmid}")
            return snapshots['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to list snapshots for {vm_type} {vmid}: {e}")
            raise

    def vm_snapshot_rollback(self, node, vmid, snapname, is_lxc=False):
        """
        Rollback VM to a snapshot.

        :param node: Node name
        :param vmid: VM ID
        :param snapname: Snapshot name
        :param is_lxc: True if LXC, False for QEMU
        :return: UPID of the rollback task
        """
        vm_type = 'lxc' if is_lxc else 'qemu'
        path = f'/nodes/{node}/{vm_type}/{vmid}/snapshot/{snapname}/rollback'
        try:
            result = self._post(path, {})
            upid = result['data']
            logger.info(f"Rollback of {vm_type} {vmid} to snapshot '{snapname}' initiated, UPID: {upid}")
            return upid
        except ProxmoxAPIError as e:
            logger.error(f"Failed to rollback {vm_type} {vmid} to snapshot '{snapname}': {e}")
            raise

    def vm_snapshot_delete(self, node, vmid, snapname, is_lxc=False, auto_poll=None):
        """
        Delete a VM snapshot.

        :param node: Node name
        :param vmid: VM ID
        :param snapname: Snapshot name
        :param is_lxc: True if LXC, False for QEMU
        :param auto_poll: If True, poll the task until completion and return status dict. Defaults to config value.
        :return: UPID if not auto_poll, status dict if auto_poll
        """
        if auto_poll is None:
            auto_poll = self.auto_poll
        vm_type = 'lxc' if is_lxc else 'qemu'
        path = f'/nodes/{node}/{vm_type}/{vmid}/snapshot/{snapname}'
        try:
            result = self._delete(path)
            upid = result['data']
            logger.info(f"Deletion of snapshot '{snapname}' for {vm_type} {vmid} initiated, UPID: {upid}")
            if auto_poll:
                poll_result = self.poll_task(node, upid)
                return {'upid': upid, **poll_result}
            return upid
        except ProxmoxAPIError as e:
            logger.error(f"Failed to delete snapshot '{snapname}' for {vm_type} {vmid}: {e}")
            raise

    def vm_migrate(self, node, vmid, target_node, online=True, is_lxc=False, auto_poll=None):
        """
        Migrate VM to another node.

        :param node: Source node name
        :param vmid: VM ID
        :param target_node: Target node name
        :param online: True for online migration, False for offline
        :param is_lxc: True if LXC, False for QEMU
        :param auto_poll: If True, poll the task until completion and return status dict. Defaults to config value.
        :return: UPID if not auto_poll, status dict if auto_poll
        """
        if auto_poll is None:
            auto_poll = self.auto_poll
        vm_type = 'lxc' if is_lxc else 'qemu'
        path = f'/nodes/{node}/{vm_type}/{vmid}/migrate'
        data = {'target': target_node, 'online': int(online)}
        try:
            result = self._post(path, data)
            upid = result['data']
            logger.info(f"Migration of {vm_type} {vmid} from {node} to {target_node} initiated, UPID: {upid}")
            if auto_poll:
                poll_result = self.poll_task(node, upid)
                return {'upid': upid, **poll_result}
            return upid
        except ProxmoxAPIError as e:
            logger.error(f"Failed to migrate {vm_type} {vmid}: {e}")
            raise

    def vm_resize(self, node, vmid, disk, size, is_lxc=False):
        """
        Resize VM disk.

        :param node: Node name
        :param vmid: VM ID
        :param disk: Disk identifier (e.g., 'scsi0')
        :param size: New size (e.g., '+10G')
        :param is_lxc: True if LXC, False for QEMU
        :return: None
        """
        vm_type = 'lxc' if is_lxc else 'qemu'
        path = f'/nodes/{node}/{vm_type}/{vmid}/resize'
        data = {'disk': disk, 'size': size}
        try:
            self._post(path, data)
            logger.info(f"Resized disk '{disk}' for {vm_type} {vmid} to {size}")
        except ProxmoxAPIError as e:
            logger.error(f"Failed to resize disk for {vm_type} {vmid}: {e}")
            raise

    def vm_move_volume(self, node, vmid, volume, storage, is_lxc=False, auto_poll=None):
        """
        Move VM volume to different storage.

        :param node: Node name
        :param vmid: VM ID
        :param volume: Volume identifier
        :param storage: Target storage ID
        :param is_lxc: True if LXC, False for QEMU
        :param auto_poll: If True, poll the task until completion and return status dict. Defaults to config value.
        :return: UPID if not auto_poll, status dict if auto_poll
        """
        if auto_poll is None:
            auto_poll = self.auto_poll
        vm_type = 'lxc' if is_lxc else 'qemu'
        path = f'/nodes/{node}/{vm_type}/{vmid}/{"move_disk" if vm_type == "qemu" else "move_volume"}'
        data = {'disk' if vm_type == 'qemu' else 'volume': volume, 'storage': storage}
        try:
            result = self._post(path, data)
            upid = result['data']
            logger.info(f"Move of volume '{volume}' for {vm_type} {vmid} to storage '{storage}' initiated, UPID: {upid}")
            if auto_poll:
                poll_result = self.poll_task(node, upid)
                return {'upid': upid, **poll_result}
            return upid
        except ProxmoxAPIError as e:
            logger.error(f"Failed to move volume for {vm_type} {vmid}: {e}")
            raise

    def vm_template(self, node, vmid, is_lxc=False):
        """
        Convert VM to template.

        :param node: Node name
        :param vmid: VM ID
        :param is_lxc: True if LXC, False for QEMU
        :return: None
        """
        vm_type = 'lxc' if is_lxc else 'qemu'
        path = f'/nodes/{node}/{vm_type}/{vmid}/template'
        try:
            self._post(path, {})
            logger.info(f"Converted {vm_type} {vmid} to template")
        except ProxmoxAPIError as e:
            logger.error(f"Failed to convert {vm_type} {vmid} to template: {e}")
            raise

    def vm_vncproxy(self, node, vmid, is_lxc=False):
        """
        Get VNC proxy for VM.

        :param node: Node name
        :param vmid: VM ID
        :param is_lxc: True if LXC, False for QEMU
        :return: VNC proxy data
        """
        vm_type = 'lxc' if is_lxc else 'qemu'
        path = f'/nodes/{node}/{vm_type}/{vmid}/vncproxy'
        try:
            proxy = self._post(path, {})
            logger.info(f"Retrieved VNC proxy for {vm_type} {vmid}")
            return proxy['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to get VNC proxy for {vm_type} {vmid}: {e}")
            raise

    def vm_spiceproxy(self, node, vmid, is_lxc=False):
        """
        Get SPICE proxy for VM.

        :param node: Node name
        :param vmid: VM ID
        :param is_lxc: True if LXC, False for QEMU
        :return: SPICE proxy data
        """
        vm_type = 'lxc' if is_lxc else 'qemu'
        path = f'/nodes/{node}/{vm_type}/{vmid}/spiceproxy'
        try:
            proxy = self._post(path, {})
            logger.info(f"Retrieved SPICE proxy for {vm_type} {vmid}")
            return proxy['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to get SPICE proxy for {vm_type} {vmid}: {e}")
            raise

    def vm_monitor(self, node, vmid, command, is_lxc=False):
        """
        Send monitor command to VM.

        :param node: Node name
        :param vmid: VM ID
        :param command: Monitor command
        :param is_lxc: True if LXC, False for QEMU
        :return: Monitor response
        """
        vm_type = 'lxc' if is_lxc else 'qemu'
        path = f'/nodes/{node}/{vm_type}/{vmid}/monitor'
        data = {'command': command}
        try:
            response = self._post(path, data)
            logger.info(f"Sent monitor command to {vm_type} {vmid}")
            return response['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to send monitor command to {vm_type} {vmid}: {e}")
            raise

    def vm_firewall(self, node, vmid, is_lxc=False):
        """
        Get VM firewall rules.

        :param node: Node name
        :param vmid: VM ID
        :param is_lxc: True if LXC, False for QEMU
        :return: Firewall rules
        """
        vm_type = 'lxc' if is_lxc else 'qemu'
        path = f'/nodes/{node}/{vm_type}/{vmid}/firewall/rules'
        try:
            rules = self._get(path)
            logger.info(f"Retrieved firewall rules for {vm_type} {vmid}")
            return rules['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to get firewall rules for {vm_type} {vmid}: {e}")
            raise

    def vm_rrd(self, node, vmid, timeframe='hour', is_lxc=False):
        """
        Get RRD data for VM.

        :param node: Node name
        :param vmid: VM ID
        :param timeframe: Timeframe (e.g., 'hour', 'day', 'week', 'month', 'year')
        :param is_lxc: True if LXC, False for QEMU
        :return: RRD data
        """
        vm_type = 'lxc' if is_lxc else 'qemu'
        path = f'/nodes/{node}/{vm_type}/{vmid}/rrd'
        params = {'timeframe': timeframe}
        try:
            rrd = self._get(path, params)
            logger.info(f"Retrieved RRD data for {vm_type} {vmid}")
            return rrd['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to get RRD data for {vm_type} {vmid}: {e}")
            raise

    def poll_task(self, node, upid, timeout=300, poll_interval=5):
        """
        Poll a node task until completion.

        :param node: Node name
        :param upid: Unique Process ID
        :param timeout: Timeout in seconds
        :param poll_interval: Initial polling interval in seconds (with backoff)
        :return: Dict with 'success', 'exitstatus', 'status'
        """
        path = f'/nodes/{node}/tasks/{upid}/status'
        start_time = time.time()
        current_interval = poll_interval
        while time.time() - start_time < timeout:
            try:
                status = self._get(path)
                task_status = status['data']['status']
                exitstatus = status['data'].get('exitstatus', 'OK')
                if task_status == 'stopped':
                    success = exitstatus == 'OK'
                    if success:
                        logger.info(f"Task {upid} completed successfully")
                    else:
                        logger.error(f"Task {upid} failed with exitstatus: {exitstatus}")
                    return {'success': success, 'exitstatus': exitstatus, 'status': 'stopped'}
                elif task_status == 'running':
                    logger.debug(f"Task {upid} still running...")
                else:
                    logger.warning(f"Task {upid} in unknown status: {task_status}")
                time.sleep(min(current_interval, 30))
                current_interval *= 1.5
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 404:
                    raise ProxmoxAPIError(f"Task {upid} not found")
                else:
                    raise
            except ProxmoxAPIError:
                raise
        raise TaskTimeoutError(f"Task {upid} timed out after {timeout} seconds")

    def poll_cluster_task(self, upid, timeout=300, poll_interval=5):
        """
        Poll a cluster task until completion.

        :param upid: Unique Process ID
        :param timeout: Timeout in seconds
        :param poll_interval: Initial polling interval in seconds (with backoff)
        :return: Dict with 'success', 'exitstatus', 'status'
        """
        path = f'/cluster/tasks/{upid}/status'
        start_time = time.time()
        current_interval = poll_interval
        while time.time() - start_time < timeout:
            try:
                status = self._get(path)
                task_status = status['data']['status']
                exitstatus = status['data'].get('exitstatus', 'OK')
                if task_status == 'stopped':
                    success = exitstatus == 'OK'
                    if success:
                        logger.info(f"Cluster task {upid} completed successfully")
                    else:
                        logger.error(f"Cluster task {upid} failed with exitstatus: {exitstatus}")
                    return {'success': success, 'exitstatus': exitstatus, 'status': 'stopped'}
                elif task_status == 'running':
                    logger.debug(f"Cluster task {upid} still running...")
                else:
                    logger.warning(f"Cluster task {upid} in unknown status: {task_status}")
                time.sleep(min(current_interval, 30))
                current_interval *= 1.5
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 404:
                    raise ProxmoxAPIError(f"Cluster task {upid} not found")
                else:
                    raise
            except ProxmoxAPIError:
                raise
        raise TaskTimeoutError(f"Cluster task {upid} timed out after {timeout} seconds")

    # Phase 3: Access Control
    def user_create(self, userid, config):
        """
        Create a user.

        :param userid: User ID (e.g., 'user@pve')
        :param config: User configuration dictionary
        :return: None
        """
        path = '/access/users'
        data = {'userid': userid, **config}
        try:
            self._post(path, data)
            logger.info(f"User '{userid}' created successfully")
        except ProxmoxAPIError as e:
            logger.error(f"Failed to create user '{userid}': {e}")
            raise

    def user_delete(self, userid):
        """
        Delete a user.

        :param userid: User ID
        :return: None
        """
        path = f'/access/users/{userid}'
        try:
            self._post(path, {})  # DELETE via POST
            logger.info(f"User '{userid}' deleted successfully")
        except ProxmoxAPIError as e:
            logger.error(f"Failed to delete user '{userid}': {e}")
            raise

    def group_list(self):
        """
        List groups.

        :return: List of groups
        """
        try:
            groups = self._get('/access/groups')
            logger.info(f"Retrieved {len(groups['data'])} groups")
            return groups['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to list groups: {e}")
            raise

    def group_create(self, groupid):
        """
        Create a group.

        :param groupid: Group ID
        :return: None
        """
        path = '/access/groups'
        data = {'groupid': groupid}
        try:
            self._post(path, data)
            logger.info(f"Group '{groupid}' created successfully")
        except ProxmoxAPIError as e:
            logger.error(f"Failed to create group '{groupid}': {e}")
            raise

    def role_list(self):
        """
        List roles.

        :return: List of roles
        """
        try:
            roles = self._get('/access/roles')
            logger.info(f"Retrieved {len(roles['data'])} roles")
            return roles['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to list roles: {e}")
            raise

    def role_create(self, roleid, privs):
        """
        Create a role.

        :param roleid: Role ID
        :param privs: List of privileges
        :return: None
        """
        path = '/access/roles'
        data = {'roleid': roleid, 'privs': ','.join(privs)}
        try:
            self._post(path, data)
            logger.info(f"Role '{roleid}' created successfully")
        except ProxmoxAPIError as e:
            logger.error(f"Failed to create role '{roleid}': {e}")
            raise

    def permission_list(self):
        """
        List permissions.

        :return: List of permissions
        """
        try:
            perms = self._get('/access/permissions')
            logger.info(f"Retrieved permissions")
            return perms['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to list permissions: {e}")
            raise

    def domain_list(self):
        """
        List authentication domains.

        :return: List of domains
        """
        try:
            domains = self._get('/access/domains')
            logger.info(f"Retrieved {len(domains['data'])} domains")
            return domains['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to list domains: {e}")
            raise

    def token_create(self, user, tokenid):
        """
        Create an API token.

        :param user: User ID
        :param tokenid: Token ID
        :return: Token data
        """
        path = f'/access/users/{user}/token'
        data = {'tokenid': tokenid}
        try:
            result = self._post(path, data)
            logger.info(f"Token '{tokenid}' created for user '{user}'")
            return result['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to create token '{tokenid}' for user '{user}': {e}")
            raise

    def token_delete(self, user, tokenid):
        """
        Delete an API token.

        :param user: User ID
        :param tokenid: Token ID
        :return: None
        """
        path = f'/access/users/{user}/token/{tokenid}'
        try:
            self._post(path, {})  # DELETE via POST
            logger.info(f"Token '{tokenid}' deleted for user '{user}'")
        except ProxmoxAPIError as e:
            logger.error(f"Failed to delete token '{tokenid}' for user '{user}': {e}")
            raise

    # Phase 3: Advanced Storage Operations
    def storage_upload(self, storage, filename, content):
        """
        Upload a file to storage.

        :param storage: Storage ID
        :param filename: Filename
        :param content: File content (bytes)
        :return: None
        """
        # Note: Upload requires multipart/form-data, not JSON
        # This is a placeholder; actual implementation may vary
        path = f'/nodes/{self.host}/storage/{storage}/upload'  # Assuming local node
        files = {'filename': (filename, content)}
        try:
            resp = self.session.post(f"https://{self.host}:8006/api2/json{path}", files=files, verify=self.verify_ssl, timeout=30)
            resp.raise_for_status()
            logger.info(f"File '{filename}' uploaded to storage '{storage}'")
        except requests.exceptions.RequestException as e:
            raise ProxmoxAPIError(f"Failed to upload file: {e}")

    def storage_download(self, storage, volid):
        """
        Download a file from storage.

        :param storage: Storage ID
        :param volid: Volume ID
        :return: File content (bytes)
        """
        path = f'/storage/{storage}/content/{volid}'
        try:
            resp = self.session.get(f"https://{self.host}:8006/api2/json{path}", verify=self.verify_ssl, timeout=30)
            resp.raise_for_status()
            logger.info(f"Downloaded volume '{volid}' from storage '{storage}'")
            return resp.content
        except requests.exceptions.RequestException as e:
            raise ProxmoxAPIError(f"Failed to download volume: {e}")

    def storage_rrd(self, storage, timeframe='hour'):
        """
        Get storage RRD data.

        :param storage: Storage ID
        :param timeframe: Timeframe (e.g., 'hour', 'day')
        :return: RRD data
        """
        path = f'/storage/{storage}/rrd'
        params = {'timeframe': timeframe}
        try:
            rrd = self._get(path, params)
            logger.info(f"Retrieved RRD data for storage '{storage}'")
            return rrd['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to get RRD data for storage '{storage}': {e}")
            raise

    def storage_scan(self, storage):
        """
        Scan storage for content.

        :param storage: Storage ID
        :return: UPID of scan task
        """
        path = f'/storage/{storage}/scan'
        try:
            result = self._post(path, {})
            upid = result['data']
            logger.info(f"Scan initiated for storage '{storage}', UPID: {upid}")
            return upid
        except ProxmoxAPIError as e:
            logger.error(f"Failed to scan storage '{storage}': {e}")
            raise

    # Phase 3: Advanced Cluster Operations
    def cluster_firewall(self):
        """
        Get cluster firewall rules.

        :return: Firewall rules
        """
        try:
            rules = self._get('/cluster/firewall/rules')
            logger.info("Retrieved cluster firewall rules")
            return rules['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to get cluster firewall rules: {e}")
            raise

    def cluster_ha(self):
        """
        Get HA status.

        :return: HA status
        """
        try:
            ha = self._get('/cluster/ha/status')
            logger.info("Retrieved HA status")
            return ha['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to get HA status: {e}")
            raise

    def cluster_resources(self, **kwargs):
        """
        List cluster resources.

        :param kwargs: Additional parameters (e.g., type='vm')
        :return: List of resources
        """
        try:
            resources = self._get('/cluster/resources', params=kwargs if kwargs else None)
            logger.info(f"Retrieved {len(resources['data'])} cluster resources")
            return resources['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to list cluster resources: {e}")
            raise

    def cluster_nextid(self):
        """
        Get next available VMID.

        :return: Next VMID
        """
        try:
            nextid = self._get('/cluster/nextid')
            logger.info(f"Next available VMID: {nextid['data']}")
            return nextid['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to get next VMID: {e}")
            raise

    # Phase 3: Node Advanced Operations
    def node_firewall(self, node):
        """
        Get node firewall rules.

        :param node: Node name
        :return: Firewall rules
        """
        path = f'/nodes/{node}/firewall/rules'
        try:
            rules = self._get(path)
            logger.info(f"Retrieved firewall rules for node '{node}'")
            return rules['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to get firewall rules for node '{node}': {e}")
            raise

    def node_dns(self, node):
        """
        Get node DNS settings.

        :param node: Node name
        :return: DNS settings
        """
        path = f'/nodes/{node}/dns'
        try:
            dns = self._get(path)
            logger.info(f"Retrieved DNS settings for node '{node}'")
            return dns['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to get DNS settings for node '{node}': {e}")
            raise

    def node_time(self, node):
        """
        Get node time settings.

        :param node: Node name
        :return: Time settings
        """
        path = f'/nodes/{node}/time'
        try:
            time_data = self._get(path)
            logger.info(f"Retrieved time settings for node '{node}'")
            return time_data['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to get time settings for node '{node}': {e}")
            raise

    def node_version(self, node):
        """
        Get node software version.

        :param node: Node name
        :return: Version info
        """
        path = f'/nodes/{node}/version'
        try:
            version = self._get(path)
            logger.info(f"Retrieved version for node '{node}'")
            return version['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to get version for node '{node}': {e}")
            raise

    def node_apt(self, node):
        """
        Get node APT package status.

        :param node: Node name
        :return: APT status
        """
        path = f'/nodes/{node}/apt'
        try:
            apt = self._get(path)
            logger.info(f"Retrieved APT status for node '{node}'")
            return apt['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to get APT status for node '{node}': {e}")
            raise

    def node_subscription(self, node):
        """
        Get node subscription info.

        :param node: Node name
        :return: Subscription info
        """
        path = f'/nodes/{node}/subscription'
        try:
            sub = self._get(path)
            logger.info(f"Retrieved subscription info for node '{node}'")
            return sub['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to get subscription info for node '{node}': {e}")
            raise

    def node_syslog(self, node, limit=None):
        """
        Get node syslog.

        :param node: Node name
        :param limit: Number of lines to retrieve
        :return: Syslog entries
        """
        path = f'/nodes/{node}/syslog'
        params = {}
        if limit:
            params['limit'] = limit
        try:
            syslog = self._get(path, params)
            logger.info(f"Retrieved syslog for node '{node}'")
            return syslog['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to get syslog for node '{node}': {e}")
            raise

    def node_rrd(self, node, timeframe='hour', **kwargs):
        """
        Get node RRD data.

        :param node: Node name
        :param timeframe: Timeframe (default 'hour')
        :param kwargs: Additional parameters
        :return: RRD data
        """
        path = f'/nodes/{node}/rrd'
        params = {'timeframe': timeframe, **kwargs}
        try:
            rrd = self._get(path, params)
            logger.info(f"Retrieved RRD data for node '{node}'")
            return rrd['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to get RRD data for node '{node}': {e}")
            raise

    def node_vncshell(self, node):
        """
        Get VNC shell for node.

        :param node: Node name
        :return: VNC shell data
        """
        path = f'/nodes/{node}/vncshell'
        try:
            shell = self._post(path, {})
            logger.info(f"Retrieved VNC shell for node '{node}'")
            return shell['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to get VNC shell for node '{node}': {e}")
            raise

    def node_spiceshell(self, node):
        """
        Get SPICE shell for node.

        :param node: Node name
        :return: SPICE shell data
        """
        path = f'/nodes/{node}/spiceshell'
        try:
            shell = self._post(path, {})
            logger.info(f"Retrieved SPICE shell for node '{node}'")
            return shell['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to get SPICE shell for node '{node}': {e}")
            raise

    def node_migrateall(self, node, target_node):
        """
        Migrate all VMs/containers from node.

        :param node: Source node
        :param target_node: Target node
        :return: UPID of migration task
        """
        path = f'/nodes/{node}/migrateall'
        data = {'target': target_node}
        try:
            result = self._post(path, data)
            upid = result['data']
            logger.info(f"Migration of all VMs from '{node}' to '{target_node}' initiated, UPID: {upid}")
            return upid
        except ProxmoxAPIError as e:
            logger.error(f"Failed to migrate all VMs from '{node}': {e}")
            raise

    def node_startall(self, node):
        """
        Start all VMs/containers on node.

        :param node: Node name
        :return: UPID of start task
        """
        path = f'/nodes/{node}/startall'
        try:
            result = self._post(path, {})
            upid = result['data']
            logger.info(f"Start all VMs on '{node}' initiated, UPID: {upid}")
            return upid
        except ProxmoxAPIError as e:
            logger.error(f"Failed to start all VMs on '{node}': {e}")
            raise

    def node_stopall(self, node):
        """
        Stop all VMs/containers on node.

        :param node: Node name
        :return: UPID of stop task
        """
        path = f'/nodes/{node}/stopall'
        try:
            result = self._post(path, {})
            upid = result['data']
            logger.info(f"Stop all VMs on '{node}' initiated, UPID: {upid}")
            return upid
        except ProxmoxAPIError as e:
            logger.error(f"Failed to stop all VMs on '{node}': {e}")
            raise

    def node_ceph(self, node):
        """
        Get Ceph status for node.

        :param node: Node name
        :return: Ceph status
        """
        path = f'/nodes/{node}/ceph'
        try:
            ceph = self._get(path)
            logger.info(f"Retrieved Ceph status for node '{node}'")
            return ceph['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to get Ceph status for node '{node}': {e}")
            raise

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

    def _put(self, path, data=None):
        """
        Perform a PUT request to the PBS API.

        :param path: API path
        :param data: JSON data to send
        :return: JSON response data
        """
        url = f"https://{self.host}:8007/api2/json{path}"
        try:
            resp = self.session.put(url, json=data, verify=self.verify_ssl, timeout=30)
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

    def _delete(self, path):
        """
        Perform a DELETE request to the PBS API.

        :param path: API path
        :return: JSON response data or empty dict
        """
        url = f"https://{self.host}:8007/api2/json{path}"
        try:
            resp = self.session.delete(url, verify=self.verify_ssl, timeout=30)
            resp.raise_for_status()
            return resp.json() if resp.text else {}
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

    def create_datastore(self, name, config):
        """
        Create a new datastore on PBS.

        :param name: Datastore name
        :param config: Datastore configuration dict
        :return: None
        """
        path = f'/config/datastore/{name}'
        try:
            self._post(path, config)
            logger.info(f"Datastore {name} created")
        except ProxmoxAPIError as e:
            logger.error(f"Failed to create datastore {name}: {e}")
            raise

    def list_backups(self, datastore):
        """
        List backups in a datastore.

        :param datastore: Datastore name
        :return: List of backup dictionaries
        """
        try:
            backups = self._get(f'/datastore/{datastore}')
            logger.info(f"Retrieved {len(backups['data'])} backups from {datastore}")
            return backups['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to list backups in {datastore}: {e}")
            raise

    def restore_backup(self, datastore, backup_id, target):
        """
        Restore a backup from PBS.

        :param datastore: Datastore name
        :param backup_id: Backup ID
        :param target: Restore target config
        :return: UPID of the restore task
        """
        path = f'/datastore/{datastore}/restore/{backup_id}'
        try:
            result = self._post(path, target)
            upid = result['data']
            logger.info(f"Restore of backup {backup_id} from {datastore} initiated, UPID: {upid}")
            return upid
        except ProxmoxAPIError as e:
            logger.error(f"Failed to restore backup {backup_id}: {e}")
            raise

    def delete_backup(self, datastore, backup_id):
        """
        Delete a backup from PBS.

        :param datastore: Datastore name
        :param backup_id: Backup ID
        :return: None
        """
        path = f'/datastore/{datastore}/backup/{backup_id}'
        try:
            self._delete(path)
            logger.info(f"Backup {backup_id} deleted from {datastore}")
        except ProxmoxAPIError as e:
            logger.error(f"Failed to delete backup {backup_id}: {e}")
            raise

    def list_tasks(self):
        """
        List PBS tasks.

        :return: List of task dictionaries
        """
        try:
            tasks = self._get('/tasks')
            logger.info(f"Retrieved {len(tasks['data'])} tasks")
            return tasks['data']
        except ProxmoxAPIError as e:
            logger.error(f"Failed to list tasks: {e}")
            raise

    def sync_datastore(self, datastore, remote):
        """
        Sync datastore with remote.

        :param datastore: Datastore name
        :param remote: Remote config
        :return: UPID of the sync task
        """
        path = f'/datastore/{datastore}/sync'
        try:
            result = self._post(path, remote)
            upid = result['data']
            logger.info(f"Sync of datastore {datastore} initiated, UPID: {upid}")
            return upid
        except ProxmoxAPIError as e:
            logger.error(f"Failed to sync datastore {datastore}: {e}")
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
            vms = self.client.list_vms()
            return [vm for vm in vms if vm['type'] == 'qemu']

    def status(self, node, vmid, is_lxc=False):
        return self.client.get_vm_status(node, vmid, is_lxc)

    def start(self, node, vmid, is_lxc=False):
        vm_type = 'lxc' if is_lxc else 'qemu'
        return self.client.vm_action(node, vmid, 'start', vm_type=vm_type)

    def stop(self, node, vmid, is_lxc=False):
        vm_type = 'lxc' if is_lxc else 'qemu'
        return self.client.vm_action(node, vmid, 'stop', vm_type=vm_type)

    def reboot(self, node, vmid, is_lxc=False):
        vm_type = 'lxc' if is_lxc else 'qemu'
        return self.client.vm_action(node, vmid, 'reboot', vm_type=vm_type)

    def shutdown(self, node, vmid, is_lxc=False, timeout=None):
        vm_type = 'lxc' if is_lxc else 'qemu'
        kwargs = {}
        if timeout:
            kwargs['timeout'] = timeout
        return self.client.vm_action(node, vmid, 'shutdown', vm_type=vm_type, **kwargs)

    def create(self, node, vmid, config, is_lxc=False):
        return self.client.vm_create(node, vmid, config, is_lxc)

    def delete(self, node, vmid, is_lxc=False):
        return self.client.vm_delete(node, vmid, is_lxc)

    def config_get(self, node, vmid, is_lxc=False):
        return self.client.vm_config_get(node, vmid, is_lxc)

    def config_set(self, node, vmid, config, is_lxc=False):
        return self.client.vm_config_set(node, vmid, config, is_lxc)

    def clone(self, node, vmid, newid, config=None, is_lxc=False):
        return self.client.vm_clone(node, vmid, newid, config, is_lxc)

    def snapshot_create(self, node, vmid, snapname=None, description=None, is_lxc=False, change_number=None, interactive=False):
        return self.client.vm_snapshot_create(node, vmid, snapname, description, is_lxc, change_number, interactive)

    def snapshot_list(self, node, vmid, is_lxc=False):
        return self.client.vm_snapshot_list(node, vmid, is_lxc)

    def snapshot_rollback(self, node, vmid, snapname, is_lxc=False):
        return self.client.vm_snapshot_rollback(node, vmid, snapname, is_lxc)

    def snapshot_delete(self, node, vmid, snapname, is_lxc=False):
        return self.client.vm_snapshot_delete(node, vmid, snapname, is_lxc)

    def migrate(self, node, vmid, target_node, online=True, is_lxc=False):
        return self.client.vm_migrate(node, vmid, target_node, online, is_lxc)

    def resize(self, node, vmid, disk, size, is_lxc=False):
        return self.client.vm_resize(node, vmid, disk, size, is_lxc)

    def move_volume(self, node, vmid, volume, storage, is_lxc=False):
        return self.client.vm_move_volume(node, vmid, volume, storage, is_lxc)

    def template(self, node, vmid, is_lxc=False):
        return self.client.vm_template(node, vmid, is_lxc)

    def vncproxy(self, node, vmid, is_lxc=False):
        return self.client.vm_vncproxy(node, vmid, is_lxc)

    def spiceproxy(self, node, vmid, is_lxc=False):
        return self.client.vm_spiceproxy(node, vmid, is_lxc)

    def monitor(self, node, vmid, command, is_lxc=False):
        return self.client.vm_monitor(node, vmid, command, is_lxc)

    def firewall(self, node, vmid, is_lxc=False):
        return self.client.vm_firewall(node, vmid, is_lxc)

    def rrd(self, node, vmid, timeframe='hour', is_lxc=False):
        return self.client.vm_rrd(node, vmid, timeframe, is_lxc)


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

    # Phase 3 additions
    def upload(self, storage, filename, content):
        return self.client.storage_upload(storage, filename, content)

    def download(self, storage, volid):
        return self.client.storage_download(storage, volid)

    def rrd(self, storage, timeframe='hour'):
        return self.client.storage_rrd(storage, timeframe)

    def scan(self, storage):
        return self.client.storage_scan(storage)


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


class Container(VM):
    """
    Wrapper class for Container (LXC) operations.
    Inherits from VM and sets is_lxc=True for all operations.
    """
    def __init__(self, client: ProxmoxClient):
        super().__init__(client)

    def list(self, node=None):
        if node:
            resources = self.client._get(f'/nodes/{node}/lxc')
            containers = resources['data']
            for ct in containers:
                ct['node'] = node
            return containers
        else:
            resources = self.client._get('/cluster/resources')
            containers = [r for r in resources['data'] if r['type'] == 'lxc']
            return containers

    def status(self, node, vmid):
        return super().status(node, vmid, is_lxc=True)

    def start(self, node, vmid):
        return super().start(node, vmid, is_lxc=True)

    def stop(self, node, vmid):
        return super().stop(node, vmid, is_lxc=True)

    def reboot(self, node, vmid):
        return super().reboot(node, vmid, is_lxc=True)

    def shutdown(self, node, vmid, timeout=None):
        return super().shutdown(node, vmid, is_lxc=True, timeout=timeout)

    def create(self, node, vmid, config):
        return super().create(node, vmid, config, is_lxc=True)

    def delete(self, node, vmid):
        return super().delete(node, vmid, is_lxc=True)

    def config_get(self, node, vmid):
        return super().config_get(node, vmid, is_lxc=True)

    def config_set(self, node, vmid, config):
        return super().config_set(node, vmid, config, is_lxc=True)

    def clone(self, node, vmid, newid, config=None):
        return super().clone(node, vmid, newid, config, is_lxc=True)

    def snapshot_create(self, node, vmid, snapname=None, description=None, change_number=None, interactive=False):
        return super().snapshot_create(node, vmid, snapname, description, is_lxc=True, change_number=change_number, interactive=interactive)

    def snapshot_list(self, node, vmid):
        return super().snapshot_list(node, vmid, is_lxc=True)

    def snapshot_rollback(self, node, vmid, snapname):
        return super().snapshot_rollback(node, vmid, snapname, is_lxc=True)

    def snapshot_delete(self, node, vmid, snapname):
        return super().snapshot_delete(node, vmid, snapname, is_lxc=True)

    def migrate(self, node, vmid, target_node, online=True):
        return super().migrate(node, vmid, target_node, online, is_lxc=True)

    def resize(self, node, vmid, disk, size):
        return super().resize(node, vmid, disk, size, is_lxc=True)

    def move_volume(self, node, vmid, volume, storage):
        return super().move_volume(node, vmid, volume, storage, is_lxc=True)

    def template(self, node, vmid):
        return super().template(node, vmid, is_lxc=True)

    def vncproxy(self, node, vmid):
        return super().vncproxy(node, vmid, is_lxc=True)

    def spiceproxy(self, node, vmid):
        return super().spiceproxy(node, vmid, is_lxc=True)

    def monitor(self, node, vmid, command):
        return super().monitor(node, vmid, command, is_lxc=True)

    def firewall(self, node, vmid):
        return super().firewall(node, vmid, is_lxc=True)


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

    # Phase 3 additions
    def firewall(self):
        return self.client.cluster_firewall()

    def ha(self):
        return self.client.cluster_ha()

    def ha_groups(self):
        return self.client.cluster_ha_groups()

    def ha_resources(self):
        return self.client.cluster_ha_resources()

    def resources(self):
        return self.client.cluster_resources()

    def nextid(self):
        return self.client.cluster_nextid()

    def rrd(self, timeframe='hour'):
        return self.client.cluster_rrd(timeframe)

    def logs(self, limit=50):
        return self.client.cluster_logs(limit)


class Access:
    """
    Wrapper class for Access Control operations.
    """
    def __init__(self, client: ProxmoxClient):
        self.client = client

    def user_list(self):
        return self.client.user_list()

    def user_create(self, userid, config):
        return self.client.user_create(userid, config)

    def user_delete(self, userid):
        return self.client.user_delete(userid)

    def group_list(self):
        return self.client.group_list()

    def group_create(self, groupid):
        return self.client.group_create(groupid)

    def role_list(self):
        return self.client.role_list()

    def role_create(self, roleid, privs):
        return self.client.role_create(roleid, privs)

    def permission_list(self):
        return self.client.permission_list()

    def domain_list(self):
        return self.client.domain_list()

    def token_create(self, user, tokenid):
        return self.client.token_create(user, tokenid)

    def token_delete(self, user, tokenid):
        return self.client.token_delete(user, tokenid)


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

    # Phase 3 additions
    def firewall(self, node):
        return self.client.node_firewall(node)

    def dns(self, node):
        return self.client.node_dns(node)

    def time(self, node):
        return self.client.node_time(node)

    def version(self, node):
        return self.client.node_version(node)

    def apt(self, node):
        return self.client.node_apt(node)

    def subscription(self, node):
        return self.client.node_subscription(node)

    def certificates(self, node):
        return self.client.node_certificates(node)

    def syslog(self, node, limit=None):
        return self.client.node_syslog(node, limit)

    def rrd(self, node, timeframe='hour'):
        return self.client.node_rrd(node, timeframe)

    def vncshell(self, node):
        return self.client.node_vncshell(node)

    def spiceshell(self, node):
        return self.client.node_spiceshell(node)

    def migrateall(self, node, target_node):
        return self.client.node_migrateall(node, target_node)

    def startall(self, node):
        return self.client.node_startall(node)

    def stopall(self, node):
        return self.client.node_stopall(node)

    def ceph(self, node):
        return self.client.node_ceph(node)

    def rrd(self, node, timeframe='hour'):
        return self.client.node_rrd(node, timeframe)


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
    result = client.poll_task(node, upid, timeout, poll_interval)
    return result['success']

# Utility function to load client from config
def load_client():
    skill_dir = os.path.dirname(os.path.dirname(__file__))
    config_path = os.path.join(skill_dir, 'secrets', 'config.proxmox.yaml')
    token_path = os.path.join(skill_dir, 'secrets', 'pve-token.txt')

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
        config.timeout = raw_config['proxmox'].get('timeout', 30)
        config.auto_poll = raw_config['proxmox'].get('auto_poll', True)

    # Load token
    with open(token_path, 'r') as f:
        token = f.read().strip()

    return ProxmoxClient(config.host, token, config.verify_ssl, config.timeout, config.auto_poll)