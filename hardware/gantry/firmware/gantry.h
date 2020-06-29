/*
	movement.h - library for conctrolling movement
	Written by Manuel Saldana
	MAE 156B Spring 2020, Team 13
*/

#ifndef movement_h
#define movement_h

#include "Arduino.h"

class movement
{
	// user-accessible public interface
	public:
		// function that handles the creation and setup of instances
		movement(void);

		// function to initialize movement pins
		void init_move(void);

		// set position [mm]
		void set_position(float,float,float);

		// get current x,y,z coordinates
		float get_curr_x(void);
		float get_curr_y(void);
		float get_curr_z(void);

		// go to home position (and reset position)
		void go_home(void);

		// arm offset, x [mm]
		// from center of gripper (where sample would be)
		// to center of threaded rod (from z translation)
		const float arm_off_x = 185;

		// arm offset, z [mm]
		// from table top
		// to bottom of gripper tips
		const float arm_off_z = 285;

	// library-accessible private interface
	private:

		// digital pins for stepper motors
		const int x_dir_pin = 9;
		const int x_stp_pin = 8;
		const int y_dir_pin = 11;
		const int y_stp_pin = 10;
		const int z_dir_pin = 13;
		const int z_stp_pin = 12;

		// digital pins for limit switches
		const int lim_x_min_pin = 48;
		const int lim_x_max_pin = 49;
		const int lim_y_min_pin = 51;
		const int lim_y_max_pin = 50;
		const int lim_z_min_pin = 53;
		const int lim_z_max_pin = 52;

		// steps per revolution (for stepper motors)
		const int steps_per_rev = 200;

		// time delay for movement [milli sec]
		const int move_delay = 500;

		// time delay for stepper motor step [micro sec]
		// 1000 us is optimal speed
		const int step_delay = 1000;
		
		// current x,y,z position [mm]
		float curr_x;
		float curr_y;
		float curr_z;

		// home position [mm]
		const float home_x = 0;
		const float home_y = 0;
		const float home_z = 0;

		// set resolution of stepper motors [mm per step]
		const float step_x = 0.2;
		const float step_y = 0.3;
		const float step_z = 0.04;

		// set tolerance values for x,y,z [mm]
		const float tol_x = 0.1;
		const float tol_y = 0.1;
		const float tol_z = 0.02;

		// take a step for stepper motor
		void take_step(int,int,bool);

		// check if switch is pressed
		bool is_pressed(int);
		
		// write coordinares to serial (for Python serial comm)
		void write_coord(float,float,float);
};

#endif
