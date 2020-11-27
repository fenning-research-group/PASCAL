import numpy as np

def run(protocol_context): 
    tipracks = [
      protocol_context.load_labware('opentrons_96_tiprack_300ul', slot)
      for slot in ['4']
      ]

    stock = protocol_context.load_labware('frg_28_wellplate_4000ul', '1')

    mix = protocol_context.load_labware('corning_96_wellplate_360ul_flat', '2')

    pipettes = [
      protocol_context.load_instrument('p300_single', side, tip_racks=listener.tipracks)
      for side in ['left', 'right']
      ]

    for p in pipettes:
        p.min_volume = 0 #pipettes will always overfill by this number.
    
    # spincoater = protocol_context.load_labware('frg_spincoater_v1', '6') #has two locations defined as "wells", called "standby" and "chuck"

    NUM_WELLS = len(mix)
    MAX_VOLUME = 250
    MIN_VOLUME = 0
    amts = np.linspace(MAX_VOLUME, MIN_VOLUME, NUM_WELLS)

    pipettes[0].transfer(
        amts,
        plate.wells('A1'),
        mix[:NUM_WELLS],
        trash = False
        )
    pipettes[0].transfer(
        amts[::-1],
        plate.wells('B1'),
        mix[:NUM_WELLS],
        trash = False
        )

