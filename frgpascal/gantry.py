import serial
import time
import re
import numpy as np
import sys
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QGridLayout, QPushButton
import PyQt5
# from PyQt5.QtCore.Qt import AlignHCenter
from functools import partial
from helpers import get_port

class Gantry:
    def __init__(self, serial_number='55838333932351108212'):
        #communication variables
        self.port = get_port(serial_number)
        self.terminator = '\n'
        self.POLLINGDELAY = 0.05 #delay between sending a command and reading a response, in seconds
        self.inmotion = False

        #gantry variables
        self.xlim = (10,797.0)
        self.ylim = (0,165.0)
        self.zlim = (0,136.0)
        self.position = [None, None, None] #start at None's to indicate stage has not been homed.
        self.__targetposition = [None, None, None] 
        self.GANTRYTIMEOUT = 15 #max time allotted to gantry motion before flagging an error, in seconds
        self.POSITIONTOLERANCE = 0.05 #tolerance for position, in mm
        self.MAXSPEED = 10000 #mm/min
        self.MINSPEED = 500   #mm/min
        self.speed = 10000 #mm/min, default speed
        self.ZHOP_HEIGHT = 20 #mm above endpoints to move to in between points
        # self.moving = [False, False, False] #boolean flag to indicate whether the xyz axes are in motion or not

        #gripper variables
        self.gripperwidth = None
        self.servoangle = None
        self.MAXANGLE = 60
        self.MINANGLE = 0
        self.MINWIDTH = 6.5
        self.MAXWIDTH = 28 #max gripper width, in mm
        self.GRIPRATE = 10 #default gripper open/close rate, mm/s
        self.GRIPINTERVAL = 0.05 #gripper open/close motions interpolated onto this time interval, s
        self.GRIPSTEP = self.GRIPRATE * self.GRIPINTERVAL
        #connect to gantry by default
        self.connect()
        self.set_defaults()

    #communication methods
    def connect(self):
        self._handle = serial.Serial(
            port = self.port,
            timeout = 1,
            baudrate = 115200
            )
        self.update()
        # self.update_gripper()
        if self.position == [max(self.xlim), max(self.ylim), max(self.zlim)]: #this is what it shows when initially turned on, but not homed
            self.position = [None, None, None] #start at None's to indicate stage has not been homed.   
        
        # self.write('M92 X40.0 Y26.77 Z400.0')

    def disconnect(self):
        self._handle.close()
        del self._handle

    def set_defaults(self):
        self.write('G90') #absolute coordinate system
        # self.write('M92 X26.667 Y26.667 Z200.0') #set steps/mm, randomly resets to defaults sometimes idk why
        self.write('M92 X53.333 Y53.333 Z400.0') #set steps/mm, randomly resets to defaults sometimes idk why
        self.write(f'M203 X{self.MAXSPEED} Y{self.MAXSPEED} Z25.00') #set max speeds, steps/mm. Z is hardcoded, limited by lead screw hardware. 
        self.set_speed_percentage(80) #set speed to 80% of max

    def write(self, msg):
        self._handle.write(f'{msg}{self.terminator}'.encode())
        time.sleep(self.POLLINGDELAY)
        output = []
        while self._handle.in_waiting:
            line = self._handle.readline().decode('utf-8').strip()
            if line != 'ok':
                output.append(line)
            time.sleep(self.POLLINGDELAY)
        return output

    def _enable_steppers(self):
        self.write('M18')

    def _disable_steppers(self):
        self.write('M17')

    def update(self):
        found_coordinates = False
        while not found_coordinates:
            output = self.write('M114') #get current position
            for line in output:
                if line.startswith('X:'):
                    x = float(re.findall('X:(\S*)', line)[0])
                    y = float(re.findall('Y:(\S*)', line)[0])
                    z = float(re.findall('Z:(\S*)', line)[0])
                    found_coordinates = True
                    break
        self.position = [x,y,z]

    def update_gripper(self):
        found_coordinates = False
        while not found_coordinates:
            output = self.write('M280 P0') #get current servo position
            for line in output:
                if line.startswith('echo: Servo'):
                    self.servoangle = float(re.findall('Servo 0: (\S*)', line)[0]) #TODO - READ SERVO POSITION
                    self.gripperwidth = self.__servo_angle_to_width(self.servoangle)
                    found_coordinates = True
                    break

    #gantry methods
    def set_speed_percentage(self, p):
        if p < 0 or p > 100:
            raise Exception('Speed must be set by a percentage value between 0-100!')
        self.speed = (p/100) * (self.MAXSPEED - self.MINSPEED) + self.MINSPEED
        self.write(f'G0 F{self.speed}')

    def gohome(self):
        self.write('G28 X Y Z')
        self.update()

    def premove(self, x, y, z):
        '''
        checks to confirm that all target positions are valid
        '''
        if self.position == [None, None, None]:
            raise Exception('Stage has not been homed! Home with self.gohome() before moving please.')
            return False

        if x > self.xlim[1] or x < self.xlim[0]:
            return False
        if y > self.ylim[1] or y < self.ylim[0]:
            return False
        if z > self.zlim[1] or z < self.zlim[0]:
            return False

        self.__targetposition = [x,y,z]
        return True

    def moveto(self, x = None, y = None, z = None, zhop = True, speed = None):
        '''
        moves to target position in x,y,z (mm)
        '''
        try:
            if len(x) == 3:
                x,y,z = x #split 3 coordinates into appropriate variables
        except:
            if x is None:
                x = self.position[0]
            if y is None:
                y = self.position[1]
            if z is None:
                z = self.position[2]
        if speed is None:
            speed = self.speed

        if zhop:
            z_ceiling = max(self.position[2], z) + self.ZHOP_HEIGHT
            z_ceiling = min(z_ceiling, max(self.zlim)) #cant z-hop above build volume. mostly here for first move after homing.
            self.moveto(z = z_ceiling, zhop = False, speed = speed)
            self.moveto(x, y, z_ceiling, zhop = False, speed = speed)
            self.moveto(z = z, zhop = False, speed = speed)
        else:
            self._movecommand(x, y, z, speed)

    def _movecommand(self, x = None, y = None, z = None, speed = None):
        if self.premove(x, y, z):
            if self.position == [x,y,z]:
                return True #already at target position
            else:
                self.write(f'G0 X{x} Y{y} Z{z} F{speed}')
                return self._waitformovement()
        else:
            raise Exception('Invalid move - probably out of bounds. Possibly due to z-hopping between points near top of working volume?')

    def moverel(self, x = 0, y = 0, z = 0, zhop = False, speed = None):
        '''
        moves by coordinates relative to the current position
        '''
        if self.position == [None, None, None]:
            raise Exception('Stage has not been homed! Home with self.gohome() before moving please.')
        try:
            if len(x) == 3:
                x,y,z = x #split 3 coordinates into appropriate variables
        except:
            pass
        x += self.position[0]
        y += self.position[1]
        z += self.position[2]
        self.moveto(x,y,z,zhop, speed)

    def _waitformovement(self):
        '''
        confirm that gantry has reached target position. returns False if
        target position is not reached in time allotted by self.GANTRYTIMEOUT
        '''
        self.inmotion = True
        start_time = time.time()
        time_elapsed = time.time() - start_time
        self._handle.write(f'M400{self.terminator}'.encode())
        self._handle.write(f'M118 E1 FinishedMoving{self.terminator}'.encode())
        reached_destination = False
        while not reached_destination and time_elapsed < self.GANTRYTIMEOUT:
            time.sleep(self.POLLINGDELAY)
            while self._handle.in_waiting:
                line = self._handle.readline().decode('utf-8').strip()
                if line == 'echo:FinishedMoving':
                    self.update()
                    if np.linalg.norm([a-b for a,b in zip(self.position, self.__targetposition)]) < self.POSITIONTOLERANCE:
                        reached_destination = True
                time.sleep(self.POLLINGDELAY)
            time_elapsed = time.time() - start_time

        self.inmotion = ~reached_destination
        return reached_destination

    #gripper methods
    def open_gripper(self, width = None, instant = True):
        '''
        open gripper to width, in mm
        '''
        if width is None:
            width = self.MAXWIDTH


        angle = self.__width_to_servo_angle(width)

        if instant:
            self.write(f'M280 P0 S{angle}')
        else:
            delta = np.abs(width - self.gripperwidth)
            n_points = np.ceil(delta/self.GRIPSTEP).astype(int)
            for w in np.linspace(self.gripperwidth, width, n_points):
                angle = self.__width_to_servo_angle(w)
                self.write(f'M280 P0 S{angle}') 
                time.sleep(self.GRIPINTERVAL)
        self.update_gripper()

    def close_gripper(self, instant = True):
        self.open_gripper(width = self.MINWIDTH, instant = instant)

    def __servo_angle_to_width(self, angle):
        '''
        convert servo angle (degrees) to gripper opening width (mm)
        '''
        if (angle > self.MAXANGLE) or (angle < self.MINANGLE):
            raise Exception(f'Angle {angle} outside acceptable range ({self.MINANGLE}-{self.MAXANGLE})')

        fractional_angle = (angle-self.MINANGLE) / (self.MAXANGLE-self.MINANGLE)
        width = fractional_angle * (self.MAXWIDTH - self.MINWIDTH) + self.MINWIDTH
        
        return np.round(width, 1)

    def __width_to_servo_angle(self, width):
        '''
        convert gripper width (mm) to servo angle (degrees)
        '''
        if (width > self.MAXWIDTH) or (width < self.MINWIDTH):
            raise Exception(f'Width {width} outside acceptable range ({self.MINWIDTH}-{self.MAXWIDTH})')

        fractional_width = (width - self.MINWIDTH) / (self.MAXWIDTH - self.MINWIDTH)
        angle = fractional_width*(self.MAXANGLE-self.MINANGLE) + self.MINANGLE
        
        return np.round(angle, 0)

    def gui(self):
        GantryGUI(gantry = self) #opens blocking gui to manually jog motors

