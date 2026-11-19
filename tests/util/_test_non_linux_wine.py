"""Tests for the Wine versions offered where GE-Proton, which needs umu, isn't available (non-Linux systems)"""

import os
import tempfile
from unittest import TestCase
from unittest.mock import patch

from lutris.util.wine import wine


class TestWineVersions(TestCase):
    def versions(self, is_linux, system_versions):
        with (
            patch.object(wine, "IS_LINUX", is_linux),
            patch.object(wine.proton, "list_proton_versions", return_value=[]),
            patch.object(wine, "list_lutris_wine_versions", return_value=[]),
            patch.object(wine, "list_system_wine_versions", return_value=system_versions),
        ):
            return wine.get_installed_wine_versions.function(), wine.get_default_wine_version()

    def test_linux_defaults_to_ge_proton(self):
        installed, default = self.versions(True, ["system"])
        self.assertEqual(installed, [wine.GE_PROTON_LATEST, "system"])
        self.assertEqual(default, wine.GE_PROTON_LATEST)

    def test_other_systems_dont_offer_ge_proton(self):
        installed, _default = self.versions(False, ["system"])
        self.assertEqual(installed, ["system"])

    def test_other_systems_default_to_the_system_wine(self):
        self.assertEqual(self.versions(False, ["system"])[1], "system")

    def test_without_system_wine_the_default_is_a_custom_one(self):
        self.assertEqual(self.versions(False, [])[1], "custom")


class TestSyncOptions(TestCase):
    def option(self, key):
        from lutris.runners.wine import wine as wine_runner

        return next(o for o in wine_runner.runner_options if o["option"] == key)

    def test_esync_and_fsync_are_locked_and_off_outside_linux(self):
        from lutris.runners import wine as runner_module

        with patch.object(runner_module, "IS_LINUX", False):
            esync, fsync = self.option("esync"), self.option("fsync")
            self.assertFalse(esync["condition"]())
            self.assertFalse(esync["default"]())
            self.assertFalse(fsync["condition"]())

    def test_esync_and_fsync_stay_available_on_linux(self):
        from lutris.runners import wine as runner_module

        with patch.object(runner_module, "IS_LINUX", True):
            self.assertTrue(self.option("esync")["condition"]())
            self.assertTrue(self.option("esync")["default"]())
            self.assertTrue(self.option("fsync")["condition"]())


class TestUsableWinePath(TestCase):
    """Builds with the old WoW64 mode need a 32-bit root that may be missing"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.bin_dir = os.path.join(self.tmp.name, "wine-x", "bin")
        os.makedirs(self.bin_dir)
        self.i386_root = os.path.join(self.tmp.name, "i386")
        patcher = patch.dict(os.environ, {"WINE_i386_ROOT": self.i386_root})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.wine = self.touch("wine")

    def touch(self, name, root=None):
        path = os.path.join(root or self.bin_dir, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "w").close()
        return path

    def usable(self, is_linux=False):
        with patch.object(wine, "IS_LINUX", is_linux):
            return wine.get_usable_wine_path(self.wine)

    def test_uses_the_loader_without_the_32_bit_root(self):
        self.touch("wine64")
        self.touch("wine64.bin")
        self.assertEqual(self.usable(), os.path.join(self.bin_dir, "wine64.bin"))

    def test_keeps_wine_with_the_32_bit_root(self):
        self.touch("wine64.bin")
        self.touch("bin/wine", root=self.i386_root + os.path.dirname(self.bin_dir))
        self.assertEqual(self.usable(), self.wine)

    def test_keeps_wine_when_the_build_has_no_loader(self):
        self.assertEqual(self.usable(), self.wine)

    def test_keeps_wine_on_linux(self):
        self.touch("wine64.bin")
        self.assertEqual(self.usable(is_linux=True), self.wine)

    def test_keeps_wine_from_the_path(self):
        with patch.object(wine, "IS_LINUX", False):
            self.assertEqual(wine.get_usable_wine_path("wine"), "wine")

    def test_wineboot_runs_through_the_loader(self):
        loader = os.path.join(self.bin_dir, wine.WINE64_LOADER)
        self.assertEqual(wine.get_wineboot_command(loader), [loader, "wineboot"])

    def test_wineboot_is_the_link_next_to_wine(self):
        self.assertEqual(wine.get_wineboot_command(self.wine), [os.path.join(self.bin_dir, "wineboot")])
