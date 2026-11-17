import io
import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts import restart, run
from runtime_revision import source_revision


def process(pid, parent, role='uvicorn', root=None):
    root = root or restart.ROOT
    executable = str(root / '.venv-backend' / 'Scripts' / 'python.exe')
    args = '-m uvicorn main:app --app-dir backend' if role == 'uvicorn' else '-u scripts/run.py'
    return {'pid':pid, 'parent':parent, 'executable':executable, 'command':f'"{executable}" {args}'}


class RevisionTests(unittest.TestCase):
    def probe(self, payload):
        response = MagicMock()
        response.__enter__.return_value = io.StringIO(json.dumps(payload))
        return patch.object(run.LOCAL_HTTP, 'open', return_value=response)

    def test_legacy_server_requires_restart(self):
        with self.probe({'estado':'ok'}):
            with self.assertRaisesRegex(RuntimeError, 'Reiniciar-meet-notes.cmd'):
                run.ensure_current_backend()

    def test_changed_source_requires_restart(self):
        with self.probe({'revision':'old-version'}):
            with self.assertRaisesRegex(RuntimeError, 'versión anterior'):
                run.ensure_current_backend()

    def test_current_server_can_be_reused(self):
        with self.probe({'revision':run.source_revision()}):
            run.ensure_current_backend()

    def test_source_revision_changes_only_for_backend_python(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'server.py').write_text('original', encoding='utf8')
            before = source_revision(root)
            (root/'notes.txt').write_text('not code', encoding='utf8')
            self.assertEqual(before,source_revision(root))
            (root/'server.py').write_text('updated', encoding='utf8')
            self.assertNotEqual(before,source_revision(root))

    def test_stale_server_does_not_open_page_or_start_services(self):
        with patch.object(run,'responds',return_value=True), self.probe({'estado':'ok'}), \
             patch.object(run.subprocess,'Popen') as start, patch.object(run.webbrowser,'open') as browser:
            with self.assertRaisesRegex(RuntimeError,'versión anterior'):run.main()
            start.assert_not_called(); browser.assert_not_called()


class RestartTests(unittest.TestCase):
    def test_owned_backend_is_identified(self):
        self.assertEqual(restart.restart_targets([process(101,99)]),[101])

    def test_owned_launcher_is_selected_to_close_its_children(self):
        self.assertEqual(restart.restart_targets([process(101,100),process(100,99,'launcher')]),[100])

    def test_unrelated_project_is_not_stopped(self):
        unrelated = process(101,99,root=restart.ROOT.parent/'another-project')
        with self.assertRaises(RuntimeError):restart.restart_targets([unrelated])

    def test_unknown_process_or_empty_inventory_is_not_stopped(self):
        for records in ([],[{'pid':101,'parent':99,'executable':'','command':''}]):
            with self.assertRaises(RuntimeError):restart.restart_targets(records)

    def test_other_python_script_is_not_stopped(self):
        record=process(101,99);record['command']=record['command'].replace('-m uvicorn main:app --app-dir backend','another_script.py')
        with self.assertRaises(RuntimeError):restart.restart_targets([record])

    def test_processing_meeting_blocks_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            database=Path(directory)/'test.sqlite3'
            with closing(sqlite3.connect(database)) as connection:
                connection.execute('CREATE TABLE meetings (analysis_status TEXT)')
                connection.execute("INSERT INTO meetings VALUES ('procesando')")
                connection.commit()
            with patch.object(restart,'DB_PATH',database):
                with self.assertRaisesRegex(RuntimeError,'procesamiento'):restart.check_idle()

    def test_finished_meeting_does_not_block_restart_or_change_database(self):
        with tempfile.TemporaryDirectory() as directory:
            database=Path(directory)/'test.sqlite3'
            with closing(sqlite3.connect(database)) as connection:
                connection.execute('CREATE TABLE meetings (analysis_status TEXT)')
                connection.execute("INSERT INTO meetings VALUES ('listo')")
                connection.commit()
            before=database.read_bytes()
            with patch.object(restart,'DB_PATH',database):restart.check_idle()
            self.assertEqual(database.read_bytes(),before)

    def test_permission_failure_does_not_kill_any_process(self):
        denied=MagicMock(returncode=1,stdout='')
        with patch.object(restart.run,'responds',return_value=True),patch.object(restart,'check_idle'), \
             patch.object(restart.subprocess,'run',return_value=denied) as command:
            with self.assertRaisesRegex(RuntimeError,'Windows no permitió'):restart.main()
            self.assertEqual(command.call_count,1)
            self.assertEqual(command.call_args.args[0][0],'powershell.exe')

    def test_restart_closes_only_verified_launcher_then_starts_app(self):
        inventory=MagicMock(returncode=0,stdout=json.dumps([process(101,100),process(100,99,'launcher')]))
        with patch.object(restart.run,'responds',return_value=True),patch.object(restart,'check_idle'), \
             patch.object(restart.subprocess,'run',side_effect=[inventory,MagicMock(returncode=0)]) as command, \
             patch.object(restart.time,'sleep'),patch.object(restart.run,'main') as start:
            restart.main()
            self.assertEqual(command.call_args_list[1].args[0],['taskkill','/PID','100','/T','/F'])
            start.assert_called_once_with()

    def test_unidentified_inventory_never_stops_processes_or_starts_copies(self):
        inventory=MagicMock(returncode=0,stdout='[]')
        with patch.object(restart.run,'responds',return_value=True),patch.object(restart,'check_idle'), \
             patch.object(restart.subprocess,'run',return_value=inventory) as command,patch.object(restart.run,'main') as start:
            with self.assertRaises(RuntimeError):restart.main()
            self.assertEqual(command.call_count,1);start.assert_not_called()
