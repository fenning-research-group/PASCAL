import string
from .geometry import Workspace


# tray constants. None = defaults
tray_versions = {
	'v1': {
		'pitch': (20,16),
		'gridsize': (8,5),
		'testslots': None,  
		'z_clearance': 5,
		'openwidth': 12
	},
	'v2': {
		'pitch': (17,13),
		'gridsize': (9,6),
		'testslots': None,  
		'z_clearance': 5,
		'openwidth': 12
	}
}
class SampleTray(Workspace):
	def __init__(self, name, num, version = 'v1', gantry = None, p0 = [None, None, None]):
		if version not in tray_versions:
			raise Exception(f'Invalid tray version "{version}" - must be in {list(tray_versions.keys())}.')
		tray_kwargs = tray_versions[version]
		super().__init__(
			name = name,
			gantry = gantry,
			p0 = p0,
			**tray_kwargs
			)

		#only consider slots with blanks loaded		
		self.slots = {
			name:{'coordinates':coord, 'payload':'blank substrate'}
			for _, (name,coord) 
			in zip(range(num), self._coordinates.items()) 
			}

		self.__queue = iter(self.slots.keys())
		self.exhausted = False
		
	def next(self):
		nextslot = next(self.__queue, None) #if no more slots left, return None
		if nextslot is None:
			self.exhausted = True

		return nextslot

	def export(self, fpath):
		"""
		routine to export tray data to save file. used to keep track of experimental conditions in certain tray.
		"""
		return None
		


