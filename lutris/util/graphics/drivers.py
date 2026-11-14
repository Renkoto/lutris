# pylint: disable=no-member
"""Hardware driver related utilities

Everything in this module should rely on /proc or /sys only, no executable calls
(except where those don't exist, which have to use pciconf, pcidump and sysctl)
"""

import os
import platform
import re
from collections.abc import Iterable
from typing import TypeAlias

from lutris.util import IS_LINUX, cache_single
from lutris.util.graphics.glxinfo import GlxInfo
from lutris.util.log import logger
from lutris.util.system import can_find_executable, read_process_output

MIN_RECOMMENDED_NVIDIA_DRIVER = 515


DriverGpuInfoDict: TypeAlias = dict[str, str]
DriverInfoDict: TypeAlias = dict[str, str]


def _get_nvidia_driver_info_sysctl() -> DriverInfoDict:
    """Nvidia driver information where there's no /proc/driver/nvidia, e.g. on FreeBSD"""
    version = re.search(r"\d+(\.\d+)+", read_process_output(["sysctl", "-n", "hw.nvidia.version"]))
    return {
        "vendor": "NVIDIA",
        "platform": platform.system(),
        "arch": platform.machine(),
        "version": version.group() if version else "",
    }


@cache_single
def get_nvidia_driver_info() -> DriverInfoDict:
    """Return information about Nvidia drivers"""
    if not IS_LINUX:
        return _get_nvidia_driver_info_sysctl()
    version_file_path = "/proc/driver/nvidia/version"

    def read_from_proc() -> dict[str, str]:
        try:
            if not os.path.exists(version_file_path):
                return {}
            with open(version_file_path, encoding="utf-8") as version_file:
                content = version_file.readlines()
        except PermissionError:
            # MAC systems (selinux, apparmor) may block access to files in /proc.
            # If this happens, we may still be able to retrieve the info by
            # other means, but need additional validation.
            logger.info("Could not access %s. Falling back to glxinfo.", version_file_path)
            return {}
        except OSError as e:
            logger.warning(
                "Unexpected error when accessing %s. Falling back to glxinfo.",
                version_file_path,
                exc_info=e,
            )
            return {}

        try:
            nvrm_version = content[0].split(": ")[1].strip().split()
            if "Open" in nvrm_version:
                return {
                    "vendor": nvrm_version[0],
                    "platform": nvrm_version[1],
                    "arch": nvrm_version[6],
                    "version": nvrm_version[7],
                }
            return {
                "vendor": nvrm_version[0],
                "platform": nvrm_version[1],
                "arch": nvrm_version[2],
                "version": nvrm_version[5],
                "date": " ".join(nvrm_version[6:]),
            }
        except IndexError as ex:
            logger.warning("Unable to parse %s. Falling back to glxinfo: %s", version_file_path, ex)
            return {}

    def invoke_glxinfo() -> dict[str, str]:
        glx_info = GlxInfo()
        platform = read_process_output(["uname", "-s"])
        arch = read_process_output(["uname", "-m"])
        vendor = glx_info.opengl_vendor  # type: ignore[attr-defined]
        if "nvidia" not in vendor.lower():
            raise RuntimeError("Expected NVIDIA vendor information, received %s." % vendor)
        return {
            "vendor": vendor,
            "platform": platform,
            "arch": arch,
            "version": glx_info.opengl_version.rsplit(maxsplit=1)[-1],  # type: ignore[attr-defined]
        }

    try:
        from_proc = read_from_proc()
        if from_proc:
            return from_proc
    except Exception as ex:
        logger.exception("Unable to read from '%s': %s", version_file_path, ex)

    return invoke_glxinfo()


def get_nvidia_gpu_ids() -> list[str]:
    """Return the list of Nvidia GPUs"""
    gpus_dir = "/proc/driver/nvidia/gpus"
    try:
        return os.listdir(gpus_dir)
    except PermissionError:
        logger.info("Permission denied to %s. Using lspci instead.", gpus_dir)
    except OSError as e:
        logger.warning("Unexpected error accessing %s. Using lspci instead.", gpus_dir, exc_info=e)
    # 10de is NVIDIA's vendor ID, 0300 gets you video controllers.
    values = read_process_output(["lspci", "-D", "-n", "-d", "10de::0300"]).splitlines()
    return [line.split(maxsplit=1)[0] for line in values]


