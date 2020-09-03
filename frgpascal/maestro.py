import numpy as np
import pyquaternion

class Maestro:
	def __init__(self):
		# coordinate system properties
		self.__breadboard_pitch = (25.4, 25.4) 	#space between neighboring breadboard holes, mm, (x,y). assume constrained in xy plane @ z = 0
		self.__breadboard_offset = (10, 10, 0)		#offset between workspace (0,0 0) and bottom-left breadboard hole, mm, (x,y,z)
		self.__breadboard_gridsize = (25, 15)	#number of breadboard holes available, (x,y)
		self.__generate_breadboard_coordinates()

		self.__T_gantry_workspace = self.__load_last_T_gantry_workspace() #transformation quaternion to map gantry coordinates onto workspace coordinates
		self.__T_gantry_workspace_testpoints = ['C1', 'F1', 'C10'] #breadboard holes to probe for workspace - gantry alignment

	def __load_last_T_gantry_workspace(self):
		return None

	def __generate_breadboard_coordinates(self):
		def letter(num):
			#converts number (0-25) to letter (A-Z)
			return chr(ord('A') + num)

		self.__breadboard_coordinates = {}
		for yidx in range(self.__breadboard_gridsize[1]): #y 
			for xidx in range(self.__breadboard_gridsize[0]): #x
				name = f'{letter(self.__breadboard_gridsize[1]-yidx-1)}{xidx+1}' #lettering +y -> -y = A -> Z, numbering -x -> +x = 1 -> 100
				relative_position = [xidx*self.__breadboard_pitch[0], yidx*self.__breadboard_pitch[1], 0]
				self.__breadboard_coordinates[name] = [p + poffset for p, poffset in zip(relative_position, self.__breadboard_offset)]

	def breadboard(self, name):
		return self.__breadboard_coordinates[name]