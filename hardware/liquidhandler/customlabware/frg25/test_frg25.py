import json
from opentrons import protocol_api, types

CALIBRATION_CROSS_COORDS = {
    '1': {
        'x': 12.13,
        'y': 9.0,
        'z': 0.0
    },
    '3': {
        'x': 380.87,
        'y': 9.0,
        'z': 0.0
    },
    '7': {
        'x': 12.13,
        'y': 258.0,
        'z': 0.0
    }
}
CALIBRATION_CROSS_SLOTS = ['1', '3', '7']
TEST_LABWARE_SLOT = '3'

RATE = 0.25  # % of default speeds
SLOWER_RATE = 0.1

PIPETTE_MOUNT = 'right'
PIPETTE_NAME = 'p300_single_gen2'

TIPRACK_SLOT = '5'
TIPRACK_LOADNAME = 'opentrons_96_tiprack_300ul'

LABWARE_DEF_JSON = """{"ordering":[["A1","B1","C1","D1","E1"],["A2","B2","C2","D2","E2"],["A3","B3","C3","D3","E3"],["A4","B4","C4","D4","E4"],["A5","B5","C5","D5","E5"]],"brand":{"brand":"frg","brandId":["1"]},"metadata":{"displayName":"frg25","displayCategory":"reservoir","displayVolumeUnits":"µL","tags":[]},"dimensions":{"xDimension":127.8,"yDimension":85.5,"zDimension":10},"wells":{"A1":{"depth":5,"totalLiquidVolume":1000,"shape":"circular","diameter":5,"x":5,"y":80.5,"z":5},"B1":{"depth":5,"totalLiquidVolume":1000,"shape":"circular","diameter":5,"x":5,"y":70.5,"z":5},"C1":{"depth":5,"totalLiquidVolume":1000,"shape":"circular","diameter":5,"x":5,"y":60.5,"z":5},"D1":{"depth":5,"totalLiquidVolume":1000,"shape":"circular","diameter":5,"x":5,"y":50.5,"z":5},"E1":{"depth":5,"totalLiquidVolume":1000,"shape":"circular","diameter":5,"x":5,"y":40.5,"z":5},"A2":{"depth":5,"totalLiquidVolume":1000,"shape":"circular","diameter":5,"x":15,"y":80.5,"z":5},"B2":{"depth":5,"totalLiquidVolume":1000,"shape":"circular","diameter":5,"x":15,"y":70.5,"z":5},"C2":{"depth":5,"totalLiquidVolume":1000,"shape":"circular","diameter":5,"x":15,"y":60.5,"z":5},"D2":{"depth":5,"totalLiquidVolume":1000,"shape":"circular","diameter":5,"x":15,"y":50.5,"z":5},"E2":{"depth":5,"totalLiquidVolume":1000,"shape":"circular","diameter":5,"x":15,"y":40.5,"z":5},"A3":{"depth":5,"totalLiquidVolume":1000,"shape":"circular","diameter":5,"x":25,"y":80.5,"z":5},"B3":{"depth":5,"totalLiquidVolume":1000,"shape":"circular","diameter":5,"x":25,"y":70.5,"z":5},"C3":{"depth":5,"totalLiquidVolume":1000,"shape":"circular","diameter":5,"x":25,"y":60.5,"z":5},"D3":{"depth":5,"totalLiquidVolume":1000,"shape":"circular","diameter":5,"x":25,"y":50.5,"z":5},"E3":{"depth":5,"totalLiquidVolume":1000,"shape":"circular","diameter":5,"x":25,"y":40.5,"z":5},"A4":{"depth":5,"totalLiquidVolume":1000,"shape":"circular","diameter":5,"x":35,"y":80.5,"z":5},"B4":{"depth":5,"totalLiquidVolume":1000,"shape":"circular","diameter":5,"x":35,"y":70.5,"z":5},"C4":{"depth":5,"totalLiquidVolume":1000,"shape":"circular","diameter":5,"x":35,"y":60.5,"z":5},"D4":{"depth":5,"totalLiquidVolume":1000,"shape":"circular","diameter":5,"x":35,"y":50.5,"z":5},"E4":{"depth":5,"totalLiquidVolume":1000,"shape":"circular","diameter":5,"x":35,"y":40.5,"z":5},"A5":{"depth":5,"totalLiquidVolume":1000,"shape":"circular","diameter":5,"x":45,"y":80.5,"z":5},"B5":{"depth":5,"totalLiquidVolume":1000,"shape":"circular","diameter":5,"x":45,"y":70.5,"z":5},"C5":{"depth":5,"totalLiquidVolume":1000,"shape":"circular","diameter":5,"x":45,"y":60.5,"z":5},"D5":{"depth":5,"totalLiquidVolume":1000,"shape":"circular","diameter":5,"x":45,"y":50.5,"z":5},"E5":{"depth":5,"totalLiquidVolume":1000,"shape":"circular","diameter":5,"x":45,"y":40.5,"z":5}},"groups":[{"metadata":{"displayName":"frg25","displayCategory":"reservoir","wellBottomShape":"flat"},"brand":{"brand":"frg","brandId":["1"]},"wells":["A1","B1","C1","D1","E1","A2","B2","C2","D2","E2","A3","B3","C3","D3","E3","A4","B4","C4","D4","E4","A5","B5","C5","D5","E5"]}],"parameters":{"format":"irregular","quirks":[],"isTiprack":false,"isMagneticModuleCompatible":false,"loadName":"frg_25"},"namespace":"custom_beta","version":1,"schemaVersion":2,"cornerOffsetFromSlot":{"x":0,"y":0,"z":0}}"""
LABWARE_DEF = json.loads(LABWARE_DEF_JSON)
LABWARE_LABEL = LABWARE_DEF.get('metadata', {}).get(
    'displayName', 'test labware')

