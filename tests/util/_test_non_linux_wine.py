"""Tests for the Wine versions offered where GE-Proton, which needs umu, isn't available (non-Linux systems)"""

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
