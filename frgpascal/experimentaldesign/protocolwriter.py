import os
import json
import yaml
# from typing import Literal #python 3.8
from typing_extensions import Literal  # python <3.8
from datetime import datetime

MODULE_DIR = os.path.dirname(__file__)

PROTOCOL_DIR = os.path.join(MODULE_DIR, "recipes", "liquidhandlerprotocols")
AVAILABLE_PROTOCOLS = []
for fid in os.listdir(PROTOCOL_DIR):
    if fid.startswith("OT2Listener_"):
        AVAILABLE_PROTOCOLS.append(fid.split("_")[1][:-3])
HARDWARE_DIR = os.path.join(os.path.dirname(MODULE_DIR), "hardware", "hardwareconstants.yaml")
with open(HARDWARE_DIR, "r") as f:
    constants = yaml.load(f, Loader=yaml.FullLoader)["liquidhandler"]
v_ = constants["velocity"]
a_ = constants["acceleration"]
p_ = constants["pipette"]

def generate_ot2_protocol(
    title,
    mixing_netlist,
    labware,
    tipracks_300,
    tipracks_1000,
    directory=".",
    template=Literal["samepipettebothsides", "1000left300right", "1000left300right-lightsON"],
):
    if template not in AVAILABLE_PROTOCOLS:
        raise ValueError(
            f"{template} is not a valid protocol template! Available: {AVAILABLE_PROTOCOLS}"
        )
    fpath = os.path.join(directory, f"OT2PASCALProtocol_{title}.py")

    labware = [
        l for l in labware if len(l.contents) > 0
    ]  # no use loading an unused labware!
    used_deck_slots = (
        [l.deck_slot for l in labware]
        + [t.deck_slot for t in tipracks_300]
        + [t.deck_slot for t in tipracks_1000]
    )
    if len(used_deck_slots) != len(set(used_deck_slots)):
        raise Exception("More than one labware/tiprack placed on the same deck slot!")

    with open(
        os.path.join(
            MODULE_DIR,
            "recipes",
            "liquidhandlerprotocols",
            f"OT2listener_{template}.py",
        ),
        "r",
    ) as f:
        template_lines = [line for line in f.readlines()]

    labware_str = "    labwares = {\n"
    for l in labware:
        labware_str += f'        "{l.name}": protocol_context.load_labware(\n'
        labware_str += f'            "{l.version}", location="{l.deck_slot}"\n'
        labware_str += f"        ),\n"
    labware_str += "    }"

    tiprack_300_str = "    tips_300 = {\n"
    for t in tipracks_300:
        tiprack_300_str += f"        protocol_context.load_labware(\n"
        tiprack_300_str += f'            "{t.version}", location="{t.deck_slot}"\n'
        tiprack_300_str += f"        ):{t.unavailable_tips},\n"
    tiprack_300_str += "    }\n"

    tiprack_1000_str = "    tips_1000 = {\n"
    for t in tipracks_1000:
        tiprack_1000_str += f"        protocol_context.load_labware(\n"
        tiprack_1000_str += f'            "{t.version}", location="{t.deck_slot}"\n'
        tiprack_1000_str += f"        ):{t.unavailable_tips},\n"
    tiprack_1000_str += "    }\n"

    with open(fpath, "w") as f:
        for line in template_lines:
            if line.startswith("mixing_netlist = []"):
                f.write(
                    f"mixing_netlist = {json.dumps(mixing_netlist, indent=4, sort_keys=True)}"
                )

            elif line.startswith("    labwares = {}"):
                f.write(labware_str)
            elif line.startswith("    tips_300 = {}"):
                f.write(tiprack_300_str)
            elif line.startswith("    tips_1000 = {}"):
                f.write(tiprack_1000_str)
            else:
                f.write(line)

    print(f'OT2 protocol dumped to "{fpath}"')

