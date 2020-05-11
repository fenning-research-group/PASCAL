"""
pseudocode protocol for a spin coating condition sweep, same compositions on all samples
"""



def run():
	"""
	# labware
    trough = protocol_context.load_labware(
        'usascientific_12_reservoir_22ml', '2')
    liquid_trash = trough.wells()[0]
    plate = protocol_context.load_labware(
        'corning_96_wellplate_360ul_flat', '3')
    tiprack = [
        protocol_context.load_labware('opentrons_96_tiprack_300ul', slot)
        for slot in ['1', '4']
    ]

    pip_name = pipette_type.split('_')[-1]

    pipette = protocol_context.load_instrument(
        pipette_type, mount='left', tip_racks=tiprack)

    transfer_volume = total_mixing_volume/dilution_factor
    diluent_volume = total_mixing_volume - transfer_volume
    """