class GantryGUI:
   def __init__(self, gantry):
      AlignHCenter = PyQt5.QtCore.Qt.AlignHCenter
      self.gantry = gantry
      self.app = QApplication(sys.argv)
      self.app.aboutToQuit.connect(self.app.deleteLater)
      self.win = QWidget()
      self.grid = QGridLayout()
      self.stepsize = 1 #default step size, in mm

      ### axes labels
      for j, label in enumerate(['X', 'Y', 'Z']):
         temp = QLabel(label)
         temp.setAlignment(AlignHCenter)
         self.grid.addWidget(temp,0,j)
      
      ### position readback values
      self.xposition = QLabel('0')
      self.xposition.setAlignment(AlignHCenter)
      self.grid.addWidget(self.xposition, 1,0)

      self.yposition = QLabel('0')
      self.yposition.setAlignment(AlignHCenter)
      self.grid.addWidget(self.yposition, 1,1)

      self.zposition = QLabel('0')
      self.zposition.setAlignment(AlignHCenter)
      self.grid.addWidget(self.zposition, 1,2)

      self.update_position()

      ### status label
      self.gantrystatus = QLabel('Idle')
      self.gantrystatus.setAlignment(AlignHCenter)
      self.grid.addWidget(self.gantrystatus, 5,4)

      ### jog motor buttons
      self.jogback = QPushButton('Back')
      self.jogback.clicked.connect(partial(self.jog, y = -1))
      self.grid.addWidget(self.jogback, 3, 1)

      self.jogforward = QPushButton('Forward')
      self.jogforward.clicked.connect(partial(self.jog, y = 1))
      self.grid.addWidget(self.jogforward, 2, 1)

      self.jogleft = QPushButton('Left')
      self.jogleft.clicked.connect(partial(self.jog, x = -1))
      self.grid.addWidget(self.jogleft, 3, 0)

      self.jogright = QPushButton('Right')
      self.jogright.clicked.connect(partial(self.jog, x = 1))
      self.grid.addWidget(self.jogright, 3, 2)
      
      self.jogup = QPushButton('Up')
      self.grid.addWidget(self.jogup, 2, 3)
      self.jogup.clicked.connect(partial(self.jog, z = 1))

      self.jogdown = QPushButton('Down')
      self.jogdown.clicked.connect(partial(self.jog, z = -1))
      self.grid.addWidget(self.jogdown, 3, 3)

      ### step size selector buttons
      self.steppt1 = QPushButton('0.1 mm')
      self.steppt1.clicked.connect(partial(self.set_stepsize, stepsize = 0.1))
      self.grid.addWidget(self.steppt1, 5, 0)
      self.step1 = QPushButton('1 mm')
      self.step1.clicked.connect(partial(self.set_stepsize, stepsize = 1))
      self.grid.addWidget(self.step1, 5, 1)
      self.step10 = QPushButton('10 mm')
      self.step10.clicked.connect(partial(self.set_stepsize, stepsize = 10))
      self.grid.addWidget(self.step10, 5, 2)
      self.step50 = QPushButton('50 mm')
      self.step50.clicked.connect(partial(self.set_stepsize, stepsize = 50))
      self.grid.addWidget(self.step50, 6, 0)
      self.step100 = QPushButton('100 mm')
      self.step100.clicked.connect(partial(self.set_stepsize, stepsize = 100))
      self.grid.addWidget(self.step100, 6, 1)
      
      self.stepsize_options = {
         0.1: self.steppt1,
         1: self.step1,
         10: self.step10,
         50: self.step50,
         100: self.step100
         }

      self.set_stepsize(self.stepsize)
      
      self.run()


   def set_stepsize(self, stepsize):
      self.stepsize = stepsize
      for setting, button in self.stepsize_options.items():
         if setting == stepsize:
            button.setStyleSheet('background-color: #a7d4d2')
         else:
            button.setStyleSheet('background-color: None')

   def jog(self, x = 0, y = 0, z = 0):
      self.gantrystatus.setText('Moving')
      self.gantrystatus.setStyleSheet('color: red')
      self.gantry.moverel(x*self.stepsize, y*self.stepsize, z*self.stepsize)
      self.update_position()
      self.gantrystatus.setText('Idle')
      self.gantrystatus.setStyleSheet('color: None')

   def update_position(self):
      for position, var in zip(self.gantry.position, [self.xposition, self.yposition, self.zposition]):
         var.setText(f'{position:.2f}')

   def run(self):
      self.win.setLayout(self.grid)
      self.win.setWindowTitle("PASCAL Gantry GUI")
      self.win.setGeometry(300,300,500,150)
      self.win.show()
      QApplication.setQuitOnLastWindowClosed(True)
      self.app.exec_()
      self.app.quit()
      # sys.exit(self.app.exec_())
      # self.app.exit()
      # sys.exit(self.app.quit())
      return

