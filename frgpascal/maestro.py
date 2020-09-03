import numpy as np
import pyquaternion

class Workspace:
	'''
	General class for defining planar workspaces. Primary use is to calibrate the coordinate system of this workspace to 
	the reference workspace to account for any tilt/rotation/translation in workspace mounting.
	'''
	def __init__(self, name, xsize, ysize, pitch, offset, gridsize, testslots = None, verticalclearance = 25):
		self.calibrated = False #set to True after calibration routine has been run
		# coordinate system properties
		self.size = (xsize, ysize)
		self.pitch = pitch
		self.offset = offset
		self.gridsize = gridsize
		self.verticalclearance = verticalclearance 	#vertical offset when calibrating points, in mm. ensures no crashing before calibration
		# self.pitch = (25.4, 25.4) 	#space between neighboring breadboard holes, mm, (x,y). assume constrained in xy plane @ z = 0
		# self.offset = (10, 10, 0)		#offset between workspace (0,0 0) and bottom-left breadboard hole, mm, (x,y,z)
		# self.gridsize = (25, 15)	#number of breadboard holes available, (x,y)
		self.__generate_coordinates()

		if testslots is None:
			testslots = []
			testslots.append(f'{self.__ycoords[0]}{self.__xcoords[0]}') 	#top left corner
			testslots.append(f'{self.__ycoords[-1]}{self.__xcoords[0]}') 	#bottom left corner
			testslots.append(f'{self.__ycoords[-1]}{self.__xcoords[-1]}')	#bottom right corner
		elif len(testslots) != 3:
			raise Exception('Must provide three test points, in list form [A1, A2,B3], etc')

		self.testslots = testslots
		self.testpoints = np.array([self.__coordinates[name] for name in testslots])

	def __generate_coordinates(self):
		def letter(num):
			#converts number (0-25) to letter (A-Z)
			return chr(ord('A') + num)

		self.__coordinates = {}
		self.__ycoords = [letter(self.gridsize[1]-yidx-1) for yidx in range(self.gridsize[1])]	#lettering +y -> -y = A -> Z
		self.__xcoords = [xidx+1 for xidx in range(self.gridsize[0])]								#numbering -x -> +x = 1 -> 100

		for yidx in range(self.gridsize[1]): #y 
			for xidx in range(self.gridsize[0]): #x
				name = f'{self.__ycoords[yidx]}{self.__xcoords[xidx]}' 
				relative_position = [xidx*self.pitch[0], yidx*self.pitch[1], 0]
				self.__coordinates[name] = [p + poffset for p, poffset in zip(relative_position, self.offset)]

	def slot_coordinates(self, name):
		return self.transform(self.__coordinates[name])

	def calibrate(self, measuredpoints):
		measuredpoints = np.array(measuredpoints)
		u1 = self.testpoints[0] - self.testpoints[1]
		v1 = self.testpoints[0] - self.testpoints[2]
		p1 = np.mean(self.testpoints, axis = 0) #centroid of 3 test points
		n1 = np.cross(u1, v1) # vector normal to test plane in workspace coordinates

		u2 = measuredpoints[0] - measuredpoints[1]
		v2 = measuredpoints[0] - measuredpoints[2]
		p2 = np.mean(measuredpoints, axis = 0) #centroid
		n2 = np.cross(u2,v2) # vector normal to test plane in reference coordinates

		self.R = pyquaternion.Quaternion(angle = np.dot(n1,n2), axis = np.cross(n1,n2)) #rotation quaternion to bring workspace coordinate system parallel to reference coordinate system
		self.T = p2 - p1 #translation vector to align workspace and reference coordinate systems
		self.meauredpoints = measuredpoints
		self.calibrated = True

	def transform(self, p):
		if not self.calibrated:
			raise Exception('Workspace has not yet been calibrated to reference coordinate system!')
		return self.R.rotate(p) + self.T