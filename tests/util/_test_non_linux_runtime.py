"""Tests for the runtime components that are downloaded where Linux binaries are of no use (non-Linux systems)"""

from unittest import TestCase
from unittest.mock import patch

from lutris import runtime

COMPONENTS = {
    "Ubuntu-18.04-x86_64": "Ubuntu-18.04-x86_64.tar.xz",
    "p7zip": "p7zip-16.02-x86_64.tar.gz",
    "innoextract-1.9-linux": "innoextract-1.9-linux.tar.xz",
    "network-tools": "network-tools.tar.xz",
    "umu": "umu-launcher-1.4.4-zipapp.tar",
    "umu-games": "umu-games.json.xz",
    "eac_runtime": "eac_runtime-20240114.tar.xz",
    "battleye_runtime": "battleeye_runtime.tar.xz",
    "dxvk": "dxvk-2.6.2.tar.gz",
    "vkd3d": "vkd3d-2.14.tar.xz",
    "d3d_extras": "v2.tar.xz",
    "dgvoodoo2": "dgvoodoo2-v2.8.2.tar.xz",
    "dxvk-nvapi": "dxvk-nvapi-v0.9.0.tar.xz",
    "winetricks": "winetricks-20250413-x86_64.tar.xz",
    "gogdl": "gogdl-1.1.2.tar.xz",
    "gamecontrollerdb": "gamecontrollerdb-20181215.tar.gz",
}


class TestRuntimeComponents(TestCase):
    def components(self, is_linux):
        versions = {
            "runtimes": {
                name: {"name": name, "architecture": "all", "url": "https://example.org/" + file}
                for name, file in COMPONENTS.items()
            }
        }
        with (
            patch.object(runtime, "IS_LINUX", is_linux),
            patch.object(runtime, "RuntimeExtractedComponentUpdater", side_effect=lambda info: info["name"]),
        ):
            return runtime.RuntimeUpdater._get_runtime_updaters(versions)

    def test_linux_gets_every_component(self):
        self.assertEqual(self.components(True), list(COMPONENTS))

    def test_other_systems_skip_the_linux_ones(self):
        self.assertEqual(
            self.components(False),
            ["dxvk", "vkd3d", "d3d_extras", "dgvoodoo2", "dxvk-nvapi", "gamecontrollerdb"],
        )


class TestFindWinetricks(TestCase):
    def find(self, is_linux):
        from lutris.runners.commands import wine as wine_commands

        with (
            patch.object(wine_commands, "IS_LINUX", is_linux),
            patch.object(wine_commands.system, "path_exists", return_value=True),
            patch.object(wine_commands.system, "find_required_executable", return_value="/usr/local/bin/winetricks"),
        ):
            return wine_commands.find_winetricks({"PATH": "/bin"})

    def test_linux_uses_the_runtime_winetricks(self):
        path, working_dir, env = self.find(True)
        self.assertTrue(path.endswith("winetricks/winetricks"))
        self.assertTrue(working_dir.endswith("winetricks"))
        self.assertIn(working_dir, env["PATH"])

    def test_other_systems_use_the_system_one(self):
        path, working_dir, env = self.find(False)
        self.assertEqual(path, "/usr/local/bin/winetricks")
        self.assertIsNone(working_dir)
        self.assertEqual(env["PATH"], "/bin")
