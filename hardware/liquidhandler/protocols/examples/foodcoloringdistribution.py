import numpy as np
from opentrons import types


metadata = {
    "protocolName": "Food Coloring Distribution",
    "author": "Rishi Kumar",
    "source": "FRG",
    "apiLevel": "2.10",
}


def run(protocol_context):
    tipracks = [
        protocol_context.load_labware("sartorius_safetyspace_tiprack_200ul", slot)
        for slot in ["8"]
    ]

    stock = protocol_context.load_labware("frg_12_wellplate_15000ul", "9")

    mix = protocol_context.load_labware("greiner_96_wellplate_360ul", "6")

    pipettes = {
        side: protocol_context.load_instrument(
            "p300_single_gen2", side, tip_racks=tipracks
        )
        for side in ["left", "right"]
    }

    # for p in pipettes:
    #     p.min_volume = 0 #pipettes will always overfill by this number.

    # spincoater = protocol_context.load_labware('frg_spincoater_v1', '6') #has two locations defined as "wells", called "standby" and "chuck"

    pipettes["right"].move_to(
        location=types.Location(point=types.Point(200, 100, 100), labware=None)
    )
    # NUM_WELLS = 8
    # MAX_VOLUME = 50
    # MIN_VOLUME = 20
    # amts = list(np.linspace(MAX_VOLUME, MIN_VOLUME, NUM_WELLS).round(3))

    # pipettes['left'].transfer(
    #     amts,
    #     stock.wells('A1'),
    #     mix.wells()[:NUM_WELLS],
    #     touch_tip=True,
    #     # blow_out=True,
    #     # blowout_location='source well',
    #     air_gap = 10
    #     # trash = False
    #     )
    # pipettes['right'].transfer(
    #     amts[::-1],
    #     stock.wells('A2'),
    #     mix.wells()[:NUM_WELLS],
    #     touch_tip=True,
    #     blow_out=True,
    #     blowout_location='source well'
    #     )