metadata = {'apiLevel': '2.0'}


def uniq(l):
    res = []
    for i in l:
        if i not in res:
            res.append(i)
    return res

def run(protocol: protocol_api.ProtocolContext):
    tiprack = protocol.load_labware(TIPRACK_LOADNAME, TIPRACK_SLOT)
    pipette = protocol.load_instrument(
        PIPETTE_NAME, PIPETTE_MOUNT, tip_racks=[tiprack])

    test_labware = protocol.load_labware_from_definition(
        LABWARE_DEF,
        TEST_LABWARE_SLOT,
        LABWARE_LABEL,
    )

    num_cols = len(LABWARE_DEF.get('ordering', [[]]))
    num_rows = len(LABWARE_DEF.get('ordering', [[]])[0])
    well_locs = uniq([
        'A1',
        '{}{}'.format(chr(ord('A') + num_rows - 1), str(num_cols))])

    pipette.pick_up_tip()

    def set_speeds(rate):
        protocol.max_speeds.update({
            'X': (600 * rate),
            'Y': (400 * rate),
            'Z': (125 * rate),
            'A': (125 * rate),
        })

        speed_max = max(protocol.max_speeds.values())

        for instr in protocol.loaded_instruments.values():
            instr.default_speed = speed_max

    set_speeds(RATE)

    for slot in CALIBRATION_CROSS_SLOTS:
        coordinate = CALIBRATION_CROSS_COORDS[slot]
        location = types.Location(point=types.Point(**coordinate),
                                  labware=None)
        pipette.move_to(location)
        protocol.pause(
            f"Confirm {PIPETTE_MOUNT} pipette is at slot {slot} calibration cross")

    pipette.home()
    protocol.pause(f"Place your labware in Slot {TEST_LABWARE_SLOT}")

    for well_loc in well_locs:
        well = test_labware.well(well_loc)
        all_4_edges = [
            [well._from_center_cartesian(x=-1, y=0, z=1), 'left'],
            [well._from_center_cartesian(x=1, y=0, z=1), 'right'],
            [well._from_center_cartesian(x=0, y=-1, z=1), 'front'],
            [well._from_center_cartesian(x=0, y=1, z=1), 'back']
        ]

        set_speeds(RATE)
        pipette.move_to(well.top())
        protocol.pause("Moved to the top of the well")

        for edge_pos, edge_name in all_4_edges:
            set_speeds(SLOWER_RATE)
            edge_location = types.Location(point=edge_pos, labware=None)
            pipette.move_to(edge_location)
            protocol.pause(f'Moved to {edge_name} edge')

        set_speeds(RATE)
        pipette.move_to(well.bottom())
        protocol.pause("Moved to the bottom of the well")

        pipette.blow_out(well)

    set_speeds(1.0)
    pipette.return_tip()
