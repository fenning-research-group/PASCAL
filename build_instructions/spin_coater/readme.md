# Overview
This is a beakout of PASCAL's custom spin coater. 

We use a drone motor since they have a hollow shaft, which allows vacuum to be pulled through the motor to hold the substrate in place. They're also quite cheap. 

To control the motor, we opted to use a rotary encoder over an ESC to enable the final position of the substrate on the coater to be controlled, this is crucial for automated movement of the substrate to the next processing step. 

![overview](demo_figure/spin_coater.gif)


# Custom Spin Coater Parts List
| Part                     | Price | Link                                                                                                           |
|--------------------------|-------|----------------------------------------------------------------------------------------------------------------|
| ODRIVE V3.6              | $260  | [https://odriverobotics.com/shop/odrive-v36](https://odriverobotics.com/shop/odrive-v36)                       |
| 8192 CPR ENCODER         | $40   | [https://odriverobotics.com/shop/cui-amt-102](https://odriverobotics.com/shop/cui-amt-102)                     |
| 1800kV Brushless motor   | $23   | [https://www.amazon.com/iFlight-1800KV-Brushless-Quadcopter-unibell/dp/B07XYYRWGP](https://www.amazon.com/iFlight-1800KV-Brushless-Quadcopter-unibell/dp/B07XYYRWGP) |
| Modular PS 600W 24V 25A  | $190  | [https://www.mouser.com/ProductDetail/Cosel/PJMA600F-24?qs=DRkmTr78QARizXWjL2NKqg%3D%3D&countryCode=US&currencyCode=USD](https://www.mouser.com/ProductDetail/Cosel/PJMA600F-24?qs=DRkmTr78QARizXWjL2NKqg%3D%3D&countryCode=US&currencyCode=USD) |
| Vaacum pump              | $X   | [X](Y) |
| Motor Chuck             | $X   | [X](Y) |
| O-rings                 | $X   | [X](Y) |
| Encoder Mount           | $X   | [X](Y) |
| Solenoid Valve          | $X   | [X](Y) |
| USB Relay                   | $X   | [X](Y) |


## Installation
Connect the hardware following https://docs.odriverobotics.com/v/0.5.5/getting-started.html
 - Motor wire configuration to ODrive does not matter, but encoder wires do
 - Ensure break resistor is connected, polarity does not matter


### Motor Control 
In order for the ODive board to control the motor and encoder, a few settings need to be inputted:
1. CPR of the encoder (this is the number of indexed "positions" the encoder has, for the encoder linked above, it is 8192)
2. Motor pole pairs (Pole pairs = number of permanent magnets in the motor/2, for the motor linked above, it is 7)
3. Motor calibration current 
4. Motor calibration voltage 
5. ODrive break resistance 
6. PID gains

In standalone_spincoater.py, these values are set during initilization, but if there are issues, these are the key settings to enable control. 


### Vacuum and Solenoid Control
1. 
2.
3. 

### Peripherals 
1.
2. 
3. 


More to come.. 