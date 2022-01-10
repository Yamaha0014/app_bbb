#!/usr/bin/env python3
import subprocess
import shlex
import sys
import itertools
from collections import namedtuple
from shutil import copyfile
import os
import logging
import yaml
import re


_LOGGER = logging.getLogger(__name__)


def is_root():
    return True if os.geteuid() == 0 else False


def flatten(data):
    return list(itertools.chain.from_iterable(data))


def run_command(cmd):
    res = subprocess.run(cmd, capture_output=True, text=True)
    return res


Response = namedtuple("Response", "returncode value")


class Whiptail:
    def __init__(self, title="", backtitle="", height=20, width=60, auto_exit=True):
        self.title = title
        self.backtitle = backtitle
        self.height = height
        self.width = width
        self.auto_exit = auto_exit

    def run(self, control, msg, extra=(), exit_on=(1, 255)):
        cmd = [
            "whiptail",
            "--title",
            self.title,
            "--backtitle",
            self.backtitle,
            "--" + control,
            msg,
            str(self.height),
            str(self.width),
        ]
        cmd += list(extra)
        p = subprocess.Popen(cmd, stderr=subprocess.PIPE)
        out, err = p.communicate()
        if self.auto_exit and p.returncode in exit_on:
            print("User cancelled operation.")
            sys.exit(p.returncode)
        return Response(p.returncode, str(err, "utf-8", "ignore"))

    def prompt(self, msg, default="", password=False):
        control = "passwordbox" if password else "inputbox"
        return self.run(control, msg, [default]).value

    def confirm(self, msg, default="yes"):
        defaultno = "--defaultno" if default == "no" else ""
        return self.run("yesno", msg, [defaultno], [255]).returncode == 0

    def alert(self, msg):
        self.run("msgbox", msg)

    def view_file(self, path):
        self.run("textbox", path, ["--scrolltext"])

    def calc_height(self, msg):
        height_offset = 8 if msg else 7
        return [str(self.height - height_offset)]

    def menu(self, msg="", items=(), prefix=" - "):
        if isinstance(items[0], str):
            items = [(i, "") for i in items]
        else:
            items = [(k, prefix + v) for k, v in items]
        extra = self.calc_height(msg) + flatten(items)
        return self.run("menu", msg, extra).value

    def showlist(self, control, msg, items, prefix):
        if isinstance(items[0], str):
            items = [(tag, "", "OFF") for tag in items]
        else:
            items = [(tag, prefix + value, state) for tag, value, state in items]
        extra = self.calc_height(msg) + flatten(items)
        return shlex.split(self.run(control, msg, extra).value)

    def show_tag_only_list(self, control, msg, items, prefix):
        if isinstance(items[0], str):
            items = [(tag, "", "OFF") for tag in items]
        else:
            items = [(tag, "", state) for tag, value, state in items]
        extra = self.calc_height(msg) + flatten(items)
        return shlex.split(self.run(control, msg, extra).value)

    def radiolist(self, msg="", items=(), prefix=" - "):
        return self.showlist("radiolist", msg, items, prefix)[0]

    def node_radiolist(self, msg="", items=(), prefix=""):
        return self.show_tag_only_list("radiolist", msg, items, prefix)[0]

    def checklist(self, msg="", items=(), prefix=" - "):
        return self.showlist("checklist", msg, items, prefix)


def read_os_release():
    return {
        k.lower(): v.strip("'\"")
        for k, v in (
            line.strip().split("=", 1)
            for line in open("/etc/os-release").read().strip().split("\n")
        )
    }


def check_os():
    if os.path.isfile("/etc/debian_version"):
        os_data = read_os_release()
        if os_data["id"] == "debian" and int(os_data["version_id"] == 10):
            return True
        _LOGGER.error("Wrong OS type.")
        return False


def check_arch():
    uname = os.uname()
    if uname.machine == "armv7l":
        return True
    _LOGGER.error(
        "This architecture is not supported. Is it Beaglebone? %s", uname.machine
    )
    return False


class BoneIODumper(yaml.Dumper):  # pylint: disable=too-many-ancestors
    def represent_stringify(self, value):
        return self.represent_scalar(tag="tag:yaml.org,2002:str", value=str(value))

    def represent_none(self, v):
        return self.represent_scalar(tag="tag:yaml.org,2002:null", value="")


BoneIODumper.add_representer(str, BoneIODumper.represent_stringify)

BoneIODumper.add_representer(type(None), BoneIODumper.represent_none)

