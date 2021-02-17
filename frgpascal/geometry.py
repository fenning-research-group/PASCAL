import numpy as np
from scipy.interpolate import LinearNDInterpolator

class CoordinateMapper: 
	"""Transforms from one coordinate system (source) to another (destination)
		Assumes the two coordinate systems are nearly parallel - can handle some rotation,
		but otherwise just does translation in xy. Actually projects xy plane with z offset,
		so this will have issues under severe rotation.
	"""
	def __init__(self, p0, p1): 
		self.destination = np.asarray(p1) 
		self.source = np.asarray(p0) 
		self.xyoffset = (self.destination.mean(axis = 0) - self.source.mean(axis = 0)) 
		self.xyoffset[2] = 0 #no z offset, but keep in 3d 
		self.zinterp = LinearNDInterpolator(self.source[:,:2], self.source[:,2]) 
		
	def map(self, p): 
		if len(p) == 2:
			p = list(p)
			p.append(0)
		p = np.asarray(p) 
		pmap = p - self.xyoffset 
		pmap[2] = self.zinterp(pmap[:2]) 
		return pmap              

def map_coordinates(slots, points, gantry, z_clearance = 5):
	"""prompts user to move gripper to target points on labware for
	calibration purposes


	:param points: list of points [[x,y,z],[x,y,z]...] to map to. In destination coordinates
	:type points: list
	:param p0: coordinate of first point in points, in source coordinates
	:type p0: list
	:param gantry: gantry object
	:type gantry: gantry.Gantry
	:param z_clearance: verstical offset (mm) from points to start at to prevent collision by initial misalignment, defaults to 5
	:type z_clearance: int, optional
	"""

	points = np.asarray(points) #destination coordinates
	p_prev = points[0]

	points_source_guess = points
	
	points_source_meas = [] #source coordinates
	for name, p in zip(slots, points_source_guess):
		movedelta = p - p_prev #offset between current and next point
		gantry.moverel(*movedelta, zhop = False) #move to next point
		print(f'Move to {name}')
		gantry.gui() #prompt user to align gantry to exact target location
		points_source_meas.append(gantry.position)
		gantry.moverel(z = z_clearance, zhop = False)
		p_prev = p 

	return CoordinateMapper(p0 = points_source_meas, p1 = points)


class Workspace:
	'''
	General class for defining planar workspaces. Primary use is to calibrate the coordinate system of this workspace to 
	the reference workspace to account for any tilt/rotation/translation in workspace mounting.
	'''
	def __init__(self, name, pitch, gridsize, gantry, p0 = [None, None, None], testslots = None, z_clearance = 5, openwidth = 20):
		"""[summary]

		:param name: name of workspace. For logging purposes
		:type name: string
		:param p0: Approximate location of lower left slot in the source (gantry) coordinate system
		:type name: list [x,y,z]
		:param pitch: space between neighboring breadboard holes, mm, (x,y). assume constrained in xy plane @ z = 0
		:type pitch: [type]
		:param gridsize: number of grid points available, (x,y)
		:type gridsize: [type]
		:param gantry: Gantry control object
		:type gridsize: gantry.Gantry
		:param testslots: slots to probe during calibration, defaults to None
		:type testslots: [type], optional
		:param z_clearance: vertical offset when calibrating points, in mm. ensures no crashing before calibration, defaults to 5
		:type z_clearance: int, optional
		"""
		self.calibrated = False #set to True after calibration routine has been run
		self.name = name
		self.gantry = gantry
		# coordinate system properties
		self.pitch = pitch
		self.p0 = np.asarray(p0)
		self.gridsize = gridsize
		self.z_clearance = z_clearance 	
		self.OPENWIDTH = openwidth
		self.__generate_coordinates()

		if testslots is None:
			testslots = []
			testslots.append(f'{self._ycoords[0]}{self._xcoords[0]}') 	#bottom left corner
			testslots.append(f'{self._ycoords[-1]}{self._xcoords[0]}') 	#top left corner
			testslots.append(f'{self._ycoords[-1]}{self._xcoords[-1]}') 	#top right corner
			testslots.append(f'{self._ycoords[0]}{self._xcoords[-1]}')	#bottom right corner
		elif len(testslots) != 4:
			raise Exception('Must provide four corner test points, in list form ["A1", "A2", "B3", "B4"], etc')

		self.testslots = testslots
		self.testpoints = np.array([self._coordinates[name] for name in testslots]).astype(np.float32)

	def __generate_coordinates(self):
		def letter(num):
			#converts number (0-25) to letter (A-Z)
			return chr(ord('A') + num)

		self._coordinates = {}
		self._ycoords = [letter(self.gridsize[1]-yidx-1) for yidx in range(self.gridsize[1])]	#lettering +y -> -y = A -> Z
		self._xcoords = [xidx+1 for xidx in range(self.gridsize[0])]								#numbering -x -> +x = 1 -> 100

		for yidx in range(self.gridsize[1]): #y 
			for xidx in range(self.gridsize[0]): #x
				name = f'{self._ycoords[yidx]}{self._xcoords[xidx]}' 
				self._coordinates[name] = [xidx*self.pitch[0], yidx*self.pitch[1], 0]
				# self._coordinates[name] = [p + poffset for p, poffset in zip(relative_position, self.offset)]

	def slot_coordinates(self, name):
		if self.calibrated == False:
			raise Exception(f'Need to calibrate {self.name} before use!')
		return self.transform.map(self._coordinates[name])

	def __call__(self, name):
		return self.slot_coordinates(name)

	def calibrate(self):
		self.gantry.moveto(*self.p0)
		self.gantry.open_gripper(self.OPENWIDTH)
		self.transform = map_coordinates(self.testslots, self.testpoints, self.gantry, self.z_clearance)
		self.calibrated = True