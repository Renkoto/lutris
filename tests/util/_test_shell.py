import os
import tempfile
from unittest import TestCase
from unittest.mock import MagicMock, patch

from lutris import runner_interpreter, settings
from lutris.util import shell


class TestBashRcFile(TestCase):
    def get_script(self, home_files):
        with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as cache:
            for name in home_files:
                open(os.path.join(home, name), "w", encoding="utf-8").close()
            with (
                patch.object(settings, "CACHE_DIR", cache),
                patch("os.path.expanduser", side_effect=lambda path: path.replace("~", home)),
            ):
                script_path = shell.get_bash_rc_file("/games", {"FOO": "bar"}, {"ll": "ls -l"})
            with open(script_path, encoding="utf-8") as script_file:
                return script_file.read(), home

    def test_sources_existing_bashrc(self):
        content, home = self.get_script([".bashrc"])
        self.assertIn(". %s/.bashrc" % home, content)

    def test_missing_bashrc_isnt_sourced(self):
        content, _home = self.get_script([])
        self.assertNotIn(".bashrc", content)
        self.assertIn("export FOO=bar", content)
        self.assertIn("alias ll='ls -l'", content)
        self.assertIn("cd /games", content)


class TestExportBashScript(TestCase):
    def test_shebang_doesnt_assume_bin_bash(self):
        with tempfile.TemporaryDirectory() as folder:
            script_path = os.path.join(folder, "game.sh")
            with patch.object(runner_interpreter, "get_launch_parameters", return_value=(["game"], {})):
                runner_interpreter.export_bash_script(MagicMock(), {}, script_path)
            with open(script_path, encoding="utf-8") as script_file:
                self.assertEqual(script_file.readline(), "#!/usr/bin/env bash\n")
