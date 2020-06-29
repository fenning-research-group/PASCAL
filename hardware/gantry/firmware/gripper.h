/*
	gripper.h - library for controlling gripper
	Written by Manuel Saldana
	MAE 156B Spring 2020, Team 13
*/

#ifndef gripper_h
#define gripper_h

#include "Arduino.h"
#include "Servo.h"

class gripper
{
	// user-accessible public interface
	public:
		// function that handles the creation and setup of instances
		gripper(char);

		// function to initialize servo pins
		void init_servo(int,int);
    
		// function to close
		void close(void);
		
		// function to open
		void open(void);
		
	// library-accessible private interface
	private:

		// create servo object
		Servo my_servo;

		// delay time for servo movement
		// allows enough time for servo to reach position
		const int move_delay = 2000;
		// delay time for servo step
		// this is to control servo speed
		const int step_delay = 25;

		// servo and feedback pins
		int pin_servo;
		int pin_fdbck;

		// values of max and min available servo degrees, large black servo
		const int max_angle_l = 180;
		const int min_angle_l = 0;
		// values of max and min feedback values, large black servo
		const int max_fdbck_l = 460;  // 180 degrees
		const int min_fdbck_l = 107;  // 0 degrees
		// values of max and min available servo degrees, small black servo
		const int max_angle_s = 180;
		const int min_angle_s = 0;
		// values of max and min feedback values, small black servo
		const int max_fdbck_s = 501;  // 180 degrees
		const int min_fdbck_s = 131;  // 0 degrees
		
		// values of max and min available servo degrees
		int max_angle;
		int min_angle;
		// values of max and min feedback values
		int max_fdbck;  // 180 degrees
		int min_fdbck;  // 0 degrees

		// gripper angle offset
		// this is to avoid hard 0,180 angles
		const int angle_off = 45;
		// close angle (results in min gripper width)
		const int angle_close = 0 + angle_off;
		// open angle (results in max gripper width)
		const int angle_open = 90 + angle_off;
		
		// set servo angle
		void angle_set(int);
		
		// get actual servo angle (using feedback)
		int angle_get(void);
};

#endif
