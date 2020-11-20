import requests # you can install this with pip

class Listener:
    def __init__(self, address):
        self.address = address
        self.experiment_in_progress = True
        self.status = 0 #liquid handler status key: 0 = idle, 1 = actively working on task, 2 = completed task, waiting for maestro to acknowlegde
        self.currenttask = None
        self.tipracks = None    #will be set externally in run(). can be any number
        self.stock = None       #set externally. assumes only one stock wellplate!
        self.pipettes = None    #set externally. assumes two pipettes.
        self.spincoater = None  #set externally, has two locations named "staging" and "chuck"

        self.AIRGAP = 20 #airgap, in ul, to aspirate after solution. helps avoid drips, but reduces max tip capacity
        
        self.ANTISOLVENT_PIPETTE = 0 #default left pipette for antisolvent
        self.PSK_PIPETTE = 1 #default right for psk

        self.tasklist = {
            'aspirate_for_spincoating': self.aspirate_for_spincoating,
            'drop_psk': self.drop_psk,
            'drop_as': self.drop_as,
            ''
        }
    def check_for_instructions(self):
        payload = {
            'status': 0,
        }

        r = requests.post(
            self.address,
            json=payload
            )

        if r['pending_request'] != 0:
            self.process_request(
                taskid = r['taskid'],
                pipette = r['pipette'],
                function = r['function'],
                args = r['args'],
                kwargs = r['kwargs'] #keyword arguments
                )

    def process_request(self, taskid, pipette, function, arguments):
        self.current_task = taskid
        self.status = 1



    def aspirate_for_spincoating(self, psk_well, psk_volume, as_well, as_volume):
        for p in self.pipettes:
            p.pick_up_tip()

        self.pipettes[self.PSK_PIPETTE].aspirate(
            psk_volume, 
            self.stock.wells()[psk_well]
            )

        self.pipettes[self.PSK_PIPETTE].air_gap(self.AIRGAP)

        self.pipettes[self.ANTISOLVENT_PIPETTE].aspirate(
            as_volume, 
            self.stock.wells()[as_well]
            )
        self.pipettes[self.ANTISOLVENT_PIPETTE].air_gap(self.AIRGAP)

        self.pipettes[1].move_to(
            self.spincoater['staging']
            ) #moves right pipette to staging location of spincoater, which should be to the bottom left of chuck

        self.status = 2









def run(protocol): 
    listener = Listener()

    listener.tipracks = [
      protocol_context.load_labware('opentrons_96_tiprack_300ul', slot)
      for slot in ['1']
      ]

    listener.stock = protocol_context.load_labware('frg_10_vial_20ml_v1', '2')
    listener.pipettes = [
      protocol.load_instrument('p300_single', side, tip_racks=tipracks)
      for side in ['left', 'right']
      ]


    listener.spincoater = protocol_context.load_labware('frg_spincoater_v1', '6') #has two locations defined as "wells", called "staging" and "chuck"


    pipette.pick_up_tip()
    pipette.aspirate(10, trough.wells()['A1'])

    experiment_in_progress = True
    while experiment_in_progress:

    done = False   # Poll to see if the server wants you to proceed
    while not done:
    r = requests.post('http://127.0.0.1/update', json={'step': 'done-aspirating'}) 
    done = r.json()['done'] 

    pipette.dispense() 