new_config_lines = [
    "from typing import Tuple\n",
    "from dataclasses import dataclass, fields, _MISSING_TYPE, field\n",
    "@dataclass\n",
    "class OT2VelocitySettings:\n",
    '   """dataclass for restricting form of velocity variables to be fed into the OT-2."""\n',
    f"   X: float = {v_['X']}\n",
    f"   Y: float = {v_['Y']}\n",
    f"   Z: float = {v_['Z']}\n",
    f"   A: float = {v_['A']}\n",
    f"   B: float = {v_['B']}\n",
    f"   C: float = {v_['C']}\n",
    "\n",
    "   def __post_init__(self):\n",
    "       for field_ in fields(self):\n",
    "           # If there is a default and the value of the field is missing, then we can assign a value\n",
    "           if not isinstance(field_.default, _MISSING_TYPE) and getattr(self, field_.name) is None:\n",
    "               setattr(self, field_.name, field_.default)\n",
    "\n",
    "@dataclass\n",
    "class OT2AccelerationSettings:\n",
    '   """dataclass for restricting form of acceleration variables to be fed into the OT-2."""\n',
    f"   X: float = {a_['X']}\n",
    f"   Y: float = {a_['Y']}\n",
    f"   Z: float = {a_['Z']}\n",
    f"   A: float = {a_['A']}\n",
    f"   B: float = {a_['B']}\n",
    f"   C: float = {a_['C']}\n",
    "\n",
    "   def __post_init__(self):\n",
    "       for field_ in fields(self):\n",
    "           # If there is a default and the value of the field is missing, then we can assign a value\n",
    "           if not isinstance(field_.default, _MISSING_TYPE) and getattr(self, field_.name) is None:\n",
    "               setattr(self, field_.name, field_.default)\n",
    "\n",
    "@dataclass\n",
    "class OT2MotionConfig:\n",
    '   """dataclass for storing properties used for programmatically adjusting OT-2 motion."""\n',
    "   # Liquid Arm Motion\n",
    "   velocities: OT2VelocitySettings = field(\n",
    "       default_factory = OT2VelocitySettings)\n",
    "   accelerations: OT2AccelerationSettings = field(\n",
    "       default_factory = OT2AccelerationSettings)\n",
    "   # Motion Execution:\n",
    f"   SLOW_Z_RATE: float = {p_['slow_z_rate']}\n",
    f"   SLOW_XY_RATE: float = {p_['slow_xy_rate']}\n",
    f"   SLOWEST_XY_RATE: float = {p_['slowest_xy_rate']}"
    "   # Pipette Actions:\n",
    f"   AIRGAP: float = {p_['airgap']} # airgap, in uL, to aspirate after drawing solution. Helps avoid drips, but reduces max tip capacity.\n",
    f"   ASPIRATE_HEIGHT: float = {p_['aspirate_height']}\n",
    f"   DISPENSE_HEIGHT: float = {p_['dispense_height']}\n",
    f"   DISPENSE_RATE: float = {p_['dispense_rate']}\n",
    f"   SPINCOATING_DISPENSE_HEIGHT: float = {p_['spincoating_dispense_height']}\n"
    f"   SPINCOATING_DISPENSE_RATE: float = {p_['spincoating_dispense_rate']}\n"
    f"   TOUCH_TIP_RATE: float = {p_['touch_tip_rate']}\n"
    "   # position planning:\n",
    "   CLEARCHUCKPOSITION: Tuple[float] = (\n",
    f"       {p_['clear_chuck']['X']},\n",
    f"       {p_['clear_chuck']['Y']},\n",
    f"       {p_['clear_chuck']['Z']},\n",
    "   ) # mm, 0,0,0 = front left floor corner of ot-2 gantry's working volume.\n",
    "\n",
    "   def __post_init__(self):\n",
    "       for field_ in fields(self):\n",
    "           # If there is a default and the value of the field is missing, then we can assign a value\n",
    "           if not isinstance(field_.default, _MISSING_TYPE) and getattr(self, field_.name) is None:\n",
    "               setattr(self, field_.name, field_.default)\n",
]
config_prop_lines = [
    "    @property\n",
    "    def config(self):\n",
    "        return self._config\n"
]
def generate_ot2_protocolNEW(
    title,
    mixing_netlist,
    labware,
    tipracks_300,
    tipracks_1000,
    directory=".",
    template=Literal["samepipettebothsides", "1000left300right", "1000left300right-lightsON", "1000left300right-NOSHAKES"],
):
    if template not in AVAILABLE_PROTOCOLS:
        raise ValueError(
            f"{template} is not a valid protocol template! Available: {AVAILABLE_PROTOCOLS}"
        )
    fpath = os.path.join(directory, f"OT2PASCALProtocol_{title}_NEW.py")

    labware = [
        l for l in labware if len(l.contents) > 0
    ]  # no use loading an unused labware!
    used_deck_slots = (
        [l.deck_slot for l in labware]
        + [t.deck_slot for t in tipracks_300]
        + [t.deck_slot for t in tipracks_1000]
    )
    if len(used_deck_slots) != len(set(used_deck_slots)):
        raise Exception("More than one labware/tiprack placed on the same deck slot!")

    with open(
        os.path.join(
            MODULE_DIR,
            "recipes",
            "liquidhandlerprotocols",
            f"OT2listener_{template}.py",
        ),
        "r",
    ) as f:
        template_lines = [line for line in f.readlines()]
    temp_lines = []
    for line in template_lines:
        if line == "File Created At:\n":
            line = "File Created At: "
            line += datetime.now().strftime("%B %d, %Y %I:%M:%S %p") + " PST\n"
        if '==Done Importing==' in line:
            # add on all of the motion config code
            for new in new_config_lines:
                temp_lines.append(new)
        if "config, #==Update Default Config==" in line:
            new = "        config = OT2Config,\n"
            line = new
        if "self.config = config #==Add Config to ListenerWebsocket==" in line:
            new = "        self._config = config\n"
            line = new
        temp_lines.append(line)
        if "==Define Config Property==" in line:
            for new in config_prop_lines:
                temp_lines.append(new)
    template_lines = temp_lines
    labware_str = "    labwares = {\n"
    for l in labware:
        labware_str += f'        "{l.name}": protocol_context.load_labware(\n'
        labware_str += f'            "{l.version}", location="{l.deck_slot}"\n'
        labware_str += f"        ),\n"
    labware_str += "    }"

    tiprack_300_str = "    tips_300 = {\n"
    for t in tipracks_300:
        tiprack_300_str += f"        protocol_context.load_labware(\n"
        tiprack_300_str += f'            "{t.version}", location="{t.deck_slot}"\n'
        tiprack_300_str += f"        ):{t.unavailable_tips},\n"
    tiprack_300_str += "    }\n"

    tiprack_1000_str = "    tips_1000 = {\n"
    for t in tipracks_1000:
        tiprack_1000_str += f"        protocol_context.load_labware(\n"
        tiprack_1000_str += f'            "{t.version}", location="{t.deck_slot}"\n'
        tiprack_1000_str += f"        ):{t.unavailable_tips},\n"
    tiprack_1000_str += "    }\n"

    with open(fpath, "w") as f:
        for line in template_lines:
            if line.startswith("mixing_netlist = []"):
                f.write(
                    f"mixing_netlist = {json.dumps(mixing_netlist, indent=4, sort_keys=True)}"
                )

            elif line.startswith("    labwares = {}"):
                f.write(labware_str)
            elif line.startswith("    tips_300 = {}"):
                f.write(tiprack_300_str)
            elif line.startswith("    tips_1000 = {}"):
                f.write(tiprack_1000_str)
            else:
                f.write(line)

    print(f'OT2 protocol dumped to "{fpath}"')
