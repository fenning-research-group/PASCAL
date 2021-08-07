import numpy as np
import json

metadata = {
	'protocolName': '96 Well Spread',
	'author': 'Rishi Kumar',
	'source': 'FRG',
	'apiLevel': '2.9'
	}

dispense_str = '{"A7": {"destination_wells": ["A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9", "A10", "A11", "A12", "B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B9", "B10", "B11", "B12", "C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9", "C10", "C11", "C12", "D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8", "D9", "D10", "D11", "D12", "E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9", "E10", "E11", "E12", "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12", "G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9", "G10", "G11", "G12", "H1", "H2", "H3", "H4", "H5", "H6", "H7", "H8", "H9", "H10", "H11", "H12"], "transfer_volumes": [48.0, 45.0, 23.0, 0.0, 30.0, 26.0, 33.0, 0.0, 10.0, 48.0, 0.0, 0.0, 57.0, 0.0, 0.0, 48.0, 10.0, 51.0, 37.0, 60.0, 24.0, 45.0, 22.0, 23.0, 15.0, 42.0, 22.0, 30.0, 23.0, 36.0, 22.0, 10.0, 54.0, 36.0, 24.0, 48.0, 15.0, 26.0, 24.0, 0.0, 30.0, 45.0, 51.0, 20.0, 10.0, 0.0, 36.0, 19.0, 8.0, 20.0, 23.0, 0.0, 0.0, 23.0, 24.0, 20.0, 20.0, 25.0, 10.0, 45.0, 0.0, 0.0, 22.0, 24.0, 22.0, 24.0, 0.0, 0.0, 36.0, 25.0, 60.0, 54.0, 0.0, 23.0, 34.0, 30.0, 39.0, 0.0, 0.0, 28.0, 0.0, 0.0, 37.0, 19.0, 8.0, 39.0, 0.0, 34.0, 28.0, 0.0, 42.0, 0.0, 33.0, 57.0, 10.0, 22.0]}, "B7": {"destination_wells": ["A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9", "A10", "A11", "A12", "B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B9", "B10", "B11", "B12", "C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9", "C10", "C11", "C12", "D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8", "D9", "D10", "D11", "D12", "E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9", "E10", "E11", "E12", "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12", "G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9", "G10", "G11", "G12", "H1", "H2", "H3", "H4", "H5", "H6", "H7", "H8", "H9", "H10", "H11", "H12"], "transfer_volumes": [0.0, 0.0, 22.0, 10.0, 0.0, 11.0, 24.0, 0.0, 10.0, 0.0, 10.0, 0.0, 0.0, 0.0, 0.0, 12.0, 0.0, 0.0, 0.0, 0.0, 36.0, 12.0, 8.0, 22.0, 22.0, 12.0, 23.0, 0.0, 28.0, 24.0, 15.0, 0.0, 0.0, 12.0, 33.0, 12.0, 22.0, 11.0, 30.0, 0.0, 24.0, 0.0, 0.0, 0.0, 0.0, 0.0, 24.0, 11.0, 22.0, 0.0, 28.0, 10.0, 0.0, 25.0, 33.0, 0.0, 0.0, 23.0, 0.0, 12.0, 0.0, 0.0, 15.0, 30.0, 8.0, 36.0, 0.0, 20.0, 12.0, 23.0, 0.0, 0.0, 0.0, 25.0, 11.0, 24.0, 12.0, 0.0, 20.0, 23.0, 10.0, 0.0, 0.0, 11.0, 22.0, 12.0, 0.0, 11.0, 23.0, 0.0, 12.0, 0.0, 24.0, 0.0, 10.0, 23.0]}, "C7": {"destination_wells": ["A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9", "A10", "A11", "A12", "B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B9", "B10", "B11", "B12", "C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9", "C10", "C11", "C12", "D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8", "D9", "D10", "D11", "D12", "E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9", "E10", "E11", "E12", "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12", "G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9", "G10", "G11", "G12", "H1", "H2", "H3", "H4", "H5", "H6", "H7", "H8", "H9", "H10", "H11", "H12"], "transfer_volumes": [12.0, 15.0, 0.0, 50.0, 30.0, 22.0, 3.0, 60.0, 40.0, 12.0, 38.0, 60.0, 3.0, 0.0, 0.0, 0.0, 12.0, 9.0, 23.0, 0.0, 0.0, 3.0, 0.0, 0.0, 22.0, 6.0, 15.0, 30.0, 0.0, 0.0, 0.0, 50.0, 6.0, 12.0, 0.0, 0.0, 22.0, 22.0, 0.0, 48.0, 6.0, 15.0, 9.0, 0.0, 12.0, 36.0, 0.0, 30.0, 30.0, 40.0, 0.0, 38.0, 36.0, 0.0, 0.0, 40.0, 0.0, 12.0, 50.0, 3.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 39.0, 12.0, 12.0, 0.0, 6.0, 48.0, 0.0, 15.0, 6.0, 9.0, 0.0, 39.0, 9.0, 50.0, 0.0, 23.0, 30.0, 30.0, 9.0, 0.0, 15.0, 9.0, 24.0, 6.0, 24.0, 3.0, 3.0, 40.0, 15.0]}, "D7": {"destination_wells": ["A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9", "A10", "A11", "A12", "B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B9", "B10", "B11", "B12", "C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9", "C10", "C11", "C12", "D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8", "D9", "D10", "D11", "D12", "E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9", "E10", "E11", "E12", "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12", "G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9", "G10", "G11", "G12", "H1", "H2", "H3", "H4", "H5", "H6", "H7", "H8", "H9", "H10", "H11", "H12"], "transfer_volumes": [0.0, 0.0, 15.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 12.0, 0.0, 0.0, 0.0, 0.0, 0.0, 38.0, 0.0, 0.0, 0.0, 0.0, 0.0, 30.0, 15.0, 0.0, 0.0, 0.0, 0.0, 9.0, 0.0, 22.0, 0.0, 0.0, 0.0, 3.0, 0.0, 0.0, 0.0, 6.0, 12.0, 0.0, 0.0, 0.0, 39.0, 38.0, 24.0, 0.0, 0.0, 0.0, 0.0, 9.0, 12.0, 24.0, 12.0, 3.0, 0.0, 39.0, 0.0, 0.0, 0.0, 0.0, 0.0, 22.0, 6.0, 30.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 12.0, 12.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 36.0, 0.0, 36.0, 0.0, 0.0, 0.0, 0.0]}}'
# isocomposition_str = [] #replace with the contents of isocomposition_list.json


