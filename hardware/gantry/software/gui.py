import sys
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QGridLayout, QPushButton
from PyQt5.QtCore.Qt import QtAlignHCenter
from functools import partial
import numpy as np

class GantryGUI():
   def __init__(self, gantry):
      self.gantry = gantry
      self.app = QApplication()
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
      self.grid.addWidget(self.gantrystatus, 5,3)

      ### jog motor buttons
      self.jogback = QPushButton('Back')
      self.jogback.clicked.connect(partial(self.jog, y = 1))
      self.grid.addWidget(self.jogback, 3, 1)

      self.jogforward = QPushButton('Forward')
      self.jogforward.clicked.connect(partial(self.jog, y = -1))
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
      
      self.stepsize_options = {
         0.1: self.steppt1,
         1: self.step1,
         10: self.step10
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
      sys.exit(self.app.exec_())
      return

class FakeGantry:
   def __init(self):
      return
   @property
   def position(self):
      return [np.random.random() for i in range(3)]

   def moverel(self, x, y, z):
      print(f'moving {x},{y},{z}')  

# if __name__ == '__main__':
#    window()