import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts import run


class LauncherTests(unittest.TestCase):
    def setUp(self):
        current = patch.object(run, 'ensure_current_backend')
        current.start()
        self.addCleanup(current.stop)

    def test_reuses_running_app_without_starting_or_installing(self):
        with patch.object(run, 'responds', return_value=True), patch.object(run.subprocess, 'Popen') as start, patch.object(run, 'availability') as model, patch.object(run.shutil, 'which') as node, patch.object(run.webbrowser, 'open') as browser:
            run.main()
            start.assert_not_called()
            model.assert_not_called()
            node.assert_not_called()
            browser.assert_called_once_with(run.FRONTEND_URL)

    def test_busy_services_can_finish_starting_without_duplicate_processes(self):
        with patch.object(run, 'responds', side_effect=[False, False, True, True]), patch.object(run, 'port_busy', return_value=True), patch.object(run.subprocess, 'Popen') as start, patch.object(run, 'availability') as model, patch.object(run.webbrowser, 'open') as browser:
            run.main()
            start.assert_not_called()
            model.assert_not_called()
            browser.assert_called_once_with(run.FRONTEND_URL)

    def test_unresponsive_busy_ports_do_not_spawn_or_terminate_processes(self):
        with patch.object(run, 'responds', return_value=False), patch.object(run, 'port_busy', return_value=True), patch.object(run.time, 'monotonic', side_effect=[0, 41]), patch.object(run.subprocess, 'Popen') as start:
            with self.assertRaisesRegex(RuntimeError, '8000 y 5173'):
                run.main()
            start.assert_not_called()

    def test_http_probe_uses_direct_local_opener(self):
        response = MagicMock()
        response.__enter__.return_value.status = 200
        with patch.object(run.LOCAL_HTTP, 'open', return_value=response) as direct, patch.object(run.urllib.request, 'urlopen') as default:
            self.assertTrue(run.responds(run.BACKEND_URL))
            direct.assert_called_once_with(run.BACKEND_URL, timeout=2)
            default.assert_not_called()

    def test_failed_connection_is_not_reported_as_ready(self):
        with patch.object(run.LOCAL_HTTP, 'open', side_effect=OSError('timeout')):
            self.assertFalse(run.responds(run.BACKEND_URL))

    def test_occupied_windows_port_is_detected(self):
        probe = MagicMock()
        probe.__enter__.return_value.bind.side_effect = OSError(10048, 'in use')
        with patch.object(run.socket, 'socket', return_value=probe):
            self.assertTrue(run.port_busy(8000))

    def test_free_port_is_detected(self):
        with patch.object(run.socket, 'socket', return_value=MagicMock()):
            self.assertFalse(run.port_busy(5173))

    def test_permission_error_stops_instead_of_starting_another_copy(self):
        probe = MagicMock()
        probe.__enter__.return_value.bind.side_effect = PermissionError(13, 'denied')
        with patch.object(run.socket, 'socket', return_value=probe):
            with self.assertRaisesRegex(RuntimeError, 'puerto 8000'):
                run.port_busy(8000)


if __name__ == '__main__':
    unittest.main()
