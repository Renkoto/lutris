"""Tests for the system information read without /proc, /sys and ldconfig (non-Linux systems)"""

from unittest import TestCase
from unittest.mock import patch

from lutris.util import linux, system


class TestSysctlSystemInfo(TestCase):
    def sysctl(self, name):
        return {
            "hw.model": "Intel(R) Core(TM) i7-4790 CPU @ 3.60GHz",
            "hw.ncpu": "8",
            "kern.smp.cores": "4",
            "hw.physmem": "17179869184",
            "vm.swap_total": "4294967296",
        }.get(name, "")

    def test_cpus(self):
        with patch.object(linux, "IS_LINUX", False), patch.object(linux, "_sysctl", self.sysctl):
            cpus = linux.LinuxSystem.get_cpus()
        self.assertEqual(
            cpus,
            [{"model name": "Intel(R) Core(TM) i7-4790 CPU @ 3.60GHz", "siblings": "8", "cpu cores": "4"}],
        )

    def test_ram_in_kb(self):
        with patch.object(linux, "IS_LINUX", False), patch.object(linux, "_sysctl", self.sysctl):
            ram = linux.LinuxSystem.get_ram_info()
        self.assertEqual(ram, {"MemTotal": "16777216", "SwapTotal": "4194304"})

    def test_ram_without_sysctl(self):
        with patch.object(linux, "IS_LINUX", False), patch.object(linux, "_sysctl", return_value=""):
            ram = linux.LinuxSystem.get_ram_info()
        self.assertEqual(ram, {"MemTotal": "0", "SwapTotal": "0"})

    def test_dist_and_kernel(self):
        linux_system = linux.LinuxSystem.__new__(linux.LinuxSystem)
        with (
            patch.object(linux, "IS_LINUX", False),
            patch("platform.system", return_value="FreeBSD"),
            patch("platform.release", return_value="15.1-RELEASE"),
        ):
            self.assertEqual(linux_system.get_dist_info(), ("FreeBSD", "15.1-RELEASE", ""))
            self.assertEqual(linux_system.get_kernel_version(), "15.1-RELEASE")

    def test_mounted_filesystems(self):
        output = (
            "/dev/ada0p2\t/\tufs\trw\t1\t1\n"
            "zroot/games\t/home/user/My Games\tzfs\trw,noatime\t0\t0\n"
            "devfs\t/dev\tdevfs\trw\t0\t0\n"
        )
        with patch.object(linux, "IS_LINUX", False), patch.object(system, "read_process_output", return_value=output):
            drives = linux.LinuxSystem.get_drives()
        self.assertEqual(drives[0], {"source": "/dev/ada0p2", "target": "/", "fstype": "ufs"})
        self.assertEqual(drives[1]["target"], "/home/user/My Games")
        self.assertEqual(drives[1]["fstype"], "zfs")
        self.assertEqual(len(drives), 3)

    def test_vulkan_ignores_ldconfig_outside_linux(self):
        linux_system = linux.LinuxSystem.__new__(linux.LinuxSystem)
        with (
            patch.object(linux, "IS_LINUX", False),
            patch.object(linux.vkquery, "is_vulkan_supported", return_value=True),
            patch.object(linux.LINUX_SYSTEM, "get_missing_lib_arch", return_value=["x86_64"]),
        ):
            self.assertTrue(linux_system.is_vulkan_supported())

    def test_amd64_is_x86_64(self):
        with patch("platform.machine", return_value="amd64"):
            self.assertEqual(linux.LinuxSystem.get_arch(), "x86_64")

    def test_no_ldconfig_libs(self):
        linux_system = linux.LinuxSystem.__new__(linux.LinuxSystem)
        with patch.object(linux, "IS_LINUX", False), patch.object(system, "read_process_output") as read_output:
            self.assertEqual(linux_system.get_ldconfig_libs(), [])
        read_output.assert_not_called()


class TestMissingCommands(TestCase):
    def warned_commands(self, is_linux):
        with (
            patch.object(linux, "IS_LINUX", is_linux),
            patch("shutil.which", return_value=None),
            patch.object(linux.LinuxSystem, "get_sbin_path", return_value=None),
            patch.object(linux.logger, "warning") as warning,
        ):
            linux.LinuxSystem()
        return {call.args[1] for call in warning.call_args_list if "not found" in call.args[0]}

    def test_linux_only_commands_arent_missed_elsewhere(self):
        self.assertTrue({"lspci", "ldconfig"}.isdisjoint(self.warned_commands(False)))
        self.assertIn("xrandr", self.warned_commands(False))

    def test_linux_still_reports_them(self):
        self.assertTrue({"lspci", "ldconfig"} <= self.warned_commands(True))
