"""
pseudocode protocol for a spin coating condition sweep, same compositions on all samples
"""

solution_sources = {
    'MAI': dict(well = 'A1', molarity = 2, solvent = 'DMSO', volume = 15000),
    'PbI2': dict(well = 'A2', molarity = 3, solvent = 'DMF', volume = 15000),
    'DMF': dict(well = 'A3', molarity = np.nan, solvent = None, volume = 15000)
}

def get_dilution(targets, sources, diluent):



    
def run():
	# labware
    trough = protocol_context.load_labware(
        'frg_10_vial_20ml_v1', '2') 
    liquid_trash = trough.wells()[-1] #use end vial as liquid trash
    plate = protocol_context.load_labware(
        'corning_96_wellplate_360ul_flat', '3')
    tiprack = [
        protocol_context.load_labware('opentrons_96_tiprack_300ul', slot)
        for slot in ['1', '4']
    ]

    pipette = protocol_context.load_instrument(
        pipette_type, mount='left', tip_racks=tiprack)

    transfer_volume = total_mixing_volume/dilution_factor
    diluent_volume = total_mixing_volume - transfer_volume
