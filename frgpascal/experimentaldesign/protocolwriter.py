import os
import json

MODULE_DIR = os.path.dirname(__file__)

PROTOCOL_DIR = os.path.join(MODULE_DIR, "recipes", "liquidhandlerprotocols")
AVAILABLE_PROTOCOLS = []
for fid in os.listdir(PROTOCOL_DIR):
    if fid.startswith("OT2listener_"):
        AVAILABLE_PROTOCOLS.append(fid.split("_")[1][:-3])


def generate_ot2_protocol(
    title, mixing_netlist, labware, tipracks, directory=".", base="default"
):
    if base not in AVAILABLE_PROTOCOLS:
        raise ValueError(
            f"{base} is not a valid protocol base! Available: {AVAILABLE_PROTOCOLS}"
        )
    fpath = os.path.join(directory, f"OT2PASCALProtocol_{title}.py")

    with open(
        os.path.join(
            MODULE_DIR,
            "recipes",
            "liquidhandlerprotocols",
            f"OT2listener_{base}.py",
        ),
        "r",
    ) as f:
        template_lines = [line for line in f.readlines()]

    used_deck_slots = []
    labware_str = "    labwares = {\n"
    for l in labware:
        if len(l.contents) == 0:
            continue  # no use loading an unused labware!
        if l.deck_slot in used_deck_slots:
            raise Exception(
                f"More than one labware/tiprack placed on deck slot {l.deck_slot}!"
            )
        labware_str += f'        "{l.name}": protocol_context.load_labware(\n'
        labware_str += f'            "{l.version}", location="{l.deck_slot}"\n'
        labware_str += f"        ),\n"
    labware_str += "    }"

    tiprack_str = "    tips = {\n"
    for t in tipracks:
        if t.deck_slot in used_deck_slots:
            raise Exception(
                f"More than one labware/tiprack placed on deck slot {t.deck_slot}!"
            )
        tiprack_str += f"        protocol_context.load_labware(\n"
        tiprack_str += f'            "{t.version}", location="{t.deck_slot}"\n'
        tiprack_str += f"        ):{t.unavailable_tips},\n"
    tiprack_str += "    }\n"

    with open(fpath, "w") as f:
        for line in template_lines:
            if line.startswith("mixing_netlist = []"):
                f.write(
                    f"mixing_netlist = {json.dumps(mixing_netlist, indent=4, sort_keys=True)}"
                )

            elif line.startswith("    labwares = {}"):
                f.write(labware_str)
            elif line.startswith("    tips = {}"):
                f.write(tiprack_str)
            else:
                f.write(line)

    print(f'OT2 protocol dumped to "{fpath}"')
