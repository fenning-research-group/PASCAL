import os
import json

# from typing import Literal #python 3.8
from typing_extensions import Literal  # python <3.8


MODULE_DIR = os.path.dirname(__file__)

PROTOCOL_DIR = os.path.join(MODULE_DIR, "recipes", "liquidhandlerprotocols")
AVAILABLE_PROTOCOLS = []
for fid in os.listdir(PROTOCOL_DIR):
    if fid.startswith("OT2Listener_"):
        AVAILABLE_PROTOCOLS.append(fid.split("_")[1][:-3])


def generate_ot2_protocol(
    title,
    mixing_netlist,
    labware,
    tipracks_300,
    tipracks_1000,
    directory=".",
    template=Literal["samepipettebothsides", "1000left300right"],
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
