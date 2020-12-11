import numpy as np

metadata = {
    'protocolName': 'Food Coloring Distribution',
    'author': 'Rishi Kumar',
    'source': 'FRG',
    'apiLevel': '2.8'
    }

def run(protocol_context): 
    tipracks = [
      protocol_context.load_labware('opentrons_96_tiprack_300ul', slot)
      for slot in ['4']
      ]

    stock = protocol_context.load_labware('frg_28_wellplate_4000ul', '1')

    mix = protocol_context.load_labware('corning_96_wellplate_360ul_flat', '2')

    pipettes = [
      protocol_context.load_instrument('p300_single', side, tip_racks=tipracks)
      for side in ['left', 'right']
      ]

    # for p in pipettes:
    #     p.min_volume = 0 #pipettes will always overfill by this number.
    
    # spincoater = protocol_context.load_labware('frg_spincoater_v1', '6') #has two locations defined as "wells", called "standby" and "chuck"

    NUM_WELLS = 96
    MAX_VOLUME = 75
    MIN_VOLUME = 0
    amts = list(np.linspace(MAX_VOLUME, MIN_VOLUME, NUM_WELLS))

    pipettes[0].transfer(
        amts,
        stock.wells('A1'),
        mix.wells()[:NUM_WELLS]
        # trash = False
        )
    pipettes[0].transfer(
        amts[::-1],
        stock.wells('B1'),
        mix.wells()[:NUM_WELLS]
        # trash = False
        )

