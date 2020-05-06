import string

class SampleTray:
	# def __init__(self, shape = (5,5), x0 = 10, xstep = 30, y0 = 10, ystep = 30):
	def __init__(self, shape = (5,5), x0 = 10, xstep = 30, y0 = 10, ystep = 30):
		self.slot = OrderedDict()
		for m, n in np.ndindex(shape):
			trayindex = '{}{}'.format(string.ascii_uppercase[m], n+1)
			self.slot[trayindex] = {
				'position': (x0 + n*xstep, y0 + m*ystep)
			}
		self.__queue = iter(self.slot.keys())
		self.exhausted = False

	def next(self):
		try:
			nextslot = next(self.__queue)
		except:
			nextslot = None #if all slots have been consumed, return none
			self.exhausted = True

	def export(self, fpath):
		"""
		routine to export tray data to save file. used to keep track of experimental conditions in certain tray.
		"""
		


