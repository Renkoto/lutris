from unittest import TestCase
from unittest.mock import patch

from lutris.util import nvidia


class TestNvidiaGlxPath(TestCase):
    def libraries_loaded(self, is_linux):
        loaded = []

        def fake_cdll(name):
            loaded.append(name)
            if name == "libGLX_nvidia.so.0":
                raise OSError("not installed")
            return object()

        with patch.object(nvidia, "IS_LINUX", is_linux), patch.object(nvidia, "CDLL", fake_cdll):
            self.assertIsNone(nvidia.get_nvidia_glx_path())
        return loaded

    def test_linux_loads_libdl(self):
        self.assertEqual(self.libraries_loaded(True), ["libdl.so.2", "libGLX_nvidia.so.0"])

    def test_other_systems_use_the_c_library(self):
        self.assertEqual(self.libraries_loaded(False), [None, "libGLX_nvidia.so.0"])
