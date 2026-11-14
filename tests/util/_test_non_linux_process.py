"""Tests for the process handling used where there is no Linux style /proc (non-Linux systems)"""

import importlib.machinery
import importlib.util
import os
import subprocess
import sys
from unittest import TestCase
from unittest.mock import patch

from lutris.util import system
from lutris.util.process import Process, PsProcess
from lutris.util.wine import fsync

PROCSTAT_FILES = """\
  PID COMM                FD T V FLAGS    REF  OFFSET PRO NAME
 4242 wine               text v r r-------   -       - -   /usr/local/bin/wine
 4242 wine                cwd v d r-------   -       - -   /home/user/Games/My Game
 4242 wine               root v d r-------   -       - -   /
"""

PROCSTAT_ENV = """\
  PID COMM             ENVIRONMENT
 4242 wine             HOME=/home/user LUTRIS_GAME_UUID=abc-123 PATH=/bin:/usr/bin
"""


def fake_run(outputs):
    """Make a PsProcess._run replacement answering by the name of the command"""

    def run(command):
        # ps commands are told apart by the field they ask for, e.g. "comm="
        return outputs.get(command[3] if command[0] == "ps" else command[0], "")

    return run


class TestPsProcess(TestCase):
    def setUp(self):
        self.process = PsProcess(4242)

    def test_basic_fields(self):
        outputs = {"comm=": "wine", "state=": "Ss+", "args=": "wine C:\\game\\game.exe"}
        with patch.object(PsProcess, "_run", side_effect=fake_run(outputs)):
            self.assertEqual(self.process.name, "wine")
            self.assertEqual(self.process.state, "S")
            self.assertEqual(self.process.cmdline, "wine C:/game/game.exe")

    def test_missing_process_has_no_fields(self):
        with patch.object(PsProcess, "_run", return_value=""):
            self.assertIsNone(self.process.name)
            self.assertIsNone(self.process.state)
            self.assertIsNone(self.process.cmdline)
            self.assertIsNone(self.process.cwd)
            self.assertEqual(self.process.environ, {})
            self.assertEqual(self.process.children, [])

    def test_cwd_keeps_spaces(self):
        with patch.object(PsProcess, "_run", return_value=PROCSTAT_FILES):
            self.assertEqual(self.process.cwd, "/home/user/Games/My Game")

    def test_environ(self):
        with patch.object(PsProcess, "_run", return_value=PROCSTAT_ENV):
            self.assertEqual(self.process.environ["LUTRIS_GAME_UUID"], "abc-123")
            self.assertEqual(self.process.environ["HOME"], "/home/user")

    def test_children(self):
        with patch.object(PsProcess, "_run", return_value="101\n102"):
            self.assertEqual([child.pid for child in self.process.children], [101, 102])

    def test_run_swallows_failures(self):
        with patch("subprocess.check_output", side_effect=subprocess.CalledProcessError(1, "pgrep")):
            self.assertEqual(PsProcess._run(["pgrep", "-P", "1"]), "")
        with patch("subprocess.check_output", side_effect=FileNotFoundError("procstat")):
            self.assertEqual(PsProcess._run(["procstat", "-e", "1"]), "")

    def test_linux_keeps_the_proc_implementation(self):
        if sys.platform.startswith("linux"):
            self.assertIsNot(Process, PsProcess)


class TestPidHelpers(TestCase):
    def test_running_pid_list_uses_ps(self):
        with (
            patch.object(system, "IS_LINUX", False),
            patch.object(system, "read_process_output", return_value="1\n  22\n333") as read_output,
        ):
            self.assertEqual(system.get_running_pid_list(), [1, 22, 333])
        self.assertEqual(read_output.call_args.args[0][0], "ps")

    def test_pid_exists_without_proc(self):
        finished = subprocess.Popen([sys.executable, "-c", "pass"])
        finished.wait()
        with patch.object(system, "IS_LINUX", False):
            self.assertTrue(system.pid_exists(os.getpid()))
            self.assertFalse(system.pid_exists(finished.pid))


class TestFsync(TestCase):
    def test_not_supported_outside_linux(self):
        with (
            patch.object(fsync, "IS_LINUX", False),
            patch.object(fsync, "is_futex_waitv_supported") as waitv,
        ):
            # Call the undecorated function so the cached result isn't touched
            self.assertFalse(fsync.get_fsync_support.function())
        waitv.assert_not_called()


def load_wrapper():
    path = os.path.join(os.path.dirname(__file__), "..", "..", "share", "lutris", "bin", "lutris-wrapper")
    loader = importlib.machinery.SourceFileLoader("lutris_wrapper", path)
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader("lutris_wrapper", loader))
    loader.exec_module(module)
    return module


class TestWrapperSubreaper(TestCase):
    def setUp(self):
        self.wrapper = load_wrapper()

    def test_freebsd_uses_procctl(self):
        with (
            patch.object(sys, "platform", "freebsd15"),
            patch.object(self.wrapper, "set_child_reaper_freebsd") as reaper,
            patch.object(self.wrapper.ctypes, "CDLL") as cdll,
        ):
            self.wrapper.set_child_subreaper()
        reaper.assert_called_once()
        cdll.assert_not_called()

    def test_other_systems_skip_prctl(self):
        with patch.object(sys, "platform", "openbsd7"), patch.object(self.wrapper.ctypes, "CDLL") as cdll:
            self.wrapper.set_child_subreaper()
        cdll.assert_not_called()