def run(protocol_context): 
	tipracks = [
	  protocol_context.load_labware('opentrons_96_tiprack_300ul', slot)
	  for slot in ['8']
	  ]
	as_plate = protocol_context.load_labware('frg_12_wellplate_15000ul', '2')
	stock = protocol_context.load_labware('frg_28_wellplate_4000ul', '5')
	mix = protocol_context.load_labware('corning_96_wellplate_360ul_flat', '6')
	pipettes = [
	  protocol_context.load_instrument('p300_single_gen2', side, tip_racks=tipracks)
	  for side in ['left']
	  ]

	# protocol_context.max_speeds['A'] = 2  # limit pipette up/down axis speed, mm/s. slow is good to allow viscous solvent to wick off outside of tip on aspiration from stock solution
	pipettes[0].well_bottom_clearance.aspirate = 3 #distance (mm) above the well bottom pipette will aspirate from
	pipettes[0].well_bottom_clearance.dispense = 10 #distance (mm) pipette will dispense above the well bottom. 96 well plate depth ~= 10.68 mm


	## Mix psk precursors
	dispenses = json.loads(dispense_str)
	first_source = True
	for source_well, vals in dispenses.items():
		if first_source:
			pipettes[0].distribute(
				vals['transfer_volumes'],
				stock[source_well],
				[mix[dw] for dw in vals['destination_wells']],
				touch_tip = True,
				blow_out = True,
				disposal_volume = 0, #extra volume to aspirate, in uL.
				trash = False
				)
		else:
			pipettes[0].distribute(
				vals['transfer_volumes'], #convert L to uL
				stock[source_well],
				[mix[dw] for dw in vals['destination_wells']],
				touch_tip = True,
				blow_out = True,
				disposal_volume = 5, #extra volume to aspirate, in uL.
				trash = True
				)
		first_source = False

	## Add antisolvent
	as_amt = 150 #uL
	as_airgap_amt = 50 #uL

	as_wells = {
		'A1': 7300, #well: volume of antisolvent (uL)
		'A2': 7300
	}

	wells = []
	for v in dispenses.values():
		wells += [dw for dw,v in zip(v['destination_wells'], v['transfer_volumes']) if v > 0]
	psk_wells = set(wells)

	consumable_as_wells = (w for w in as_wells.keys())
	current_as_well = consumable_as_wells.__next__()

	pipettes[0].pick_up_tip()
	for dw in psk_wells:

		#pick AS well + aspirate
		if as_wells[current_as_well] <= as_amt*2:
			current_as_well = consumable_as_wells.__next__()
		pipettes[0].move_to(as_plate[current_as_well].top())
		protocol_context.max_speeds['Z'] = 10  # limit left pipette up/down axis speed, mm/s. slow is good to allow viscous solvent to wick off outside of tip on aspiration from stock solution
		pipettes[0].aspirate(as_amt, as_plate[current_as_well], rate=0.5) #aspirate at 20% default rate
		as_wells[current_as_well] -= as_amt
		pipettes[0].move_to(as_plate[current_as_well].top()) #slowly move back up to top
		protocol_context.max_speeds['Z'] = None #vertical travel back to default
		pipettes[0].touch_tip()
		pipettes[0].move_to(as_plate[current_as_well].top(5)) #move 5mm above top
		pipettes[0].air_gap(as_airgap_amt)

		#dispense
		pipettes[0].dispense(as_amt+as_airgap_amt, mix[dw].top(1)) #dispense from 1 mm above well
		pipettes[0].blow_out()

	pipettes[0].drop_tip()







