import os
import json

MODULE_DIR = os.path.dirname(__file__)


def generate_ot2listenerprotocol(fpath, mixing_netlist):
    with open(
        os.path.join(
            MODULE_DIR,
            "recipes",
            "liquidhandlerprotocols",
            "OT2listener_websocket_template.py",
        ),
        "r",
    ) as f:
        template_lines = [line for line in f.readlines()]

    with open(fpath, "w") as f:
        for line in template_lines:
            if line.startswith("mixing_netlist"):
                f.write(
                    f"mixing_netlist = {json.dumps(mixing_netlist, indent=4, sort_keys=True)}"
                )
            else:
                f.write(line)
