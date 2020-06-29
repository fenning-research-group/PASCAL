/*
	gripper.cpp - library for controlling gripper
	Written by Manuel Saldana
	MAE 156B Spring 2020, Team 13
*/

// include core Wiring API
#include "Arduino.h"
// include servo library
#include "Servo.h"

// include this library's description file
#include "gripper.h"

// constructor
// function that handles the creation and setup of instances
gripper::gripper(char servo_size)
{
	// set limits depending on servo size
	if (servo_size == 's' || servo_size == 'S')
	{
		// set angle and feedback limits for small servo
		max_angle = max_angle_s;
		min_angle = min_angle_s;
		max_fdbck = max_fdbck_s;
		min_fdbck = min_fdbck_s;
	}
	else if (servo_size == 'l' || servo_size == 'L')
	{
		// set angle and feedback limits for large servo
		max_angle = max_angle_l;
		min_angle = min_angle_l;
		max_fdbck = max_fdbck_l;
		min_fdbck = min_fdbck_l;
	}
}

// function to initialize servo pins
void gripper::init_servo(int pin_s, int pin_f)
{
	// set servo and feedback pins
	pin_servo = pin_s;
	pin_fdbck = pin_f;

	// attach servo
	my_servo.attach(pin_servo);

	// set servo to closed angle
	my_servo.write(angle_close);
	// delay
	delay(move_delay);
}

// function to close
void gripper::close(void)
{
	angle_set(angle_close);
}
// function to open
void gripper::open(void)
{
	angle_set(angle_open);
}

// set servo angle
void gripper::angle_set(int angle_target)
{
	// get previous angle
	int angle_prev = my_servo.read();

	// move to target position
	if (angle_prev < angle_target)
	{
		for (int pos = angle_prev; pos <= angle_target; pos++)
		{
		  // increment
		  my_servo.write(pos);
		  delay(step_delay);
		}
	}
	else if (angle_prev > angle_target)
	{
		for (int pos = angle_prev; pos >= angle_target; pos--)
		{
		  // decrement
		  my_servo.write(pos);
		  delay(step_delay);
		}
	}
	else if (angle_prev == angle_target)
	{
		// stay
		int pos = angle_target;
		my_servo.write(pos);
		delay(step_delay);
	}

	// delay
	delay(move_delay);

	// get actual servo angle (feedback)
	// NOTE: not used in current gripper design
	// int angle_act = angle_get();
}

// get actual servo angle (using feedback)
int gripper::angle_get(void)
{
	// get feedback value for servo position
	int fdbck = analogRead(pin_fdbck);
	// return angle value via mapping
	return map(fdbck, min_fdbck, max_fdbck, min_angle, max_angle);
}
