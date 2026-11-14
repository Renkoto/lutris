"""Class to manipulate a process"""

import os
import subprocess

from lutris.util import IS_LINUX
from lutris.util.log import logger

IGNORED_PROCESSES = (
    "tracker-store",
    "tracker-extract",
    "kworker",
)


class Process:
    """Python abstraction a Linux process"""

    def __init__(self, pid):
        try:
            self.pid = int(pid)
        except ValueError as err:
            raise ValueError("'%s' is not a valid pid" % pid) from err

    def __repr__(self):
        return "Process {}".format(self.pid)

    def __str__(self):
        return "{} ({}:{})".format(self.name, self.pid, self.state)

    def _read_content(self, file_path):
        """Return the contents from a file in /proc"""
        try:
            with open(file_path, encoding="utf-8", errors="replace") as proc_file:
                content = proc_file.read()
        except PermissionError:
            return ""
        except (ProcessLookupError, FileNotFoundError) as ex:
            logger.debug(ex)
            return ""
        return content.strip("\x00")

    def get_stat(self, parsed=True):
        stat_filename = "/proc/{}/stat".format(self.pid)
        try:
            with open(stat_filename, encoding="utf-8", errors="replace") as stat_file:
                _stat = stat_file.readline()
        except (ProcessLookupError, FileNotFoundError):
            return None
        if parsed:
            return _stat[_stat.rfind(")") + 1 :].split()
        return _stat

    def get_thread_ids(self):
        """Return a list of thread ids opened by process."""
        basedir = "/proc/{}/task/".format(self.pid)
        if os.path.isdir(basedir):
            try:
                return os.listdir(basedir)
            except FileNotFoundError:
                return []
        else:
            return []

    def get_children_pids_of_thread(self, tid):
        """Return pids of child processes opened by thread `tid` of process."""
        children_path = "/proc/{}/task/{}/children".format(self.pid, tid)
        try:
            with open(children_path, encoding="utf-8", errors="replace") as children_file:
                children_content = children_file.read()
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            children_content = ""
        return children_content.strip().split()

    @property
    def name(self):
        """Filename of the executable."""
        _stat = self.get_stat(parsed=False)
        if _stat:
            return _stat[_stat.find("(") + 1 : _stat.rfind(")")]
        return None

    @property
    def state(self):
        """One character from the string "RSDZTW" where R is running, S is
        sleeping in an interruptible wait, D is waiting in uninterruptible disk
        sleep, Z is zombie, T is traced or stopped (on a signal), and W is
        paging.
        """
        _stat = self.get_stat()
        if _stat:
            return _stat[0]
        return None

    @property
    def cmdline(self):
        """Return command line used to run the process `pid`."""
        cmdline_path = "/proc/{}/cmdline".format(self.pid)
        _cmdline_content = self._read_content(cmdline_path)
        if _cmdline_content:
            return _cmdline_content.replace("\x00", " ").replace("\\", "/")

    @property
    def cwd(self):
        """Return current working dir of process"""
        cwd_path = "/proc/%d/cwd" % int(self.pid)
        return os.readlink(cwd_path)

    @property
    def environ(self):
        """Return the process' environment variables"""
        environ_path = "/proc/{}/environ".format(self.pid)
        _environ_text = self._read_content(environ_path)
        if not _environ_text or "=" not in _environ_text:
            return {}
        env_vars = []
        for line in _environ_text.split("\x00"):
            if "=" not in line:
                continue
            env_vars.append(line.split("=", 1))
        return dict(env_vars)

    @property
    def children(self):
        """Return the child processes of this process"""
        _children = []
        for tid in self.get_thread_ids():
            for child_pid in self.get_children_pids_of_thread(tid):
                _children.append(Process(child_pid))
        return _children

    def iter_children(self):
        """Iterator that yields all the children of a process"""
        for child in self.children:
            yield child
            yield from child.iter_children()

    def wait_for_finish(self):
        """Waits until the process finishes
        This only works if self.pid is a child process of Lutris
        """
        try:
            pid, ret_status = os.waitpid(int(self.pid) * -1, 0)
        except OSError as ex:
            logger.error("Failed to get exit status for PID %s", self.pid)
            logger.error(ex)
            return -1
        logger.info("PID %s exited with code %s", pid, ret_status)
        return ret_status


class PsProcess(Process):
    """Process for systems without a Linux style /proc, like the BSDs.

    The information comes from ps, pgrep and procstat instead.
    """

    @staticmethod
    def _run(command):
        """Return the output of a command, or an empty string if it fails (e.g. the process is gone)"""
        try:
            return subprocess.check_output(
                command, encoding="utf-8", errors="replace", stderr=subprocess.DEVNULL, timeout=5
            ).strip()
        except (OSError, subprocess.SubprocessError):
            return ""

    def _ps(self, keyword):
        return self._run(["ps", "-ww", "-o", "%s=" % keyword, "-p", str(self.pid)])

    @property
    def name(self):
        """Filename of the executable."""
        return self._ps("comm") or None

    @property
    def state(self):
        """First character of the process state as reported by ps; like on Linux, "Z" is a zombie."""
        return self._ps("state")[:1] or None

    @property
    def cmdline(self):
        """Return command line used to run the process `pid`."""
        return self._ps("args").replace("\\", "/") or None

    @property
    def cwd(self):
        """Return current working dir of process"""
        for line in self._run(["procstat", "-f", str(self.pid)]).splitlines()[1:]:
            fields = line.split(None, 9)
            if len(fields) == 10 and fields[2] == "cwd":
                return fields[9]
        return None

    @property
    def environ(self):
        """Return the process' environment variables.

        procstat separates variables with spaces, so values that contain
        spaces are cut short; fine for looking up variables like LUTRIS_GAME_UUID.
        """
        env = {}
        for line in self._run(["procstat", "-e", str(self.pid)]).splitlines()[1:]:
            fields = line.split(None, 2)
            for variable in fields[2].split() if len(fields) == 3 else []:
                if "=" in variable:
                    key, value = variable.split("=", 1)
                    env[key] = value
        return env

    @property
    def children(self):
        """Return the child processes of this process"""
        return [type(self)(pid) for pid in self._run(["pgrep", "-P", str(self.pid)]).split()]


if not IS_LINUX:
    Process = PsProcess  # type: ignore[misc]  # noqa: F811
