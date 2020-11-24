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
        self.spincoater = None  #set externally, has two locations named "standby" and "chuck"

        self.AIRGAP = 20 #airgap, in ul, to aspirate after solution. helps avoid drips, but reduces max tip capacity
        self.DISPENSE_HEIGHT = 1 #distance between tip and bottom of wells while dispensing, mm
        self.SPINCOATING_DISPENSE_HEIGHT = 10 # distance between tip and chuck, mm
        self.DISPENSE_RATE = 5 #distance between tip and bottom of wells while dispensing, mm
        self.SPINCOATING_DISPENSE_RATE = 50 # distance between tip and chuck, mm
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

        if 'all_done' in r:
            return True
        if r['pending_requests'] > 0:
            self.process_request(
                taskid = r['taskid'],
                pipette = r['pipette'],
                function = r['function'],
                args = r['args'],
                kwargs = r['kwargs'] #keyword arguments
                )

        return False #flag to indicate whether experiment is completed

    def process_request(self, taskid, pipette, function, args, kwargs):
        if function in tasklist:
            function = tasklist[function]
        else:
            pipette = self.parse_pipette(pipette)
            function = getattr(pipette, function)

        self.taskid = taskid
        self.status = 1
        payload = {
            'status': 1,
            'taskid': taskid
        }
        r = requests.post(
                self.address,
                json = payload
            )

        function(*args, **kwargs)

        self.status = 2
        payload = {
            'status': 2,
            'taskid': taskid
        }
        r = requests.post(
                self.address,
                json = payload
            )
        if r['completion_acknowledged']:
            self.status = 0

    def parse_pipette(self, pipette):
        if type(pipette) is int:
            return(self.pipettes[pipette])

        if type(pipette) is str:
            pipette = pipette.lower()
        if pipette in ['psk', 'perovskite', 'p', 'left', 'l']:
            return self.pipettes[self.PSK_PIPETTE]
        elif pipette in ['as', 'antisolvent', 'a', 'right', 'r']:
            return self.pipettes[self.ANTISOLVENT_PIPETTE]
        else
            raise ValueError('Invalid pipette name given!')

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
            self.spincoater['standby']
            ) #moves right pipette to standby location of spincoater, which should be to the bottom left of chuck

    def dispense_onto_chuck(self, pipette, height = None, rate = None):
        if height is None:
            height = self.SPINCOATING_DISPENSE_HEIGHT
        if rate is None:
            rate = self.SPINCOATING_DISPENSE_RATE


        pipette = self.parse_pipette(pipette)
        #set dispense settings for spincoating
        pipette.well_bottom_clearance.dispense = height #set z-offset from chuck to tip, mm
        pipette.flow_rate.dispense = rate #dispense flow rate, ul/s
        
        pipette.dispense(self.spincoater['chuck'])
        
        #set dispense settings to defaults for liquid handling
        pipette.well_bottom_clearance.dispense = self.DISPENSE_HEIGHT
        pipette.flow_rate.dispense = self.DISPENSE_RATE #dispense flow rate, ul/s







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


    listener.spincoater = protocol_context.load_labware('frg_spincoater_v1', '6') #has two locations defined as "wells", called "standby" and "chuck"


    pipette.pick_up_tip()
    pipette.aspirate(10, trough.wells()['A1'])

    experiment_in_progress = True
    while experiment_in_progress:
        experiment_in_progress = listener.check_for_instructions()
        time.sleep(0.5)