ON = "ON"
OFF = "OFF"
if __name__ == "__main__":
    if is_root():
        _LOGGER.error("Can't run this script as root!")
        sys.exit(1)
    if not check_os() or not check_arch():
        _LOGGER.error("Wrong operating system or CPU architecture!")
        sys.exit(1)
    if sys.version_info[:2] <= (3, 7):
        _LOGGER.error("Wrong Python version")
        exit(1)
    run_command(cmd=["sudo", "true"])
    whiptail = Whiptail(
        title="BoneIO", backtitle="Installation script", height=39, width=120
    )
    maindir = whiptail.prompt(
        msg="Where would you like to install package? Last part of directory will be created for you",
        default=f"{os.environ.get('HOME', '/home/debian')}/boneIO",
    )
    try:
        os.mkdir(maindir)
    except FileNotFoundError:
        _LOGGER.error("No such path")
        sys.exit(1)
    run_command(
        cmd=shlex.split(
            "sudo apt-get install libopenjp2-7-dev libatlas-base-dev python3-venv python3-ruamel.yaml"
        )
    )
    run_command(cmd=shlex.split(f"python3 -m venv {maindir}/venv"))
    run_command(cmd=shlex.split(f"{maindir}/venv/bin/pip3 install --upgrade boneio"))
    _configure = whiptail.confirm(
        msg="Would you like to give some basic mqtt credentials so we can configure boneio for you?"
    )
    if _configure:
        _boneio_name = whiptail.prompt("Name for this BoneIO", default="myboneio")
        _mqtt_hostname = whiptail.prompt("Type mqtt hostname", default="localhost")
        _mqtt_username = whiptail.prompt("Type mqtt username", default="mqtt")
        _mqtt_password = whiptail.prompt("Type mqtt password", password=True)
        _ha_discovery = whiptail.confirm(msg="Enable HA discovery", default="yes")
        _oled_enabled = whiptail.confirm(
            msg="Do you want OLED screen ON", default="yes"
        )
        _enabled_inputs = whiptail.checklist(
            "Inputs",
            items=[
                (
                    "Input",
                    "Enable inputs (better to edit them anyway according to your needs later)",
                    ON,
                ),
            ],
        )
        _enabled_sensors = whiptail.checklist(
            "Sensors, choose which sensors you have onboard.",
            items=[
                (
                    "LM75_RB24",
                    "Enable LM75 temperature sensor on Relay board 24x16A",
                    OFF,
                ),
                (
                    "LM75_RB32",
                    "Enable LM75 temperature sensor on Relay board 32x5A",
                    OFF,
                ),
                (
                    "MCP9808_RB32",
                    "Enable MCP9808 temperature sensor on Relay board 32x5A",
                    OFF,
                ),
                ("ADC", "Enable ADC input sensors", OFF),
            ],
        )
        _enabled_outputs = whiptail.radiolist(
            "Outputs, choose which output you want to enable.",
            items=[
                ("RB32", "Enable relay board 32x5A", OFF),
                ("RB24", "Enable relay board 24x16A", OFF),
            ],
        )
        mqtt_part = {
            "host": _mqtt_hostname,
            "topic_prefix": _boneio_name,
            "ha_discovery": {"enabled": _ha_discovery},
            "username": _mqtt_username,
            "password": _mqtt_password,
        }
        output = {"mqtt": mqtt_part}
        exampled_dir = f"{sys.path[-1]}/boneio/example_config/"
        os.makedirs(maindir, exist_ok=True)
        if _oled_enabled:
            output["oled"] = None
        if "RB24" in _enabled_outputs:
            copyfile(f"{exampled_dir}output24x16A.yaml", f"{maindir}/output24x16A.yaml")
            output["mcp23017"] = (
                [{"id": "mcp1", "address": "0x20"}, {"id": "mcp2", "address": "0x21"}],
            )
            output["output"] = "!include output24x16A.yaml"
        elif "RB32" in _enabled_outputs:
            copyfile(f"{exampled_dir}output32x5A.yaml", f"{maindir}/output32x5A.yaml")
            if "mcp23017" in output:
                output["mcp23017"].append({"id": "mcp1", "address": "0x32"})
                output["mcp23017"].append({"id": "mcp1", "address": "0x33"})
            output["mcp23017"] = [
                {"id": "mcp1", "address": "0x32"},
                {"id": "mcp2", "address": "0x33"},
            ]
            output["output"] = "!include output32x5A.yaml"
        if "LM75_RB32" in _enabled_sensors:
            output["lm75"] = {"id": "temp", "address": "0x72"}
        if "Input" in _enabled_inputs:
            copyfile(f"{exampled_dir}input.yaml", f"{maindir}/input.yaml")
            output["input"] = "!include input.yaml"
        if "ADC" in _enabled_sensors:
            copyfile(f"{exampled_dir}adc.yaml", f"{maindir}/adc.yaml")
            output["adc"] = "!include adc.yaml"

        with open(f"{maindir}/config.yaml", "w+") as file:
            result = re.sub(
                r"(.*): (')(.+)(')",
                "\\1: \\3",
                yaml.dump(
                    output,
                    default_flow_style=False,
                    allow_unicode=True,
                    sort_keys=False,
                    Dumper=BoneIODumper,
                ),
                0,
            )
            file.write(result)
    _configure = whiptail.confirm(
        msg="Would you like to create startup script for you?"
    )
    _configure = whiptail.confirm(msg="Start BoneIO at system startup automatically?")
    sys.exit(0)
