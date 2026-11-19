"""Tests for the GPU detection that relies on pciconf or pcidump instead of /sys/class/drm (non-Linux systems)"""

from unittest import TestCase
from unittest.mock import patch

from lutris.util.graphics import drivers, gpu

PCICONF_OUTPUT = """\
hostb0@pci0:0:0:0:	class=0x060000 rev=0x00 hdr=0x00 vendor=0x8086 device=0x0000 subvendor=0x0000 subdevice=0x0000
    vendor     = 'Fictional Vendor'
    device     = 'Fictional Host Bridge'
    class      = bridge
    subclass   = HOST-PCI
vgapci0@pci0:1:0:0:	class=0x030000 rev=0x00 hdr=0x00 vendor=0x10de device=0x0001 subvendor=0x0000 subdevice=0x0001
    vendor     = 'Fictional NVIDIA'
    device     = 'Fictional Discrete GPU'
    class      = display
    subclass   = VGA
vgapci1@pci0:0:2:0:	class=0x030000 rev=0x00 hdr=0x00 vendor=0x8086 device=0x0002 subvendor=0x0000 subdevice=0x0002
    vendor     = 'Fictional Intel'
    device     = 'Fictional Integrated GPU'
    class      = display
    subclass   = VGA
"""

PCIDUMP_OUTPUT = """\
Domain /dev/pci0:
 0:0:0: Fictional Host Bridge
\t0x0000: Vendor ID: 8086, Product ID: 0000
\t0x0004: Command: 0106, Status: 2090
\t0x0008:\tClass: 06 Bridge, Subclass: 00 Host,
\t\tInterface: 00, Revision: 00
\t0x002c: Subsystem Vendor ID: 0000 Product ID: 0000
 1:0:0: Fictional Discrete GPU
\t0x0000: Vendor ID: 10de, Product ID: 0001
\t0x0004: Command: 0007, Status: 0010
\t0x0008:\tClass: 03 Display, Subclass: 00 VGA,
\t\tInterface: 00, Revision: 00
\t0x002c: Subsystem Vendor ID: 0000 Product ID: 0001
 2:0:0: Fictional GPU Without Subsystem
\t0x0000: Vendor ID: 1002, Product ID: 0003
\t0x0008:\tClass: 03 Display, Subclass: 00 VGA,
Domain /dev/pci1:
 3:2:1: Fictional Integrated GPU
\t0x0000: Vendor ID: 8086, Product ID: 0002
\t0x0008:\tClass: 03 Display, Subclass: 00 VGA,
"""


def get_cards(output=PCICONF_OUTPUT, tool="pciconf"):
    with (
        patch.object(drivers, "IS_LINUX", False),
        patch.object(drivers, "can_find_executable", side_effect=lambda name: name == tool),
        patch.object(drivers, "read_process_output", return_value=output),
    ):
        return drivers._get_pci_gpus.function()


class TestPciconfGpus(TestCase):
    def test_only_display_devices_are_listed(self):
        self.assertEqual(list(get_cards()), ["card0", "card1"])

    def test_info_has_the_keys_of_the_uevent_file(self):
        card = get_cards()["card0"]
        self.assertEqual(card["DRIVER"], "nvidia")
        self.assertEqual(card["PCI_ID"], "10DE:0001")
        self.assertEqual(card["PCI_SUBSYS_ID"], "0000:0001")
        self.assertEqual(card["PCI_SLOT_NAME"], "0000:01:00.0")
        self.assertEqual(card["DEVICE_NAME"], "Fictional Discrete GPU")

    def test_second_card(self):
        card = get_cards()["card1"]
        self.assertEqual((card["DRIVER"], card["PCI_ID"], card["PCI_SLOT_NAME"]), ("i915", "8086:0002", "0000:00:02.0"))

    def test_no_pciconf_output(self):
        self.assertEqual(get_cards(""), {})

    def test_unknown_vendor_uses_the_attached_driver(self):
        output = PCICONF_OUTPUT.replace("vendor=0x10de", "vendor=0x1234")
        self.assertEqual(get_cards(output)["card0"]["DRIVER"], "vgapci")

    def test_cards_and_info_through_the_public_functions(self):
        with (
            patch.object(drivers, "IS_LINUX", False),
            patch.object(drivers, "_get_pci_gpus", return_value=get_cards()),
        ):
            self.assertEqual(list(drivers.get_gpu_cards()), ["card0", "card1"])
            self.assertEqual(drivers.get_gpu_info("card1")["PCI_ID"], "8086:0002")
            self.assertEqual(drivers.get_gpu_info("missing"), {"DRIVER": "", "PCI_ID": "", "PCI_SUBSYS_ID": ""})

    def test_gpu_class_uses_pciconf(self):
        with (
            patch.object(gpu, "IS_LINUX", False),
            patch.object(drivers, "IS_LINUX", False),
            patch.object(drivers, "_get_pci_gpus", return_value=get_cards()),
            patch.object(gpu, "VULKANINFO_PATH", None),
        ):
            card = gpu.GPU("card0")
        self.assertEqual(card.pci_id, "10de:0001")
        self.assertEqual(card.name, "Fictional Discrete GPU")


class TestPcidumpGpus(TestCase):
    def test_only_display_devices_are_listed(self):
        self.assertEqual(list(get_cards(PCIDUMP_OUTPUT, "pcidump")), ["card0", "card1", "card2"])

    def test_info_has_the_keys_of_the_uevent_file(self):
        card = get_cards(PCIDUMP_OUTPUT, "pcidump")["card0"]
        self.assertEqual(card["DRIVER"], "nvidia")
        self.assertEqual(card["PCI_ID"], "10DE:0001")
        self.assertEqual(card["PCI_SUBSYS_ID"], "0000:0001")
        self.assertEqual(card["PCI_SLOT_NAME"], "0000:01:00.0")
        self.assertEqual(card["DEVICE_NAME"], "Fictional Discrete GPU")

    def test_device_without_subsystem(self):
        self.assertEqual(get_cards(PCIDUMP_OUTPUT, "pcidump")["card1"]["PCI_SUBSYS_ID"], "0000:0000")

    def test_domain_is_kept_in_the_slot(self):
        self.assertEqual(get_cards(PCIDUMP_OUTPUT, "pcidump")["card2"]["PCI_SLOT_NAME"], "0001:03:02.1")

    def test_no_pcidump_output(self):
        self.assertEqual(get_cards("", "pcidump"), {})


class TestNoPciTool(TestCase):
    def test_no_tool_means_no_gpus(self):
        with (
            patch.object(drivers, "IS_LINUX", False),
            patch.object(drivers, "can_find_executable", return_value=False),
            patch.object(drivers, "read_process_output") as read_output,
        ):
            self.assertEqual(drivers._get_pci_gpus.function(), {})
        read_output.assert_not_called()


class TestNvidiaSysctl(TestCase):
    def test_version_from_sysctl(self):
        output = "Fictional NVIDIA Kernel Module  999.99.99  Thu Jan 1 00:00:00 UTC 1970"
        with (
            patch.object(drivers, "IS_LINUX", False),
            patch.object(drivers, "read_process_output", return_value=output),
        ):
            info = drivers.get_nvidia_driver_info.function()
        self.assertEqual(info["version"], "999.99.99")
        self.assertEqual(info["vendor"], "NVIDIA")

    def test_no_sysctl_gives_an_empty_version(self):
        with patch.object(drivers, "IS_LINUX", False), patch.object(drivers, "read_process_output", return_value=""):
            self.assertEqual(drivers.get_nvidia_driver_info.function()["version"], "")
