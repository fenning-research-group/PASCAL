/*
	movement.cpp - library for controlling movement
	Written by Manuel Saldana
	MAE 156B Spring 2020, Team 13
*/

// include core Wiring API
#include "Arduino.h"

//include this library's description file
#include "movement.h"

// constructor
// function that handles creation and setup of instances
movement::movement(void)
{
	// by default, set x,y,z to non-zero value
	// set x,y,z to extreme values [mm]
	// this is to ensure system reaches home duirng first zero-out
	curr_x = 10000;
	curr_y = 10000;
	curr_z = 10000;
	pinMode(x_dir_pin, OUTPUT);
	pinMode(x_stp_pin, OUTPUT);
	pinMode(y_dir_pin, OUTPUT);
	pinMode(y_stp_pin, OUTPUT);
	pinMode(z_dir_pin, OUTPUT);
	pinMode(z_stp_pin, OUTPUT);
}

// // function to initialize movement pins
// void movement::init(void)
// {
// 	pinMode(x_dir_pin, OUTPUT);
// 	pinMode(x_stp_pin, OUTPUT);
// 	pinMode(y_dir_pin, OUTPUT);
// 	pinMode(y_stp_pin, OUTPUT);
// 	pinMode(z_dir_pin, OUTPUT);
// 	pinMode(z_stp_pin, OUTPUT);
// }

void movement::set_position(float x, float y, float z)
{
	target_x = x;
	target_y = y;
	target_z = z;
}

// execute one cycle of motor movement
void movement::process_move(void)
{

	if (curr_x < (target_x - TOL_X))
	{ 
		// if (is_pressed(lim_x_max_pin))
		// {	//make sure we havent hit the limit switch
		// 	break;
		// }
		curr_x += STEP_X;
		take_step(x_dir_pin,x_stp_pin,true);
		x_moving = true;

	}
	else if (curr_x > (target_x + TOL_X))
	{
		// if (is_pressed(lim_x_min_pin)){
		// 	break;
		// }
		curr_x -= STEP_X;
		take_step(x_dir_pin,x_stp_pin,false);
		x_moving = true;

	}
	else
	{
		x_moving = false;
	}
		
	// move in y
	if (curr_y < (target_y - TOL_Y))
	{ 
		// if (is_pressed(lim_y_max_pin)){
		// 	break;
		// }
		curr_y += STEP_Y;
		take_step(y_dir_pin,y_stp_pin,false);
		y_moving = true;
	}
	else if (curr_y > (target_y + TOL_Y))
	{
		// if (is_pressed(lim_y_min_pin)){
		// 	break;
		// }
		curr_y -= STEP_Y;
		take_step(y_dir_pin,y_stp_pin,true);
		y_moving = true;
	}
	else
	{
		y_moving = false;
	}


	// move in z
	if (curr_z < (target_z - TOL_Z))
	{
		// if (is_pressed(lim_z_max_pin)){
		// 	break;
		// }
		curr_z += STEP_Z;
		take_step(z_dir_pin,z_stp_pin,true);
		z_moving = true;

	}
	else if (curr_z>(target_z + TOL_Z))
	{
		// if (is_pressed(lim_z_min_pin)){
		// 	break;
		// }
		curr_z -= STEP_Z;
		take_step(z_dir_pin,z_stp_pin,false);
		z_moving = true;
	}
	else
	{
		z_moving = false;
	}

	// wait for movement, update current coordinates
	delay(MOVE_DELAY);		
}


// go to home position (and reset position)
void movement::go_home(void)
{
	bool reached_x = false;
	bool reached_y = false;
	bool reached_z = false;

	while (!reached_x || !reached_y || !reached_z){
		// move in x
		if (!reached_x){ 
			if (is_pressed(lim_x_min_pin)){	//make sure we havent hit the limit switch
				reached_x = true;
			}else{
				curr_x -= STEP_X;
				take_step(x_dir_pin,x_stp_pin,false);
			}
		}
		if (!reached_y){ 
			if (is_pressed(lim_y_min_pin)){	//make sure we havent hit the limit switch
				reached_y = true;
			}else{
				curr_y -= STEP_Y;
				take_step(y_dir_pin,y_stp_pin,true);
			}
		}
		if (!reached_z){ 
			if (is_pressed(lim_z_min_pin)){	//make sure we havent hit the limit switch
				reached_z = true;
			}else{
				curr_z -= STEP_Z;
				take_step(z_dir_pin,z_stp_pin,false);
			}
		}
		delay(MOVE_DELAY);
	}
	curr_x = 0;
	curr_y = 0;
	curr_z = 0;
	//send current coordinates to serial
	write_coord(curr_x,curr_y,curr_z);
}

// take step for stepper motor
void movement::take_step(int dir_pin, int step_pin, bool is_cw)
{
	// set spinning direction
	if (is_cw == true)
	{
		digitalWrite(dir_pin, HIGH);
	}
	else
	{
		digitalWrite(dir_pin, LOW);
	}
	// spin the stepper motor for one step
	// delay is required [us]
	digitalWrite(step_pin, HIGH);
	delayMicroseconds(step_delay);
	digitalWrite(step_pin, LOW);
	delayMicroseconds(step_delay);
}

// check if switch is pressed
bool movement::is_pressed(int switch_pin)
{
	if (digitalRead(switch_pin) == LOW)
	{
		// switch is pressed
		return true;
	}
	else
	{
		// switch is not pressed
		return false;
	}
}

// function to write coordinates to serial (for Python serial comm)
void movement::write_coord(float x, float y, float z)
{
	Serial.print(x);
	Serial.print(",");
	Serial.print(y);
	Serial.print(",");
	Serial.println(z);
}
