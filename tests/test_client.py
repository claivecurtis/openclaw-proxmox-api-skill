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
        mock_response = Mock()
        mock_response.json.return_value = {'version': '1.0'}
        mock_response.raise_for_status.return_value = None
        mock_session.get.return_value = mock_response

        client = ProxmoxClient('pve.example.com', 'token123', True)

        import requests
        mock_session.get.side_effect = requests.exceptions.Timeout()

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
        upid = client.vm_action('node1', 101, 'start', auto_poll=False)  # Explicit async

        assert upid == 'UPID:node1:00000001:00000002:00000003:some:task:'
        mock_session.post.assert_called_with('https://pve.example.com:8006/api2/json/nodes/node1/qemu/101/status/start', json={}, verify=True, timeout=30)

    @patch('client.requests.Session')
    def test_vm_action_auto_poll(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response_version = Mock()
        mock_response_version.json.return_value = {'version': '1.0'}
        mock_response_version.raise_for_status.return_value = None
        mock_response_post = Mock()
        mock_response_post.json.return_value = {'data': 'UPID:node1:00000001:00000002:00000003:some:task:'}
        mock_response_post.raise_for_status.return_value = None
        mock_response_poll = Mock()
        mock_response_poll.json.return_value = {'data': {'status': 'stopped', 'exitstatus': 'OK'}}
        mock_response_poll.raise_for_status.return_value = None
        mock_session.post.return_value = mock_response_post
        mock_session.get.side_effect = [mock_response_version, mock_response_poll]

        client = ProxmoxClient('pve.example.com', 'token123', True)
        result = client.vm_action('node1', 101, 'start', auto_poll=True)

        assert result == {'upid': 'UPID:node1:00000001:00000002:00000003:some:task:', 'success': True, 'exitstatus': 'OK', 'status': 'stopped'}
        mock_session.post.assert_called_once()
        assert mock_session.get.call_count == 2

    @patch('client.requests.Session')
    def test_vm_action_default_auto_poll_true(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response_version = Mock()
        mock_response_version.json.return_value = {'version': '1.0'}
        mock_response_version.raise_for_status.return_value = None
        mock_response_post = Mock()
        mock_response_post.json.return_value = {'data': 'UPID:node1:00000001:00000002:00000003:some:task:'}
        mock_response_post.raise_for_status.return_value = None
        mock_response_poll = Mock()
        mock_response_poll.json.return_value = {'data': {'status': 'stopped', 'exitstatus': 'OK'}}
        mock_response_poll.raise_for_status.return_value = None
        mock_session.post.return_value = mock_response_post
        mock_session.get.side_effect = [mock_response_version, mock_response_poll]

        client = ProxmoxClient('pve.example.com', 'token123', True)
        result = client.vm_action('node1', 101, 'start')  # Default auto_poll=True

        assert result == {'upid': 'UPID:node1:00000001:00000002:00000003:some:task:', 'success': True, 'exitstatus': 'OK', 'status': 'stopped'}
        mock_session.post.assert_called_once()
        assert mock_session.get.call_count == 2

    @patch('client.requests.Session')
    def test_vm_action_config_auto_poll_false(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response_version = Mock()
        mock_response_version.json.return_value = {'version': '1.0'}
        mock_response_version.raise_for_status.return_value = None
        mock_response_post = Mock()
        mock_response_post.json.return_value = {'data': 'UPID:node1:00000001:00000002:00000003:some:task:'}
        mock_response_post.raise_for_status.return_value = None
        mock_session.post.return_value = mock_response_post
        mock_session.get.return_value = mock_response_version

        client = ProxmoxClient('pve.example.com', 'token123', True, timeout=30, auto_poll=False)
        result = client.vm_action('node1', 101, 'start')  # Config auto_poll=False, no polling

        assert result == 'UPID:node1:00000001:00000002:00000003:some:task:'
        mock_session.post.assert_called_once()
        assert mock_session.get.call_count == 1  # Only version check, no poll

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

        assert result == {'success': True, 'exitstatus': 'OK', 'status': 'stopped'}
        assert mock_sleep.call_count == 0

    @patch('client.requests.Session')
    def test_poll_task_failure(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.json.return_value = {'data': {'status': 'stopped', 'exitstatus': 'ERROR'}}
        mock_response.raise_for_status.return_value = None
        mock_session.get.return_value = mock_response

        client = ProxmoxClient('pve.example.com', 'token123', True)

        result = client.poll_task('node1', 'upid123')
        assert result == {'success': False, 'exitstatus': 'ERROR', 'status': 'stopped'}

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
        import requests
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response_version = Mock()
        mock_response_version.json.return_value = {'version': '1.0'}
        mock_response_version.raise_for_status.return_value = None
        mock_response_pool = Mock()
        http_error = requests.exceptions.HTTPError("404 Client Error")
        http_error.response = Mock()
        http_error.response.status_code = 404
        mock_response_pool.raise_for_status.side_effect = http_error
        mock_response_post = Mock()
        mock_response_post.json.return_value = {}
        mock_response_post.raise_for_status.return_value = None
        mock_session.get.side_effect = [mock_response_version, mock_response_pool]
        mock_session.post.return_value = mock_response_post

        client = ProxmoxClient('pve.example.com', 'token123', True)
        client.create_resource_pool('newpool', 'Test pool')

        mock_session.post.assert_called_with('https://pve.example.com:8006/api2/json/pools', json={'poolid': 'newpool', 'comment': 'Test pool'}, verify=True, timeout=30)

    @patch('client.requests.Session')
    def test_list_pools_with_members(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response_version = Mock()
        mock_response_version.json.return_value = {'version': '1.0'}
        mock_response_version.raise_for_status.return_value = None
        mock_response_pools = Mock()
        mock_response_pools.json.return_value = {'data': [{'poolid': 'pool1'}, {'poolid': 'pool2'}]}
        mock_response_pools.raise_for_status.return_value = None
        mock_response_detail1 = Mock()
        mock_response_detail1.json.return_value = {'data': {'poolid': 'pool1', 'members': [{'vmid': 101, 'type': 'qemu'}]}}
        mock_response_detail1.raise_for_status.return_value = None
        mock_response_detail2 = Mock()
        mock_response_detail2.json.return_value = {'data': {'poolid': 'pool2', 'members': []}}
        mock_response_detail2.raise_for_status.return_value = None
        mock_session.get.side_effect = [mock_response_version, mock_response_pools, mock_response_detail1, mock_response_detail2]

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
        import requests
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response_version = Mock()
        mock_response_version.json.return_value = {'version': '1.0'}
        mock_response_version.raise_for_status.return_value = None
        mock_response_status = Mock()
        http_error = requests.exceptions.HTTPError("404 Client Error")
        http_error.response = Mock()
        http_error.response.status_code = 404
        mock_response_status.raise_for_status.side_effect = http_error
        mock_response_post = Mock()
        mock_response_post.json.return_value = {'data': 'UPID:node1:00000001:00000002:00000003:create:'}
        mock_response_post.raise_for_status.return_value = None
        mock_session.get.side_effect = [mock_response_version, mock_response_status]
        mock_session.post.return_value = mock_response_post

        client = ProxmoxClient('pve.example.com', 'token123', True)
        upid = client.vm_create('node1', 101, {'name': 'test-vm'}, auto_poll=False)

        assert upid == 'UPID:node1:00000001:00000002:00000003:create:'
        mock_session.post.assert_called_with('https://pve.example.com:8006/api2/json/nodes/node1/qemu', json={'vmid': 101, 'name': 'test-vm'}, verify=True, timeout=30)

    @patch('client.requests.Session')
    def test_vm_delete(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response_version = Mock()
        mock_response_version.json.return_value = {'version': '1.0'}
        mock_response_version.raise_for_status.return_value = None
        mock_response_status = Mock()
        mock_response_status.json.return_value = {'data': {'status': 'stopped'}}
        mock_response_status.raise_for_status.return_value = None
        mock_response_post = Mock()
        mock_response_post.json.return_value = {'data': 'UPID:node1:00000001:00000002:00000003:delete:'}
        mock_response_post.raise_for_status.return_value = None
        mock_session.get.side_effect = [mock_response_version, mock_response_status]
        mock_session.post.return_value = mock_response_post

        client = ProxmoxClient('pve.example.com', 'token123', True)
        upid = client.vm_delete('node1', 101, auto_poll=False)

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
        import requests
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response_version = Mock()
        mock_response_version.json.return_value = {'version': '1.0'}
        mock_response_version.raise_for_status.return_value = None
        http_error = requests.exceptions.HTTPError("404 Client Error")
        http_error.response = Mock()
        http_error.response.status_code = 404
        mock_response_status = Mock()
        mock_response_status.raise_for_status.side_effect = http_error
        mock_response_post = Mock()
        mock_response_post.json.return_value = {}
        mock_response_post.raise_for_status.return_value = None
        mock_session.get.side_effect = [mock_response_version, mock_response_status]
        mock_session.post.return_value = mock_response_post

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
        assert mock_sleep.call_count == 0

    # Phase 2 tests
    @patch('client.requests.Session')
    def test_vm_clone(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.json.return_value = {'data': 'UPID:node1:00000001:00000002:00000003:clone:'}
        mock_response.raise_for_status.return_value = None
        mock_session.post.return_value = mock_response

        client = ProxmoxClient('pve.example.com', 'token123', True)
        upid = client.vm_clone('node1', 101, 102, {'name': 'clone-vm'}, auto_poll=False)

        assert upid == 'UPID:node1:00000001:00000002:00000003:clone:'
        mock_session.post.assert_called_with('https://pve.example.com:8006/api2/json/nodes/node1/qemu/101/clone', json={'newid': 102, 'name': 'clone-vm'}, verify=True, timeout=30)

    @patch('client.requests.Session')
    def test_vm_snapshot_create(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.json.return_value = {'data': 'UPID:node1:00000001:00000002:00000003:snapshot:'}
        mock_response.raise_for_status.return_value = None
        mock_session.post.return_value = mock_response

        client = ProxmoxClient('pve.example.com', 'token123', True)
        upid = client.vm_snapshot_create('node1', 101, 'snap1', 'Test snapshot', auto_poll=False)

        assert upid == 'UPID:node1:00000001:00000002:00000003:snapshot:'
        mock_session.post.assert_called_with('https://pve.example.com:8006/api2/json/nodes/node1/qemu/101/snapshot', json={'snapname': 'snap1', 'description': 'Test snapshot'}, verify=True, timeout=30)

    @patch('client.save_snapshot_settings')
    @patch('client.load_snapshot_settings')
    @patch('client.requests.Session')
    def test_vm_snapshot_create_auto_name(self, mock_session_class, mock_load_settings, mock_save_settings):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.json.return_value = {'data': 'UPID:node1:00000001:00000002:00000003:snapshot:'}
        mock_response.raise_for_status.return_value = None
        mock_session.post.return_value = mock_response
        mock_load_settings.return_value = {'naming_convention': 'aiagent-snap-{number:04d}', 'next_number': 5}
        mock_save_settings.return_value = None

        client = ProxmoxClient('pve.example.com', 'token123', True)
        upid = client.vm_snapshot_create('node1', 101, auto_poll=False)

        assert upid == 'UPID:node1:00000001:00000002:00000003:snapshot:'
        mock_session.post.assert_called_with('https://pve.example.com:8006/api2/json/nodes/node1/qemu/101/snapshot', json={'snapname': 'aiagent-snap-0005'}, verify=True, timeout=30)
        mock_save_settings.assert_called_with({'naming_convention': 'aiagent-snap-{number:04d}', 'next_number': 6})

    @patch('client.requests.Session')
    def test_vm_snapshot_list(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.json.return_value = {'data': [{'name': 'snap1', 'description': 'Test'}]}
        mock_response.raise_for_status.return_value = None
        mock_session.get.return_value = mock_response

        client = ProxmoxClient('pve.example.com', 'token123', True)
        snapshots = client.vm_snapshot_list('node1', 101)

        assert snapshots == [{'name': 'snap1', 'description': 'Test'}]
        mock_session.get.assert_called_with('https://pve.example.com:8006/api2/json/nodes/node1/qemu/101/snapshot', params=None, verify=True, timeout=30)

    @patch('client.requests.Session')
    def test_vm_snapshot_rollback(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.json.return_value = {'data': 'UPID:node1:00000001:00000002:00000003:rollback:'}
        mock_response.raise_for_status.return_value = None
        mock_session.post.return_value = mock_response

        client = ProxmoxClient('pve.example.com', 'token123', True)
        upid = client.vm_snapshot_rollback('node1', 101, 'snap1')

        assert upid == 'UPID:node1:00000001:00000002:00000003:rollback:'
        mock_session.post.assert_called_with('https://pve.example.com:8006/api2/json/nodes/node1/qemu/101/snapshot/snap1/rollback', json={}, verify=True, timeout=30)

    @patch('client.requests.Session')
    def test_vm_snapshot_delete(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.json.return_value = {'data': 'UPID:node1:00000001:00000002:00000003:delete:'}
        mock_response.raise_for_status.return_value = None
        mock_session.delete.return_value = mock_response

        client = ProxmoxClient('pve.example.com', 'token123', True)
        upid = client.vm_snapshot_delete('node1', 101, 'snap1', auto_poll=False)

        assert upid == 'UPID:node1:00000001:00000002:00000003:delete:'
        mock_session.delete.assert_called_with('https://pve.example.com:8006/api2/json/nodes/node1/qemu/101/snapshot/snap1', verify=True, timeout=30)

    @patch('client.requests.Session')
    def test_vm_migrate(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.json.return_value = {'data': 'UPID:node1:00000001:00000002:00000003:migrate:'}
        mock_response.raise_for_status.return_value = None
        mock_session.post.return_value = mock_response

        client = ProxmoxClient('pve.example.com', 'token123', True)
        upid = client.vm_migrate('node1', 101, 'node2', online=False, auto_poll=False)

        assert upid == 'UPID:node1:00000001:00000002:00000003:migrate:'
        mock_session.post.assert_called_with('https://pve.example.com:8006/api2/json/nodes/node1/qemu/101/migrate', json={'target': 'node2', 'online': 0}, verify=True, timeout=30)

    @patch('client.requests.Session')
    def test_vm_resize(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.json.return_value = {}
        mock_response.raise_for_status.return_value = None
        mock_session.post.return_value = mock_response

        client = ProxmoxClient('pve.example.com', 'token123', True)
        client.vm_resize('node1', 101, 'scsi0', '+10G')

        mock_session.post.assert_called_with('https://pve.example.com:8006/api2/json/nodes/node1/qemu/101/resize', json={'disk': 'scsi0', 'size': '+10G'}, verify=True, timeout=30)

    @patch('client.requests.Session')
    def test_vm_move_volume(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.json.return_value = {'data': 'UPID:node1:00000001:00000002:00000003:move:'}
        mock_response.raise_for_status.return_value = None
        mock_session.post.return_value = mock_response

        client = ProxmoxClient('pve.example.com', 'token123', True)
        upid = client.vm_move_volume('node1', 101, 'scsi0', 'nfs', auto_poll=False)

        assert upid == 'UPID:node1:00000001:00000002:00000003:move:'
        mock_session.post.assert_called_with('https://pve.example.com:8006/api2/json/nodes/node1/qemu/101/move_disk', json={'disk': 'scsi0', 'storage': 'nfs'}, verify=True, timeout=30)

    @patch('client.requests.Session')
    def test_vm_template(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.json.return_value = {}
        mock_response.raise_for_status.return_value = None
        mock_session.post.return_value = mock_response

        client = ProxmoxClient('pve.example.com', 'token123', True)
        client.vm_template('node1', 101)

        mock_session.post.assert_called_with('https://pve.example.com:8006/api2/json/nodes/node1/qemu/101/template', json={}, verify=True, timeout=30)

    @patch('client.requests.Session')
    def test_vm_vncproxy(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.json.return_value = {'data': {'port': 5900, 'ticket': 'ticket123'}}
        mock_response.raise_for_status.return_value = None
        mock_session.post.return_value = mock_response

        client = ProxmoxClient('pve.example.com', 'token123', True)
        proxy = client.vm_vncproxy('node1', 101)

        assert proxy == {'port': 5900, 'ticket': 'ticket123'}
        mock_session.post.assert_called_with('https://pve.example.com:8006/api2/json/nodes/node1/qemu/101/vncproxy', json={}, verify=True, timeout=30)

    @patch('client.requests.Session')
    def test_vm_spiceproxy(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.json.return_value = {'data': {'proxy': 'spice://host:port'}}
        mock_response.raise_for_status.return_value = None
        mock_session.post.return_value = mock_response

        client = ProxmoxClient('pve.example.com', 'token123', True)
        proxy = client.vm_spiceproxy('node1', 101)

        assert proxy == {'proxy': 'spice://host:port'}
        mock_session.post.assert_called_with('https://pve.example.com:8006/api2/json/nodes/node1/qemu/101/spiceproxy', json={}, verify=True, timeout=30)

    @patch('client.requests.Session')
    def test_vm_monitor(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.json.return_value = {'data': 'OK'}
        mock_response.raise_for_status.return_value = None
        mock_session.post.return_value = mock_response

        client = ProxmoxClient('pve.example.com', 'token123', True)
        response = client.vm_monitor('node1', 101, 'info version')

        assert response == 'OK'
        mock_session.post.assert_called_with('https://pve.example.com:8006/api2/json/nodes/node1/qemu/101/monitor', json={'command': 'info version'}, verify=True, timeout=30)

    @patch('client.requests.Session')
    def test_vm_firewall(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.json.return_value = {'data': [{'type': 'in', 'action': 'ACCEPT'}]}
        mock_response.raise_for_status.return_value = None
        mock_session.get.return_value = mock_response

        client = ProxmoxClient('pve.example.com', 'token123', True)
        rules = client.vm_firewall('node1', 101)

        assert rules == [{'type': 'in', 'action': 'ACCEPT'}]
        mock_session.get.assert_called_with('https://pve.example.com:8006/api2/json/nodes/node1/qemu/101/firewall/rules', params=None, verify=True, timeout=30)

    # Phase 3 tests
    @patch('client.requests.Session')
    def test_storage_upload(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_session.post.return_value = mock_response

        client = ProxmoxClient('pve.example.com', 'token123', True)
        client.storage_upload('local', 'test.iso', b'content')

        # Note: actual call may vary for multipart
        mock_session.post.assert_called_with('https://pve.example.com:8006/api2/json/nodes/pve.example.com/storage/local/upload', files={'filename': ('test.iso', b'content')}, verify=True, timeout=30)

    @patch('client.requests.Session')
    def test_storage_download(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.content = b'downloaded content'
        mock_response.raise_for_status.return_value = None
        mock_session.get.return_value = mock_response

        client = ProxmoxClient('pve.example.com', 'token123', True)
        content = client.storage_download('local', 'test.iso')

        assert content == b'downloaded content'
        mock_session.get.assert_called_with('https://pve.example.com:8006/api2/json/storage/local/content/test.iso', verify=True, timeout=30)

    @patch('client.requests.Session')
    def test_storage_rrd(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.json.return_value = {'data': [{'time': 123456, 'value': 100}]}
        mock_response.raise_for_status.return_value = None
        mock_session.get.return_value = mock_response

        client = ProxmoxClient('pve.example.com', 'token123', True)
        rrd = client.storage_rrd('local', timeframe='day')

        assert rrd == [{'time': 123456, 'value': 100}]
        mock_session.get.assert_called_with('https://pve.example.com:8006/api2/json/storage/local/rrd', params={'timeframe': 'day'}, verify=True, timeout=30)

    @patch('client.requests.Session')
    def test_storage_scan(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.json.return_value = {'data': 'UPID:node1:123:scan'}
        mock_response.raise_for_status.return_value = None
        mock_session.post.return_value = mock_response

        client = ProxmoxClient('pve.example.com', 'token123', True)
        upid = client.storage_scan('local')

        assert upid == 'UPID:node1:123:scan'
        mock_session.post.assert_called_with('https://pve.example.com:8006/api2/json/storage/local/scan', json={}, verify=True, timeout=30)

    @patch('client.requests.Session')
    def test_storage_scan_default_auto_poll_true(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response_version = Mock()
        mock_response_version.json.return_value = {'version': '1.0'}
        mock_response_version.raise_for_status.return_value = None
        mock_response_post = Mock()
        mock_response_post.json.return_value = {'data': 'UPID:cluster:00000001:00000002:00000003:scan:'}
        mock_response_post.raise_for_status.return_value = None
        mock_response_poll = Mock()
        mock_response_poll.json.return_value = {'data': {'status': 'stopped', 'exitstatus': 'OK'}}
        mock_response_poll.raise_for_status.return_value = None
        mock_session.post.return_value = mock_response_post
        mock_session.get.side_effect = [mock_response_version, mock_response_poll]

        client = ProxmoxClient('pve.example.com', 'token123', True)
        result = client.storage_scan('local', auto_poll=True)

        assert result == {'upid': 'UPID:cluster:00000001:00000002:00000003:scan:', 'success': True, 'exitstatus': 'OK', 'status': 'stopped'}
        mock_session.post.assert_called_once()
        assert mock_session.get.call_count == 2

    @patch('client.requests.Session')
    def test_cluster_firewall(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.json.return_value = {'data': [{'type': 'in', 'action': 'DROP'}]}
        mock_response.raise_for_status.return_value = None
        mock_session.get.return_value = mock_response

        client = ProxmoxClient('pve.example.com', 'token123', True)
        rules = client.cluster_firewall()

        assert rules == [{'type': 'in', 'action': 'DROP'}]
        mock_session.get.assert_called_with('https://pve.example.com:8006/api2/json/cluster/firewall/rules', params=None, verify=True, timeout=30)

    @patch('client.requests.Session')
    def test_cluster_ha(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.json.return_value = {'data': {'status': 'active'}}
        mock_response.raise_for_status.return_value = None
        mock_session.get.return_value = mock_response

        client = ProxmoxClient('pve.example.com', 'token123', True)
        ha = client.cluster_ha()

        assert ha == {'status': 'active'}
        mock_session.get.assert_called_with('https://pve.example.com:8006/api2/json/cluster/ha/status', params=None, verify=True, timeout=30)

    @patch('client.requests.Session')
    def test_cluster_resources(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.json.return_value = {'data': [{'type': 'node', 'id': 'node1'}]}
        mock_response.raise_for_status.return_value = None
        mock_session.get.return_value = mock_response

        client = ProxmoxClient('pve.example.com', 'token123', True)
        resources = client.cluster_resources(type='node')

        assert resources == [{'type': 'node', 'id': 'node1'}]
        mock_session.get.assert_called_with('https://pve.example.com:8006/api2/json/cluster/resources', params={'type': 'node'}, verify=True, timeout=30)

    @patch('client.requests.Session')
    def test_cluster_nextid(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.json.return_value = {'data': 102}
        mock_response.raise_for_status.return_value = None
        mock_session.get.return_value = mock_response

        client = ProxmoxClient('pve.example.com', 'token123', True)
        nextid = client.cluster_nextid()

        assert nextid == 102
        mock_session.get.assert_called_with('https://pve.example.com:8006/api2/json/cluster/nextid', params=None, verify=True, timeout=30)

    @patch('client.requests.Session')
    def test_user_list(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.json.return_value = {'data': [{'userid': 'user@pve'}]}
        mock_response.raise_for_status.return_value = None
        mock_session.get.return_value = mock_response

        client = ProxmoxClient('pve.example.com', 'token123', True)
        users = client.user_list()

        assert users == [{'userid': 'user@pve'}]
        mock_session.get.assert_called_with('https://pve.example.com:8006/api2/json/access/users', params=None, verify=True, timeout=30)

    @patch('client.requests.Session')
    def test_node_firewall(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.json.return_value = {'data': [{'type': 'in', 'action': 'ACCEPT'}]}
        mock_response.raise_for_status.return_value = None
        mock_session.get.return_value = mock_response

        client = ProxmoxClient('pve.example.com', 'token123', True)
        rules = client.node_firewall('node1')

        assert rules == [{'type': 'in', 'action': 'ACCEPT'}]
        mock_session.get.assert_called_with('https://pve.example.com:8006/api2/json/nodes/node1/firewall/rules', params=None, verify=True, timeout=30)

    @patch('client.requests.Session')
    def test_node_dns(self, mock_session_class):
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        mock_response = Mock()
        mock_response.json.return_value = {'data': {'search': 'example.com'}}
        mock_response.raise_for_status.return_value = None
        mock_session.get.return_value = mock_response

        client = ProxmoxClient('pve.example.com', 'token123', True)
        dns = client.node_dns('node1')

        assert dns == {'search': 'example.com'}
        mock_session.get.assert_called_with('https://pve.example.com:8006/api2/json/nodes/node1/dns', params=None, verify=True, timeout=30)