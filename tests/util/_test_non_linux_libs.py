"""Tests for the library checks that only make sense on Linux"""

from unittest import TestCase
from unittest.mock import patch

from lutris.runners import runner


class TestRequiredLibraries(TestCase):
    class NeedsLibrary(runner.Runner):
        name = "needs-library"
        require_libs = ["libdoesnotexist.so.0"]

    def test_not_checked_outside_linux(self):
        with patch.object(runner, "IS_LINUX", False):
            self.NeedsLibrary().prelaunch()

    def test_still_checked_on_linux(self):
        with patch.object(runner, "IS_LINUX", True):
            with self.assertRaises(runner.UnavailableLibrariesError):
                self.NeedsLibrary().prelaunch()