def get_nvidia_gpu_info(gpu_id: str) -> DriverGpuInfoDict:
    """Return details about a GPU"""
    gpu_info_file = f"/proc/driver/nvidia/gpus/{gpu_id}/information"
    try:
        with open(gpu_info_file, encoding="utf-8") as info_file:
            content = info_file.readlines()
    except PermissionError:
        logger.info("Permission denied to %s. Detecting with lspci.", gpu_info_file)
    except OSError as e:
        logger.warning(
            "Unexpected error accessing %s. Detecting with lspci",
            gpu_info_file,
            exc_info=e,
        )
    else:
        info = {}
        for line in content:
            key, value = line.split(":", 1)
            info[key] = value.strip()
        return info
    return get_lspci_nvidia_gpu_info(gpu_id)


def get_lspci_nvidia_gpu_info(gpu_id: str) -> DriverGpuInfoDict:
    lspci_data = read_process_output(["lspci", "-v", "-s", gpu_id])
    model_info = re.search(r"NVIDIA Corporation \w+ \[(.+?)\]", lspci_data)
    if model_info:
        model = model_info.group(1)
    else:
        logger.error("Could not detect NVIDIA GPU model.")
        model = "Unknown"
    irq_info = re.search("IRQ ([0-9]+)", lspci_data)
    if irq_info:
        irq = irq_info.group(1)
    else:
        logger.error("Could not detect GPU IRQ information.")
        irq = None

    info = {
        "Model": f"NVIDIA {model}",
        "IRQ": str(irq),
        "Bus Location": str(gpu_id),
    }
    for line in lspci_data.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        info[key.strip()] = value.strip()
    return info


def is_nvidia() -> bool:
    """Return true if the Nvidia drivers are currently in use.

    Note: This function may not detect use of the nouveau drivers.
    """

    try:
        return os.path.exists("/proc/driver/nvidia")
    except OSError:
        logger.info("Could not determine whether /proc/driver/nvidia exists. Falling back to alternative method")
    try:
        with open("/proc/modules", encoding="utf-8") as proc_modules:
            modules = proc_modules.read()
        return bool(re.search(r"^nvidia ", modules, flags=re.MULTILINE))
    except OSError:
        logger.error("Could not access /proc/modules to find the Nvidia drivers. Nvidia card may not be detected.")
    glx_info = GlxInfo()
    return "NVIDIA" in glx_info.opengl_vendor  # type: ignore[attr-defined]


# What pciconf -lv prints for every device, e.g.
# vgapci0@pci0:1:0:0:	class=0x030000 rev=0xa1 hdr=0x00 vendor=0x10de device=0x128b subvendor=0x1458 subdevice=0x3532
PCICONF_DEVICE = re.compile(
    r"^(?P<driver>[a-z_]+)\d+@pci(?P<domain>\d+):(?P<bus>\d+):(?P<slot>\d+):(?P<func>\d+):\s+"
    r"class=0x(?P<class>[0-9a-f]{2})[0-9a-f]{4} .*?vendor=0x(?P<vendor>[0-9a-f]{4}) device=0x(?P<device>[0-9a-f]{4}) "
    r"subvendor=0x(?P<subvendor>[0-9a-f]{4}) subdevice=0x(?P<subdevice>[0-9a-f]{4})"
)
# What pcidump -v prints for every device (OpenBSD); the lines after the first one start with a tab
#  1:0:0: NVIDIA GK208B
# 	0x0000: Vendor ID: 10de, Product ID: 128b
# 	0x0008:	Class: 03 Display, Subclass: 00 VGA,
# 	0x002c: Subsystem Vendor ID: 1458 Product ID: 3532
PCIDUMP_DOMAIN = re.compile(r"^Domain /dev/pci(?P<domain>\d+):")
PCIDUMP_DEVICE = re.compile(r"^ (?P<bus>\d+):(?P<slot>\d+):(?P<func>\d+): (?P<name>.*)$")
PCIDUMP_IDS = re.compile(r"Vendor ID: (?P<vendor>[0-9a-f]{4}), Product ID: (?P<device>[0-9a-f]{4})")
PCIDUMP_CLASS = re.compile(r"Class: (?P<class>[0-9a-f]{2}) ")
PCIDUMP_SUBSYSTEM = re.compile(
    r"Subsystem Vendor ID: (?P<subvendor>[0-9a-f]{4}) Product ID: (?P<subdevice>[0-9a-f]{4})"
)
PCI_DISPLAY_CLASS = "03"
# The kernel driver that handles the GPUs of each PCI vendor, named as /sys/class/drm names them
PCI_VENDOR_DRIVERS = {"10de": "nvidia", "1002": "amdgpu", "8086": "i915"}


