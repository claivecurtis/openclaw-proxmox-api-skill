import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add scripts directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from client import ProxmoxClient, ProxmoxAuthError, ProxmoxAPIError, TaskTimeoutError

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