"""Tests for finding the extraction tools where the runtime's Linux binaries can't run (non-Linux systems)"""

import os
import tempfile
from unittest import TestCase
from unittest.mock import patch

from lutris.util import extract


class TestExtractionTools(TestCase):
    def setUp(self):
        self.runtime = tempfile.TemporaryDirectory()
        self.addCleanup(self.runtime.cleanup)
        for path in ("p7zip/7z", "innoextract-1.9/innoextract"):
            full_path = os.path.join(self.runtime.name, path)
            os.makedirs(os.path.dirname(full_path))
            open(full_path, "w").close()
        for target, value in (
            (extract.settings, {"RUNTIME_DIR": self.runtime.name}),
            (extract.system, {"find_required_executable": lambda name: "/usr/local/bin/" + name}),
        ):
            for key, attr in value.items():
                patcher = patch.object(target, key, attr)
                patcher.start()
                self.addCleanup(patcher.stop)

    def tools(self, is_linux):
        with patch.object(extract, "IS_LINUX", is_linux):
            return extract._get_7zip_path(), extract._get_innoextract_path()

    def test_linux_prefers_the_runtime(self):
        self.assertEqual(
            self.tools(True),
            (
                os.path.join(self.runtime.name, "p7zip/7z"),
                os.path.join(self.runtime.name, "innoextract-1.9/innoextract"),
            ),
        )

    def test_other_systems_use_the_installed_tools(self):
        self.assertEqual(self.tools(False), ("/usr/local/bin/7z", "/usr/local/bin/innoextract"))
