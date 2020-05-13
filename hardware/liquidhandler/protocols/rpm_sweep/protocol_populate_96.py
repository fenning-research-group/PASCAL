"""
pseudocode protocol for a spin coating condition sweep, same compositions on all samples
"""

solution_sources = {
    'MA_Pb_I3': dict(well = 'A1', molarity = 1.5, solvent = dict(DMSO = 9, DMF = 1), volume = 15000),
    'Cs_I': dict(well = 'A2', molarity = 3, solvent = dict(DMSO = 1), volume = 15000),
    'FA_Pb_I3': dict(well = 'A3', molarity = 1.5, solvent = dict(DMSO = 9, DMF = 1), volume = 15000)
}

def get_components(name, delimiter = '_'):
    components = {}
    for part in name.split(delimiter):
        species = part
        count = 1.0
        for l in range(len(part), 0, -1):
            try:
                count = float(part[-l:])
                species = part[:l]
                break
            except:
                pass
        components[species] = count
    return components


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
