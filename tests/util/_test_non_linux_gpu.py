"""Tests for the GPU detection that relies on pciconf or pcidump instead of /sys/class/drm (non-Linux systems)"""

from unittest import TestCase
from unittest.mock import patch

from lutris.util.graphics import drivers, gpu

PCICONF_OUTPUT = """\
hostb0@pci0:0:0:0:	class=0x060000 rev=0x06 hdr=0x00 vendor=0x8086 device=0x0c00 subvendor=0x1043 subdevice=0x8534
    vendor     = 'Intel Corporation'
    device     = '4th Gen Core Processor DRAM Controller'
    class      = bridge
    subclass   = HOST-PCI
vgapci0@pci0:1:0:0:	class=0x030000 rev=0xa1 hdr=0x00 vendor=0x10de device=0x128b subvendor=0x1458 subdevice=0x3532
    vendor     = 'NVIDIA Corporation'
    device     = 'GK208B [GeForce GT 710]'
    class      = display
    subclass   = VGA
vgapci1@pci0:0:2:0:	class=0x030000 rev=0x06 hdr=0x00 vendor=0x8086 device=0x0412 subvendor=0x1043 subdevice=0x8534
    vendor     = 'Intel Corporation'
    device     = 'Xeon E3-1200 v3/4th Gen Core Processor Integrated Graphics Controller'
    class      = display
    subclass   = VGA
"""

PCIDUMP_OUTPUT = """\
Domain /dev/pci0:
 0:0:0: Intel Core 4G Host
\t0x0000: Vendor ID: 8086, Product ID: 0c00
\t0x0004: Command: 0106, Status: 2090
\t0x0008:\tClass: 06 Bridge, Subclass: 00 Host,
\t\tInterface: 00, Revision: 06
\t0x002c: Subsystem Vendor ID: 1043 Product ID: 8534
 1:0:0: NVIDIA GK208B
\t0x0000: Vendor ID: 10de, Product ID: 128b
\t0x0004: Command: 0007, Status: 0010
\t0x0008:\tClass: 03 Display, Subclass: 00 VGA,
\t\tInterface: 00, Revision: a1
\t0x002c: Subsystem Vendor ID: 1458 Product ID: 3532
 2:0:0: AMD Radeon
\t0x0000: Vendor ID: 1002, Product ID: 67df
\t0x0008:\tClass: 03 Display, Subclass: 00 VGA,
Domain /dev/pci1:
 3:2:1: Intel HD Graphics
\t0x0000: Vendor ID: 8086, Product ID: 0412
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
        self.assertEqual(card["PCI_ID"], "10DE:128B")
        self.assertEqual(card["PCI_SUBSYS_ID"], "1458:3532")
        self.assertEqual(card["PCI_SLOT_NAME"], "0000:01:00.0")
        self.assertEqual(card["DEVICE_NAME"], "GK208B [GeForce GT 710]")

    def test_second_card(self):
        card = get_cards()["card1"]
        self.assertEqual((card["DRIVER"], card["PCI_ID"], card["PCI_SLOT_NAME"]), ("i915", "8086:0412", "0000:00:02.0"))

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
            self.assertEqual(drivers.get_gpu_info("card1")["PCI_ID"], "8086:0412")
            self.assertEqual(drivers.get_gpu_info("missing"), {"DRIVER": "", "PCI_ID": "", "PCI_SUBSYS_ID": ""})

    def test_gpu_class_uses_pciconf(self):
        with (
            patch.object(gpu, "IS_LINUX", False),
            patch.object(drivers, "IS_LINUX", False),
            patch.object(drivers, "_get_pci_gpus", return_value=get_cards()),
            patch.object(gpu, "VULKANINFO_PATH", None),
        ):
            card = gpu.GPU("card0")
        self.assertEqual(card.pci_id, "10de:128b")
        self.assertEqual(card.name, "GK208B [GeForce GT 710]")


class TestPcidumpGpus(TestCase):
    def test_only_display_devices_are_listed(self):
        self.assertEqual(list(get_cards(PCIDUMP_OUTPUT, "pcidump")), ["card0", "card1", "card2"])

    def test_info_has_the_keys_of_the_uevent_file(self):
        card = get_cards(PCIDUMP_OUTPUT, "pcidump")["card0"]
        self.assertEqual(card["DRIVER"], "nvidia")
        self.assertEqual(card["PCI_ID"], "10DE:128B")
        self.assertEqual(card["PCI_SUBSYS_ID"], "1458:3532")
        self.assertEqual(card["PCI_SLOT_NAME"], "0000:01:00.0")
        self.assertEqual(card["DEVICE_NAME"], "NVIDIA GK208B")

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
        output = "NVIDIA UNIX x86_64 Kernel Module  470.256.02  Thu May 2 14:37:44 UTC 2024"
        with (
            patch.object(drivers, "IS_LINUX", False),
            patch.object(drivers, "read_process_output", return_value=output),
        ):
            info = drivers.get_nvidia_driver_info.function()
        self.assertEqual(info["version"], "470.256.02")
        self.assertEqual(info["vendor"], "NVIDIA")

    def test_no_sysctl_gives_an_empty_version(self):
        with patch.object(drivers, "IS_LINUX", False), patch.object(drivers, "read_process_output", return_value=""):
            self.assertEqual(drivers.get_nvidia_driver_info.function()["version"], "")
