from unittest import TestCase
from unittest.mock import patch

from lutris.util import gogdl


class TestGogdlBinary(TestCase):
    def test_other_systems_use_the_one_on_the_system(self):
        with (
            patch.object(gogdl, "IS_LINUX", False),
            patch.object(gogdl.system, "find_executable", return_value="/usr/local/bin/gogdl"),
        ):
            self.assertEqual(gogdl._get_gogdl_binary(), "/usr/local/bin/gogdl")

    def test_other_systems_do_not_use_the_runtime_one(self):
        with (
            patch.object(gogdl, "IS_LINUX", False),
            patch.object(gogdl.system, "find_executable", return_value=None),
            patch.object(gogdl.os.path, "isfile", return_value=True),
        ):
            with self.assertRaises(FileNotFoundError):
                gogdl._get_gogdl_binary()

    def test_linux_ignores_the_system_one(self):
        with (
            patch.object(gogdl, "IS_LINUX", True),
            patch.object(gogdl.system, "find_executable", return_value="/usr/local/bin/gogdl") as find,
            patch.object(gogdl.os.path, "isfile", return_value=False),
        ):
            with self.assertRaises(FileNotFoundError):
                gogdl._get_gogdl_binary()
            find.assert_not_called()
