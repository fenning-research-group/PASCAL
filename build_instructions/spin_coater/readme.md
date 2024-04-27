# Overview
This document details PASCAL's custom-designed spin coater, utilizing a drone motor for its hollow shaft which facilitates vacuum suction to secure the substrate. The motor is controlled via a rotary encoder, allowing precise substrate positioning essential for automated processing. The setup requires a Windows machine with Python to send commands; alternatively, a Raspberry Pi may be used to operate the ODrive, though this configuration remains untested.

<img src="demo_figure/spin_coater.gif" width="25%" height="auto" />


# Parts List
| Part                     | Price | Link|
|--------------------------|-------|----------------------------------------------------------------------------------------------------------------|
| ODRIVE V3.6              | $260  | [https://odriverobotics.com/shop/odrive-v36](https://odriverobotics.com/shop/odrive-v36)                       |
| 8192 CPR ENCODER         | $40   | [https://odriverobotics.com/shop/cui-amt-102](https://odriverobotics.com/shop/cui-amt-102)                     |
| 1800kV Brushless motor   | $23   | [https://www.amazon.com/iFlight-1800KV-Brushless-Quadcopter-unibell/dp/B07XYYRWGP](https://www.amazon.com/iFlight-1800KV-Brushless-Quadcopter-unibell/dp/B07XYYRWGP) |
| Modular PS 600W 24V 25A  | $190  | [https://www.mouser.com/ProductDetail/Cosel/PJMA600F-24?qs=DRkmTr78QARizXWjL2NKqg%3D%3D&countryCode=US&currencyCode=USD](https://www.mouser.com/ProductDetail/Cosel/PJMA600F-24?qs=DRkmTr78QARizXWjL2NKqg%3D%3D&countryCode=US&currencyCode=USD) |
| Vaacum pump              | $300   | [https://www.rocker.com.tw/en/product/lab-pumps/ptfe-coated-chemical-resistant-vacuum-pump/rocker-400c-ptfe-coated-vacuum-pump/](https://www.rocker.com.tw/en/product/lab-pumps/ptfe-coated-chemical-resistant-vacuum-pump/rocker-400c-ptfe-coated-vacuum-pump/) |
| Al-Machined Motor Chuck  | $200   | [https://www.hubs.com/manufacture/?technology=cnc-machining](https://www.hubs.com/manufacture/?technology=cnc-machining) |
| O-rings                 | $8   | [https://www.amazon.com/Assortment-Plusmart-Pressure-Plumbing-Connections/dp/B0BRN1H471/ref=sr_1_3?crid=2V931C3RGIA20&dib=eyJ2IjoiMSJ9.rMalqnjJK4ptQgIJLXaeol0CN2hMWmSikj0mL1o6aGlH5g0-8UIIJyiXwOtEuSjqxBKzqwW-IMcVi-_6pHMGr_V17O1k9zyMj5X0CCneCI-Jw45dT5PRA3iP8sXJPMMB65hSxLmY9sEAnRvApKuByc5BMIBpTVl4fiq46vQLhJXs_yEAJ9ZE8y7I4x47jYTukhg214csptJHL4ErhJntWRZFgNtJlqjsY_1cCjp2F6k.j1-vT5KaGQSVuHFfXLnOroh-s68B_fjaRGQ5Qn03ITc&dib_tag=se&keywords=o+rings&qid=1712552969&sprefix=o+ring%2Caps%2C179&sr=8-3](https://www.amazon.com/Assortment-Plusmart-Pressure-Plumbing-Connections/dp/B0BRN1H471/ref=sr_1_3?crid=2V931C3RGIA20&dib=eyJ2IjoiMSJ9.rMalqnjJK4ptQgIJLXaeol0CN2hMWmSikj0mL1o6aGlH5g0-8UIIJyiXwOtEuSjqxBKzqwW-IMcVi-_6pHMGr_V17O1k9zyMj5X0CCneCI-Jw45dT5PRA3iP8sXJPMMB65hSxLmY9sEAnRvApKuByc5BMIBpTVl4fiq46vQLhJXs_yEAJ9ZE8y7I4x47jYTukhg214csptJHL4ErhJntWRZFgNtJlqjsY_1cCjp2F6k.j1-vT5KaGQSVuHFfXLnOroh-s68B_fjaRGQ5Qn03ITc&dib_tag=se&keywords=o+rings&qid=1712552969&sprefix=o+ring%2Caps%2C179&sr=8-3) |
| SLA Printed Peripherals           | $10   | [https://www.amazon.com/OVERTURE-Filament-Consumables-Dimensional-Accuracy/dp/B07PGY2JP1/ref=sr_1_3_pp?dib=eyJ2IjoiMSJ9.SPz8Xg0t9pBHW5vzHC0hcqYxYtXwfa-Yil5LIAxK-nDf3JL1GTkKLyJrApjVsETM4KNQFX0PTiyEjpSvCEeJO5QKM6cQ-r08OafjWC4lTNDPu67BWv0pnhG3ZZ_HfrawVwvNJynrEMEsomfeJCVhNsTjr1BFBFbQpH87o5VaQDwiJH4rlViSL9sBvPO-Piux_RiqL3OfRC7emvw6rOVGAw8aUow_buCBNpMFJfJO4-Q.SG9CzlajxzBXdi_JxmHuRgmdlpNjiI1lcAEBselnEtU&dib_tag=se&keywords=-%2BPLA&qid=1712552942&sr=8-3&th=1](https://www.amazon.com/OVERTURE-Filament-Consumables-Dimensional-Accuracy/dp/B07PGY2JP1/ref=sr_1_3_pp?dib=eyJ2IjoiMSJ9.SPz8Xg0t9pBHW5vzHC0hcqYxYtXwfa-Yil5LIAxK-nDf3JL1GTkKLyJrApjVsETM4KNQFX0PTiyEjpSvCEeJO5QKM6cQ-r08OafjWC4lTNDPu67BWv0pnhG3ZZ_HfrawVwvNJynrEMEsomfeJCVhNsTjr1BFBFbQpH87o5VaQDwiJH4rlViSL9sBvPO-Piux_RiqL3OfRC7emvw6rOVGAw8aUow_buCBNpMFJfJO4-Q.SG9CzlajxzBXdi_JxmHuRgmdlpNjiI1lcAEBselnEtU&dib_tag=se&keywords=-%2BPLA&qid=1712552942&sr=8-3&th=1) |
| Solenoid Valve          | $8   | [https://www.amazon.com/4inch-Normally-Closed-Electric-Solenoid/dp/B074Z5SDG3/ref=sr_1_3?crid=5POYNORA9EZL&dib=eyJ2IjoiMSJ9.JLsx3y_np7SG8hfKIUtJtWj8VtkfgF_CTbaxIyYoZ5OHgnqSQ8kOew68nTNhAhrPIDTpnumhJRObFIyRSCQiZCXshF3rObQj-HOZV87RKFJ6do-l0fcqZO3ZMh0pw_jtH8uBoLCpnQS4xYqQm-zO0h_RK_vBkP_qY5F-44N056ZKnEJHcm_twtE9Qvi0YZVwB6c-gy3uV4SWPL2bweUyBgrk076l_5p9qJ5PWumZ4mg.hs0sm7t366FhuDrl8LP-5qxEI9jizQlWJ90Q60t1cAI&dib_tag=se&keywords=12v+solenoid+valve&qid=1712552992&sprefix=12v+solenoid+valv%2Caps%2C130&sr=8-3](https://www.amazon.com/4inch-Normally-Closed-Electric-Solenoid/dp/B074Z5SDG3/ref=sr_1_3?crid=5POYNORA9EZL&dib=eyJ2IjoiMSJ9.JLsx3y_np7SG8hfKIUtJtWj8VtkfgF_CTbaxIyYoZ5OHgnqSQ8kOew68nTNhAhrPIDTpnumhJRObFIyRSCQiZCXshF3rObQj-HOZV87RKFJ6do-l0fcqZO3ZMh0pw_jtH8uBoLCpnQS4xYqQm-zO0h_RK_vBkP_qY5F-44N056ZKnEJHcm_twtE9Qvi0YZVwB6c-gy3uV4SWPL2bweUyBgrk076l_5p9qJ5PWumZ4mg.hs0sm7t366FhuDrl8LP-5qxEI9jizQlWJ90Q60t1cAI&dib_tag=se&keywords=12v+solenoid+valve&qid=1712552992&sprefix=12v+solenoid+valv%2Caps%2C130&sr=8-3) |
| 16 Channel USB Relay Module                   | $100   | [https://numato.com/product/16-channel-usb-relay-module/](https://numato.com/product/16-channel-usb-relay-module/) |


# Installation
Connect the hardware following https://docs.odriverobotics.com/v/0.5.5/getting-started.html
 - Motor wire configuration to ODrive does not matter, but encoder wires do
 - Ensure break resistor is connected&enabled, polarity does not matter
 - Ensure that the encoder is supported (use our 3D printed part)
 - Ensure that the motor can rotate with minimal friction when completely assemeled 


### Motor Control 
To enable Odrive to properly control the motor, the following parameters need to be set:

0. Start odrivetool in your terminal to set encoder settings

1. CPR of the encoder (this is the number of indexed "positions" the encoder has, for the encoder linked above, it is 8192)
- `odrv0.axis0.encoder.config.cpr = 8192`

2. Motor pole pairs (Pole pairs = number of permanent magnets in the motor/2, for the motor linked above, it is 7)
- `odrv0.axis0.motor.config.pole_pairs = 7`

3. Motor current limit and calibration current
- `odrv0.axis0.motor.config.current_lim = 40`
- `odrv0.axis0.motor.config.calibration_current = 10`

4. Motor Torque Constant (8.27/motorkV
- `odrv0.axis0.motor.config.torque_constant = 8.27 / 1800`

5. ODrive break resistance 
- `odrv0.config.enable_brake_resistor = True`
- `odrv0.config.brake_resistance = 2`

6. Motor PID Gains (adjust to 0 if the motor vibrates or spins after calibration, but start by raising P and V value from 0 if rpm control fails after calibration)

| Motor                    | Position | Velocity  | Integrator
|--------------------------|-------|---------------|-------------------------------------------------------------------------------------------------|
| 1800kV | `odrv0.axis0.controller.config.pos_gain = 5` | `odrv0.axis0.controller.config.vel_gain = 0.05` | `odrv0.axis0.controller.config.vel_integrator_gain =  5 * vel_gain`
| 1700kV | `odrv0.axis0.controller.config.pos_gain = 100` | `odrv0.axis0.controller.config.vel_gain = 0.05` | `odrv0.axis0.controller.config.vel_integrator_gain =  0`

7. Save the settings
- `odrv0.save_configuration()`

8. Test Calibration
- `odrv0.axis0.requested_state = AXIS_STATE_ENCODER_OFFSET_CALIBRATION` #Should rotate CW and CCW

9. Test Control Mode
- `odrv0.axis0.requested_state = AXIS_STATE_CLOSED_LOOP_CONTROL`

* See https://docs.odriverobotics.com/v/0.5.5/getting-started.html for more details.

10. Proceed to Python Code if no issues
Go to Example Usage at bottom

### Vacuum and Solenoid Control
1. Connect a 12v 1A power supply to the solenoid valve by connecting its + terminal to the solenoid + terminal then connect the solenoid's - terminal to the relay module slot 7. 
2. Connect the relay modules's slot 7 - terminal to the power supplys - terminal.
3. Connect the relay modules's usb to the computer. 
4. Ensure that your PC has the driver for the module, if not, download it from https://numato.com/product/16-channel-usb-relay-module/ 
5. Connect vacuum tubing form the pump to the solenoid valve, then from the solenoid valve to the motor chuck.


### Peripherals 
1. Get the aluminum spin coater chuck machined, ensure that the NPT is tapped for the vacuum valve and that M5 screws are tapped to fasten the encoder to the chuck.
2. Remove the screw underneath the motor shaft to allow for vacuum to be pulled through the motor.
3. Place an gasket or o-ring on the chuck to ensure a tight seal with the motor. We've found a gasket (sheet of soft rubber like material) works better (~3cm square).
4. Screw the motor down to the chuck. Ensure that the screw underneath the motor shaft is removed. 
5. Place encoder onto the chuck. 
6. Screw on the M5 hex shaft to the remaining threads of the motor shaft.
7. Place the spincoater plate (3D printed part) onto the hex shaft (pressure fit)
8. Glue on an o-ring to the top of the hex shaft to ensure a tight seal with the substrate (plate should be flush with top of the o-ring so that substrate is level with the plate)
9. 3D print the encoder mount and screw it down to the chuck. Glue magnets into place.
10. 3D print the spin coater bowl. Glue magnets into place.
11. Using the magnets attach the bowl to the encoder mount. 



# Example Usage
`ipython #if not in it`

`cd "C:\Users\Fenning lab\Documents\GitHub\PASCAL\build_instructions\spin_coater"`

`from standalone_spincoater import SpinCoater`

`sc = SpinCoater()`

`sc.set_rpm(rpm = 2000, acceleration = 1000)`

This can be combined with our SpinCoater.stop() command which will decelerate the motor to a stop and then lock the motor to a predefined position. 

Combining these two commonds a typical spin coating sequence would look like:

`sc.set_rpm(rpm = 2000, acceleration = 1000)`

`time.sleep(10)`

`sc.stop()`
