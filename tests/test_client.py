import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add scripts directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from client import ProxmoxClient, PBSClient, ProxmoxAuthError, ProxmoxAPIError, TaskTimeoutError, VM, Storage, Pool, poll_task_until_complete

class TestProxmoxClient:

    @patch('client.requests.Session')
    def test_init_success(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.json.return_value = {'data': 'version'}
        mock_session.get.return_value = mock_response

        client = ProxmoxClient('pve.example.com', 'token123', True)

        assert client.host == 'pve.example.com'
        assert client.token == 'token123'
        mock_session.headers.update.assert_called()
        mock_session.get.assert_called_with('https://pve.example.com:8006/api2/json/version', params=None, verify=True, timeout=30)

    @patch('client.requests.Session')
    def test_init_auth_fail(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_session.get.side_effect = Exception('Connection failed')

        with pytest.raises(ProxmoxAuthError):
            ProxmoxClient('pve.example.com', 'token123', True)

    @patch('client.requests.Session')
    def test_get_success(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.json.return_value = {'data': 'test'}
        mock_response.raise_for_status.return_value = None
        mock_session.get.return_value = mock_response

        client = ProxmoxClient('pve.example.com', 'token123', True)
        result = client._get('/test')

        assert result == {'data': 'test'}
        mock_session.get.assert_called_with('https://pve.example.com:8006/api2/json/test', params=None, verify=True, timeout=30)

    @patch('client.requests.Session')
    def test_get_timeout(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_session.get.side_effect = TimeoutError()

        client = ProxmoxClient('pve.example.com', 'token123', True)

        with pytest.raises(ProxmoxAPIError, match="Request timed out"):
            client._get('/test')

    @patch('client.requests.Session')
    def test_list_vms(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.json.return_value = {
            'data': [
                {'type': 'qemu', 'id': 101},
                {'type': 'lxc', 'id': 201},
                {'type': 'node', 'id': 'node1'}
            ]
        }
        mock_response.raise_for_status.return_value = None
        mock_session.get.return_value = mock_response

        client = ProxmoxClient('pve.example.com', 'token123', True)
        vms = client.list_vms()

        assert len(vms) == 2
        assert vms[0]['type'] == 'qemu'
        assert vms[1]['type'] == 'lxc'

    @patch('client.requests.Session')
    def test_vm_action_async(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.json.return_value = {'data': 'UPID:node1:00000001:00000002:00000003:some:task:'}
        mock_response.raise_for_status.return_value = None
        mock_session.post.return_value = mock_response

        client = ProxmoxClient('pve.example.com', 'token123', True)
        upid = client.vm_action('node1', 101, 'start')

        assert upid == 'UPID:node1:00000001:00000002:00000003:some:task:'
        mock_session.post.assert_called_with('https://pve.example.com:8006/api2/json/nodes/node1/qemu/101/status/start', json={}, verify=True, timeout=30)

    @patch('client.requests.Session')
    def test_poll_task_success(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.json.side_effect = [
            {'data': {'status': 'running'}},
            {'data': {'status': 'stopped', 'exitstatus': 'OK'}}
        ]
        mock_response.raise_for_status.return_value = None
        mock_session.get.return_value = mock_response

        client = ProxmoxClient('pve.example.com', 'token123', True)

        with patch('time.sleep') as mock_sleep:
            with patch('time.time', side_effect=[0, 1, 2]):
                result = client.poll_task('node1', 'upid123', timeout=10, poll_interval=1)

        assert result is True
        assert mock_sleep.call_count == 1

    @patch('client.requests.Session')
    def test_poll_task_failure(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.json.return_value = {'data': {'status': 'stopped', 'exitstatus': 'ERROR'}}
        mock_response.raise_for_status.return_value = None
        mock_session.get.return_value = mock_response

        client = ProxmoxClient('pve.example.com', 'token123', True)

        with pytest.raises(ProxmoxAPIError, match="Task upid123 failed"):
            client.poll_task('node1', 'upid123')

    @patch('client.requests.Session')
    def test_poll_task_timeout(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.json.return_value = {'data': {'status': 'running'}}
        mock_response.raise_for_status.return_value = None
        mock_session.get.return_value = mock_response

        client = ProxmoxClient('pve.example.com', 'token123', True)

        with patch('time.sleep') as mock_sleep:
            with patch('time.time', side_effect=[0, 300, 301]):
                with pytest.raises(TaskTimeoutError, match="Task upid123 timed out"):
                    client.poll_task('node1', 'upid123', timeout=300)

    @patch('client.requests.Session')
    def test_list_storage_pools(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.json.return_value = {
            'data': [
                {'type': 'storage', 'id': 'local'},
                {'type': 'storage', 'id': 'nfs'},
                {'type': 'node', 'id': 'node1'}
            ]
        }
        mock_response.raise_for_status.return_value = None
        mock_session.get.return_value = mock_response

        client = ProxmoxClient('pve.example.com', 'token123', True)
        pools = client.list_storage_pools()

        assert len(pools) == 2
        assert pools[0]['id'] == 'local'
        assert pools[1]['id'] == 'nfs'

    @patch('client.requests.Session')
    def test_list_resource_pools(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.json.return_value = {
            'data': [
                {'poolid': 'pool1', 'comment': 'Test pool'},
                {'poolid': 'pool2'}
            ]
        }
        mock_response.raise_for_status.return_value = None
        mock_session.get.return_value = mock_response

        client = ProxmoxClient('pve.example.com', 'token123', True)
        pools = client.list_resource_pools()

        assert len(pools) == 2
        assert pools[0]['poolid'] == 'pool1'

    @patch('client.requests.Session')
    def test_create_resource_pool(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.json.return_value = {}
        mock_response.raise_for_status.return_value = None
        mock_session.post.return_value = mock_response

        client = ProxmoxClient('pve.example.com', 'token123', True)
        client.create_resource_pool('newpool', 'Test pool')

        mock_session.post.assert_called_with('https://pve.example.com:8006/api2/json/pools', json={'poolid': 'newpool', 'comment': 'Test pool'}, verify=True, timeout=30)

    @patch('client.requests.Session')
    def test_list_pools_with_members(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response_pools = Mock()
        mock_response_pools.json.return_value = {'data': [{'poolid': 'pool1'}, {'poolid': 'pool2'}]}
        mock_response_pools.raise_for_status.return_value = None
        mock_response_detail1 = Mock()
        mock_response_detail1.json.return_value = {'data': {'poolid': 'pool1', 'members': [{'vmid': 101, 'type': 'qemu'}]}}
        mock_response_detail1.raise_for_status.return_value = None
        mock_response_detail2 = Mock()
        mock_response_detail2.json.return_value = {'data': {'poolid': 'pool2', 'members': []}}
        mock_response_detail2.raise_for_status.return_value = None
        mock_session.get.side_effect = [mock_response_pools, mock_response_detail1, mock_response_detail2]

        client = ProxmoxClient('pve.example.com', 'token123', True)
        pools = client.list_pools_with_members()

        assert len(pools) == 2
        assert pools[0]['poolid'] == 'pool1'
        assert pools[0]['members'][0]['vmid'] == 101
        assert pools[1]['poolid'] == 'pool2'

    @patch('client.requests.Session')
    def test_get_vm_status(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.json.return_value = {'data': {'status': 'running', 'vmid': 101}}
        mock_response.raise_for_status.return_value = None
        mock_session.get.return_value = mock_response

        client = ProxmoxClient('pve.example.com', 'token123', True)
        status = client.get_vm_status('node1', 101, False)

        assert status['status'] == 'running'
        assert status['vmid'] == 101
        mock_session.get.assert_called_with('https://pve.example.com:8006/api2/json/nodes/node1/qemu/101/status/current', params=None, verify=True, timeout=30)

    @patch('client.requests.Session')
    def test_pbs_init_success(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.json.return_value = {'data': 'version'}
        mock_session.get.return_value = mock_response

        client = PBSClient('pbs.example.com', 'token123', True)

        assert client.host == 'pbs.example.com'
        mock_session.get.assert_called_with('https://pbs.example.com:8007/api2/json/version', params=None, verify=True, timeout=30)

    @patch('client.requests.Session')
    def test_pbs_list_datastores(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.json.return_value = {
            'data': [
                {'id': 'store1'},
                {'id': 'store2'}
            ]
        }
        mock_response.raise_for_status.return_value = None
        mock_session.get.return_value = mock_response

        client = PBSClient('pbs.example.com', 'token123', True)
        datastores = client.list_datastores()

        assert len(datastores) == 2
        assert datastores[0]['id'] == 'store1'

    @patch('client.requests.Session')
    def test_pbs_backup_vm(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.json.return_value = {'data': 'UPID:pbs:00000001:00000002:00000003:backup:'}
        mock_response.raise_for_status.return_value = None
        mock_session.post.return_value = mock_response

        client = PBSClient('pbs.example.com', 'token123', True)
        upid = client.backup_vm('store1', 101, 'node1')

        assert upid == 'UPID:pbs:00000001:00000002:00000003:backup:'
        mock_session.post.assert_called_with('https://pbs.example.com:8007/api2/json/datastore/store1/backup', json={'id': 'node1/101', 'type': 'vm'}, verify=True, timeout=30)

    @patch('client.requests.Session')
    def test_vm_create(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.json.return_value = {'data': 'UPID:node1:00000001:00000002:00000003:create:'}
        mock_response.raise_for_status.return_value = None
        mock_session.post.return_value = mock_response

        client = ProxmoxClient('pve.example.com', 'token123', True)
        upid = client.vm_create('node1', 101, {'name': 'test-vm'})

        assert upid == 'UPID:node1:00000001:00000002:00000003:create:'
        mock_session.post.assert_called_with('https://pve.example.com:8006/api2/json/nodes/node1/qemu', json={'vmid': 101, 'name': 'test-vm'}, verify=True, timeout=30)

    @patch('client.requests.Session')
    def test_vm_delete(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.json.return_value = {'data': 'UPID:node1:00000001:00000002:00000003:delete:'}
        mock_response.raise_for_status.return_value = None
        mock_session.post.return_value = mock_response

        client = ProxmoxClient('pve.example.com', 'token123', True)
        upid = client.vm_delete('node1', 101)

        assert upid == 'UPID:node1:00000001:00000002:00000003:delete:'
        mock_session.post.assert_called_with('https://pve.example.com:8006/api2/json/nodes/node1/qemu/101', json={}, verify=True, timeout=30)

    @patch('client.requests.Session')
    def test_vm_config_get(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.json.return_value = {'data': {'name': 'test-vm', 'memory': 1024}}
        mock_response.raise_for_status.return_value = None
        mock_session.get.return_value = mock_response

        client = ProxmoxClient('pve.example.com', 'token123', True)
        config = client.vm_config_get('node1', 101)

        assert config == {'name': 'test-vm', 'memory': 1024}
        mock_session.get.assert_called_with('https://pve.example.com:8006/api2/json/nodes/node1/qemu/101/config', params=None, verify=True, timeout=30)

    @patch('client.requests.Session')
    def test_vm_config_set(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.json.return_value = {}
        mock_response.raise_for_status.return_value = None
        mock_session.post.return_value = mock_response

        client = ProxmoxClient('pve.example.com', 'token123', True)
        client.vm_config_set('node1', 101, {'memory': 2048})

        mock_session.post.assert_called_with('https://pve.example.com:8006/api2/json/nodes/node1/qemu/101/config', json={'memory': 2048}, verify=True, timeout=30)

    @patch('client.requests.Session')
    def test_storage_status(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.json.return_value = {'data': {'used': 100, 'available': 900}}
        mock_response.raise_for_status.return_value = None
        mock_session.get.return_value = mock_response

        client = ProxmoxClient('pve.example.com', 'token123', True)
        status = client.storage_status('local')

        assert status == {'used': 100, 'available': 900}
        mock_session.get.assert_called_with('https://pve.example.com:8006/api2/json/storage/local/status', params=None, verify=True, timeout=30)

    @patch('client.requests.Session')
    def test_storage_content(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.json.return_value = {'data': [{'volid': 'iso1.iso', 'size': 100}]}
        mock_response.raise_for_status.return_value = None
        mock_session.get.return_value = mock_response

        client = ProxmoxClient('pve.example.com', 'token123', True)
        content = client.storage_content('local', 'iso')

        assert content == [{'volid': 'iso1.iso', 'size': 100}]
        mock_session.get.assert_called_with('https://pve.example.com:8006/api2/json/storage/local/content', params={'content': 'iso'}, verify=True, timeout=30)

    @patch('client.requests.Session')
    def test_storage_create(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.json.return_value = {}
        mock_response.raise_for_status.return_value = None
        mock_session.post.return_value = mock_response

        client = ProxmoxClient('pve.example.com', 'token123', True)
        client.storage_create('nfs1', {'type': 'nfs', 'server': 'nfs.example.com'})

        mock_session.post.assert_called_with('https://pve.example.com:8006/api2/json/storage', json={'id': 'nfs1', 'type': 'nfs', 'server': 'nfs.example.com'}, verify=True, timeout=30)

    @patch('client.requests.Session')
    def test_storage_delete(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.json.return_value = {}
        mock_response.raise_for_status.return_value = None
        mock_session.post.return_value = mock_response

        client = ProxmoxClient('pve.example.com', 'token123', True)
        client.storage_delete('nfs1')

        mock_session.post.assert_called_with('https://pve.example.com:8006/api2/json/storage/nfs1', json={}, verify=True, timeout=30)

    @patch('client.requests.Session')
    def test_pool_members(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.json.return_value = {'data': {'poolid': 'pool1', 'members': [{'vmid': 101, 'type': 'qemu'}]}}
        mock_response.raise_for_status.return_value = None
        mock_session.get.return_value = mock_response

        client = ProxmoxClient('pve.example.com', 'token123', True)
        members = client.pool_members('pool1')

        assert members == [{'vmid': 101, 'type': 'qemu'}]
        mock_session.get.assert_called_with('https://pve.example.com:8006/api2/json/pools/pool1', params=None, verify=True, timeout=30)

    @patch('client.requests.Session')
    def test_pool_update(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.json.return_value = {}
        mock_response.raise_for_status.return_value = None
        mock_session.post.return_value = mock_response

        client = ProxmoxClient('pve.example.com', 'token123', True)
        client.pool_update('pool1', {'comment': 'Updated pool'})

        mock_session.post.assert_called_with('https://pve.example.com:8006/api2/json/pools/pool1', json={'comment': 'Updated pool'}, verify=True, timeout=30)

    @patch('client.requests.Session')
    def test_pool_delete(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.json.return_value = {}
        mock_response.raise_for_status.return_value = None
        mock_session.post.return_value = mock_response

        client = ProxmoxClient('pve.example.com', 'token123', True)
        client.pool_delete('pool1')

        mock_session.post.assert_called_with('https://pve.example.com:8006/api2/json/pools/pool1', json={}, verify=True, timeout=30)

    @patch('client.requests.Session')
    def test_vm_wrapper_list(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.json.return_value = {'data': [{'vmid': 101, 'name': 'vm1'}]}
        mock_response.raise_for_status.return_value = None
        mock_session.get.return_value = mock_response

        client = ProxmoxClient('pve.example.com', 'token123', True)
        vm = VM(client)
        vms = vm.list('node1')

        assert vms == [{'vmid': 101, 'name': 'vm1', 'node': 'node1'}]

    @patch('client.requests.Session')
    def test_storage_wrapper_list(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.json.return_value = {'data': [{'type': 'storage', 'id': 'local'}]}
        mock_response.raise_for_status.return_value = None
        mock_session.get.return_value = mock_response

        client = ProxmoxClient('pve.example.com', 'token123', True)
        storage = Storage(client)
        storages = storage.list()

        assert storages == [{'type': 'storage', 'id': 'local'}]

    @patch('client.requests.Session')
    def test_pool_wrapper_list(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.json.return_value = {'data': [{'poolid': 'pool1'}]}
        mock_response.raise_for_status.return_value = None
        mock_session.get.return_value = mock_response

        client = ProxmoxClient('pve.example.com', 'token123', True)
        pool = Pool(client)
        pools = pool.list()

        assert pools == [{'poolid': 'pool1'}]

    @patch('client.requests.Session')
    def test_poll_task_until_complete(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.json.side_effect = [
            {'data': {'status': 'running'}},
            {'data': {'status': 'stopped', 'exitstatus': 'OK'}}
        ]
        mock_response.raise_for_status.return_value = None
        mock_session.get.return_value = mock_response

        client = ProxmoxClient('pve.example.com', 'token123', True)

        with patch('time.sleep') as mock_sleep:
            with patch('time.time', side_effect=[0, 1, 2]):
                result = poll_task_until_complete(client, 'node1', 'upid123', timeout=10, poll_interval=1)

        assert result is True
        assert mock_sleep.call_count == 1