def _pci_gpu_info(ids: dict[str, str], driver: str = "", name: str = "") -> dict[str, str]:
    """Build the information of a GPU, with the keys of the uevent file of /sys/class/drm/<card>/device"""
    return {
        "DRIVER": PCI_VENDOR_DRIVERS.get(ids["vendor"], driver),
        "PCI_ID": f"{ids['vendor']}:{ids['device']}".upper(),
        "PCI_SUBSYS_ID": f"{ids.get('subvendor', '0000')}:{ids.get('subdevice', '0000')}".upper(),
        "PCI_SLOT_NAME": "%04x:%02x:%02x.%d"
        % (int(ids["domain"]), int(ids["bus"]), int(ids["slot"]), int(ids["func"])),
        "DEVICE_NAME": name,
    }


def _parse_pciconf(output: str) -> list[dict[str, str]]:
    gpus = []
    device: dict[str, str] | None = None
    for line in output.splitlines():
        if not line.startswith((" ", "\t")):
            device = None
            match = PCICONF_DEVICE.match(line)
            if match and match["class"] == PCI_DISPLAY_CLASS:
                device = _pci_gpu_info(match.groupdict(), match["driver"])
                gpus.append(device)
        elif device is not None and line.strip().startswith("device"):
            # device     = 'GK208B [GeForce GT 710]'
            device["DEVICE_NAME"] = line.partition("=")[2].strip().strip("'")
    return gpus


def _parse_pcidump(output: str) -> list[dict[str, str]]:
    gpus = []
    domain = "0"
    device: dict[str, str] | None = None

    def finish() -> None:
        if device and device.get("class") == PCI_DISPLAY_CLASS and "vendor" in device:
            gpus.append(_pci_gpu_info(device, name=device["name"]))

    for line in output.splitlines():
        if match := PCIDUMP_DOMAIN.match(line):
            finish()
            device = None
            domain = match["domain"]
        elif match := PCIDUMP_DEVICE.match(line):
            finish()
            device = {**match.groupdict(), "domain": domain}
        elif device is not None:
            for pattern in (PCIDUMP_IDS, PCIDUMP_CLASS, PCIDUMP_SUBSYSTEM):
                if match := pattern.search(line):
                    device.update(match.groupdict())
    finish()
    return gpus


# Tools that list the PCI devices, with their arguments and the parser of their output
PCI_LISTERS = (("pciconf", ["-lv"], _parse_pciconf), ("pcidump", ["-v"], _parse_pcidump))


@cache_single
def _get_pci_gpus() -> dict[str, dict[str, str]]:
    """Return the GPUs found with the PCI tool of the system, named card0, card1... like the DRM cards are"""
    for tool, args, parse in PCI_LISTERS:
        if can_find_executable(tool):
            return {"card%d" % index: gpu for index, gpu in enumerate(parse(read_process_output([tool, *args])))}
    logger.warning(
        "Can't list the GPUs, none of %s is available", ", ".join(tool for tool, _args, _parse in PCI_LISTERS)
    )
    return {}


def get_gpu_cards() -> Iterable[str]:
    """Return GPUs connected to the system"""
    if not IS_LINUX:
        yield from _get_pci_gpus()
        return

    if not os.path.exists("/sys/class/drm"):
        logger.error("No GPU available on this system!")
        return

    try:
        cardlist = os.listdir("/sys/class/drm/")
    except PermissionError:
        logger.error("Your system does not allow reading from /sys/class/drm, no GPU detected.")
        return

    for cardname in cardlist:
        if re.match(r"^card\d$", cardname):
            yield cardname


def get_gpu_info(card: str) -> dict[str, str]:
    """Return information about a GPU"""
    infos = {"DRIVER": "", "PCI_ID": "", "PCI_SUBSYS_ID": ""}
    if not IS_LINUX:
        return {**infos, **_get_pci_gpus().get(card, {})}
    try:
        with open(f"/sys/class/drm/{card}/device/uevent", encoding="utf-8") as card_uevent:
            content = card_uevent.readlines()
    except FileNotFoundError:
        logger.error("Unable to read driver information for card %s", card)
        return infos
    for line in content:
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        infos[key] = value.strip()
    return infos


def is_amd() -> bool:
    """Return true if the system uses the AMD driver"""
    for card in get_gpu_cards():
        if get_gpu_info(card)["DRIVER"] == "amdgpu":
            return True
    return False


def is_outdated() -> bool:
    if not is_nvidia():
        return False
    driver_info = get_nvidia_driver_info()
    driver_version = driver_info["version"]
    if not driver_version:
        logger.error("Failed to get Nvidia version")
        return True
    try:
        major_version = int(driver_version.split(".")[0])
    except (IndexError, ValueError) as ex:
        logger.exception("Failed to parse Nvidia version: %s", ex)
        return True
    return major_version < MIN_RECOMMENDED_NVIDIA_DRIVER
