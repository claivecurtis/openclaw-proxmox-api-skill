import pytest
from unittest.mock import patch, mock_open
import sys
import os

# Add scripts directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from client import load_client

class TestLoadClient:

    @patch('os.getenv')
    @patch('os.path.dirname')
    @patch('builtins.open', new_callable=mock_open, read_data='host: pve.example.com\nverify_ssl: true\n')
    @patch('yaml.safe_load')
    @patch('client.ProxmoxClient')
    def test_load_client_with_env_workspace(self, mock_proxmox_client, mock_yaml_load, mock_file, mock_dirname, mock_getenv):
        mock_getenv.return_value = '/custom/workspace'
        mock_yaml_load.return_value = {'proxmox': {'host': 'pve.example.com', 'verify_ssl': True}}
        mock_file.return_value.read.return_value = 'token123'

        client = load_client()

        mock_getenv.assert_called_with('OPENCLAW_WORKSPACE', os.path.dirname(os.path.dirname(mock_dirname.return_value)))
        assert mock_proxmox_client.called
        args, kwargs = mock_proxmox_client.call_args
        assert args[0] == 'pve.example.com'
        assert args[1] == 'token123'
        assert args[2] == True

    @patch('os.getenv')
    @patch('os.path.dirname')
    @patch('builtins.open', new_callable=mock_open, read_data='host: pve.example.com\nverify_ssl: false\n')
    @patch('yaml.safe_load')
    @patch('client.ProxmoxClient')
    def test_load_client_fallback_workspace(self, mock_proxmox_client, mock_yaml_load, mock_file, mock_dirname, mock_getenv):
        mock_getenv.return_value = None
        mock_dirname.side_effect = lambda path: '/path/to/scripts' if 'client.py' in path else '/path/to'
        mock_yaml_load.return_value = {'proxmox': {'host': 'pve.example.com', 'verify_ssl': False}}
        mock_file.return_value.read.return_value = 'token456'

        client = load_client()

        mock_getenv.assert_called_with('OPENCLAW_WORKSPACE', '/path/to')
        assert mock_proxmox_client.called
        args, kwargs = mock_proxmox_client.call_args
        assert args[0] == 'pve.example.com'
        assert args[1] == 'token456'
        assert args[2] == False