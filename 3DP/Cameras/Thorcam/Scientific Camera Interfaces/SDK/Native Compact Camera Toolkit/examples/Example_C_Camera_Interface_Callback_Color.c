/*	Color Callback Example
*
*	Goes through each step to open up the SDKs for a Thorlabs compact-scientific camera, sets the
*	exposure to 10ms, waits for a snapshot, then closes the camera and SDKs. This method
*	uses a callback that is registered with the camera prior to taking an image. This callback
*	returns an image buffer on a worker thread.
*
*	By default, this example is going to perform software triggering. There are comments explaining
*	how to edit the example to use hardware triggering.
*
*	The event model used here is for Windows operating systems. To port the example to another OS,
*	a different concurrent locking structure will have to be used.
*
*	Include the following files in your application to utilize the camera sdk:
*		tl_camera_sdk.h
*		tl_camera_sdk_load.h
*		tl_camera_sdk_load.c
*
*	After acquiring a frame from the camera, this example uses the mono to color processing SDK to color the image.
*	The mono to color processing SDK reduces the complexity of the color processing suite, but some advanced color
*	processing details are unavailable.
*
*	Include the following files in your application to utilize the mono to color processing sdk:
*		tl_mono_to_color_processing.h
*		tl_mono_to_color_enum.h
*		tl_mono_to_color_processing_load.h
*		tl_mono_to_color_processing_load.c
*		tl_color_enum.h
*/


#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "windows.h"
#include "tl_camera_sdk.h"
#include "tl_camera_sdk_load.h"
#include "tl_color_enum.h"
#include "tl_mono_to_color_processing_load.h"
#include "tl_mono_to_color_processing.h"

HANDLE frame_acquired_event = 0;
int is_camera_sdk_open = 0;
int is_camera_dll_open = 0;
void *camera_handle = 0;
int is_mono_to_color_sdk_open = 0;
void *mono_to_color_processor_handle = 0;

int report_error_and_cleanup_resources(char *error_string);
int initialize_camera_resources();

volatile int is_first_frame_finished = 0;
unsigned short *callback_image_buffer_copy = 0;
unsigned short *output_buffer = 0;
int image_width = 0;
int image_height = 0;

// The callback that is registered with the camera
void frame_available_callback(void* sender, unsigned short* image_buffer, int frame_count, unsigned char* metadata, int metadata_size_in_bytes, void* context)
{
	if (is_first_frame_finished)
		return;

	printf("image buffer = 0x%p\n", image_buffer);
	printf("frame_count = %d\n", frame_count);
	printf("meta data buffer = 0x%p\n", metadata);
	printf("metadata size in bytes = %d\n", metadata_size_in_bytes);

	is_first_frame_finished = 1;
	SetEvent(frame_acquired_event);

	// If you need to save the image data for application specific purposes, this would be the place to copy it into separate buffer.
	if (callback_image_buffer_copy)
		memcpy(callback_image_buffer_copy, image_buffer, (sizeof(unsigned short) * image_width * image_height));
}

void camera_connect_callback(char* camera_serial_number, enum USB_PORT_TYPE usb_bus_speed, void* context)
{
	printf("camera %s connected with bus speed = %d!\n", camera_serial_number, usb_bus_speed);
}

void camera_disconnect_callback(char* camera_serial_number, void* context)
{
	printf("camera %s disconnected!\n", camera_serial_number);
}

int main(void)
{
	if (initialize_camera_resources())
		return 1;

	// Initializes the mono to color dll and sdk
	if (tl_mono_to_color_processing_initialize())
		return report_error_and_cleanup_resources("Failed to initialize mono to color processing sdk!\n");
	is_mono_to_color_sdk_open = 1;

	// Query the camera for all the parameters needed to construct a mono to color processor
	enum TL_CAMERA_SENSOR_TYPE camera_sensor_type;
	enum TL_COLOR_FILTER_ARRAY_PHASE color_filter_array_phase;
	float color_correction_matrix[9];
	float default_white_balance_matrix[9];
	int bit_depth;

	if (tl_camera_get_camera_sensor_type(camera_handle, &camera_sensor_type))
		return report_error_and_cleanup_resources(tl_camera_get_last_error());

	if (tl_camera_get_color_filter_array_phase(camera_handle, &color_filter_array_phase))
		return report_error_and_cleanup_resources(tl_camera_get_last_error());

	if (tl_camera_get_color_correction_matrix(camera_handle, color_correction_matrix))
		return report_error_and_cleanup_resources(tl_camera_get_last_error());

	if (tl_camera_get_default_white_balance_matrix(camera_handle, default_white_balance_matrix))
		return report_error_and_cleanup_resources(tl_camera_get_last_error());

	if (tl_camera_get_bit_depth(camera_handle, &bit_depth))
		return report_error_and_cleanup_resources(tl_camera_get_last_error());

	if (camera_sensor_type != TL_CAMERA_SENSOR_TYPE_BAYER)
		return report_error_and_cleanup_resources("Camera is not a color camera, color processing cannot continue.\n");

	// Construct a mono to color processor
	if (tl_mono_to_color_create_mono_to_color_processor(
		camera_sensor_type,
		color_filter_array_phase,
		color_correction_matrix,
		default_white_balance_matrix,
		bit_depth,
		&mono_to_color_processor_handle))
		return report_error_and_cleanup_resources(tl_mono_to_color_get_last_error());

	// Set the camera connect event callback. This is used to register for run time camera connect events.
	if (tl_camera_set_camera_connect_callback(camera_connect_callback, 0))
		return report_error_and_cleanup_resources(tl_camera_get_last_error());

	// Set the camera disconnect event callback. This is used to register for run time camera disconnect events.
	if (tl_camera_set_camera_disconnect_callback(camera_disconnect_callback, 0))
		return report_error_and_cleanup_resources(tl_camera_get_last_error());

	// Set the exposure
	long long const exposure = 10000; // 10 ms
	if (tl_camera_set_exposure_time(camera_handle, exposure))
		return report_error_and_cleanup_resources(tl_camera_get_last_error());
	printf("Camera exposure set to %lld\n", exposure);

    // Set the gain
    int gain_min;
    int gain_max;
    if (tl_camera_get_gain_range(camera_handle, &gain_min, &gain_max))
        return report_error_and_cleanup_resources(tl_camera_get_last_error());
    if (gain_max > 0)
    {
        // this camera supports gain, set it to 6.0 decibels
        const double gain_dB = 6.0;
        int gain_index;
        if (tl_camera_convert_decibels_to_gain(camera_handle, gain_dB, &gain_index))
            return report_error_and_cleanup_resources(tl_camera_get_last_error());
        tl_camera_set_gain(camera_handle, gain_index);
    }

	// Configure camera for continuous acquisition by setting the number of frames to 0.
	// This project only waits for the first frame before exiting
	if (tl_camera_set_frames_per_trigger_zero_for_unlimited(camera_handle, 0))
		return report_error_and_cleanup_resources(tl_camera_get_last_error());

	// Set the frame available callback
	if (tl_camera_set_frame_available_callback(camera_handle, frame_available_callback, 0))
		return report_error_and_cleanup_resources(tl_camera_get_last_error());

	/**HARDWARE TRIGGER**/
	/*
		The alternative to software triggering. This is specified by tl_camera_set_operation_mode().
		By default, the operation mode is TL_CAMERA_OPERATION_MODE_SOFTWARE_TRIGGERED, which means that
		the camera will not be listening for hardware triggers.
		TL_CAMERA_OPERATION_MODE_HARDWARE_TRIGGERED means for each hardware trigger the camera will take an image
		with exposure equal to the current value of tl_camera_get_exposure_time_us().
		TL_CAMERA_OPERATION_MODE_BULB means that exposure will be equal to the duration of the high pulse (or low, depending on polarity).

		Uncomment the next two blocks of code to set the trigger polarity and set the camera operation mode to Hardware Triggered mode.
	*/
	//// Set the trigger polarity for hardware triggers (ACTIVE_HIGH or ACTIVE_LOW)
	//if (tl_camera_set_trigger_polarity(camera_handle, TL_CAMERA_TRIGGER_POLARITY_ACTIVE_HIGH))
	//	return report_error_and_cleanup_resources(tl_camera_get_last_error());

	//// Set trigger mode
	//if (tl_camera_set_operation_mode(camera_handle, TL_CAMERA_OPERATION_MODE_HARDWARE_TRIGGERED))
	//	return report_error_and_cleanup_resources(tl_camera_get_last_error());
	//printf("Hardware trigger mode activated\n");

	// Arm the camera.
	// if Hardware Triggering, make sure to set the operation mode before arming the camera.
	if (tl_camera_arm(camera_handle, 2))
		return report_error_and_cleanup_resources(tl_camera_get_last_error());
	printf("Camera armed\n");

	// Get image width and height
	if (tl_camera_get_image_width(camera_handle, &image_width))
		return report_error_and_cleanup_resources(tl_camera_get_last_error());
	if (tl_camera_get_image_height(camera_handle, &image_height))
		return report_error_and_cleanup_resources(tl_camera_get_last_error());

	// Allocate space for the callback image buffer copy
	callback_image_buffer_copy = malloc(sizeof(unsigned short) * image_width * image_height);
	// Allocate space for the final color image
	output_buffer = (unsigned short *)malloc(sizeof(unsigned short) * image_width * image_height * 3); // color image size will be 3x the size of a mono image

	/**SOFTWARE TRIGGER**/
	/*
		Once the camera is initialized and armed, this function sends a trigger command to the camera over USB, GE, or CL.
		Camera will return images using a worker thread to call frame_available_callback.
		Continuous acquisition is specified by setting the number of frames to 0 and issuing a single software trigger request.

		Comment out the following code block if using Hardware Triggering.
	*/
	if (tl_camera_issue_software_trigger(camera_handle))
		return report_error_and_cleanup_resources(tl_camera_get_last_error());
	printf("Software trigger sent\n");

	// Wait to get an image from the frame available callback
	printf("Waiting for an image...\n");
	for (;;)
	{
		WaitForSingleObject(frame_acquired_event, INFINITE);
		if (is_first_frame_finished) break;
	}

	printf("Image received!\n");
	// callback_image_buffer_copy now has the unprocessed image

	// transform to 48 bpp
	if (tl_mono_to_color_transform_to_48(mono_to_color_processor_handle, callback_image_buffer_copy, image_width, image_height, output_buffer))
		return report_error_and_cleanup_resources(tl_mono_to_color_get_last_error());

	/* output_buffer now contains a color image. Once the color image is no longer needed, remember to release its memory. */

	// Stop the camera.
	if (tl_camera_disarm(camera_handle))
		report_error_and_cleanup_resources(tl_camera_get_last_error());

	//Clean up and exit
	return report_error_and_cleanup_resources(0);
}

/*
	Initializes camera sdk and opens the first available camera. Returns a nonzero value to indicate failure.
 */
int initialize_camera_resources()
{
	// Initializes camera dll
	if (tl_camera_sdk_dll_initialize())
		return report_error_and_cleanup_resources("Failed to initialize dll!\n");
	printf("Successfully initialized dll\n");
	is_camera_dll_open = 1;

	// Open the camera SDK
	if (tl_camera_open_sdk())
		return report_error_and_cleanup_resources("Failed to open SDK!\n");
	printf("Successfully opened SDK\n");
	is_camera_sdk_open = 1;

	char camera_ids[1024];
	camera_ids[0] = 0;

	// Discover cameras.
	if (tl_camera_discover_available_cameras(camera_ids, 1024))
		return report_error_and_cleanup_resources(tl_camera_get_last_error());
	printf("camera IDs: %s\n", camera_ids);

	// Check for no cameras.
	if (!strlen(camera_ids))
		return report_error_and_cleanup_resources("Did not find any cameras!\n");

	// Camera IDs are separated by spaces.
	char* p_space = strchr(camera_ids, ' ');
	if (p_space)
		*p_space = '\0'; // isolate the first detected camera
	char first_camera[256];

	// Copy the ID of the first camera to separate buffer (for clarity)
	strcpy_s(first_camera, 256, camera_ids);
	printf("First camera_id = %s\n", first_camera);

	// Connect to the camera (get a handle to it).
	if (tl_camera_open_camera(first_camera, &camera_handle))
		return report_error_and_cleanup_resources(tl_camera_get_last_error());
	printf("Camera handle = 0x%p\n", camera_handle);

	return 0;
}

/*
	Reports the given error string if it is not null and closes any opened resources. Returns the number of errors that occured during cleanup, +1 if error string was not null.
*/
int report_error_and_cleanup_resources(const char *error_string)
{
	int num_errors = 0;

	if (error_string)
	{
		printf("Error: %s\n", error_string);
		num_errors++;
	}

	printf("Closing all resources...\n");

	if (camera_handle)
	{
		if (tl_camera_close_camera(camera_handle))
		{
			printf("Failed to close camera!\n%s\n", tl_camera_get_last_error());
			num_errors++;
		}
		camera_handle = 0;
	}
	if (is_camera_sdk_open)
	{
		if (tl_camera_close_sdk())
		{
			printf("Failed to close camera SDK!\n");
			num_errors++;
		}
		is_camera_sdk_open = 0;
	}
	if (is_camera_dll_open)
	{
		if (tl_camera_sdk_dll_terminate())
		{
			printf("Failed to close camera dll!\n");
			num_errors++;
		}
		is_camera_dll_open = 0;
	}
	if (mono_to_color_processor_handle)
	{
		if(tl_mono_to_color_destroy_mono_to_color_processor(mono_to_color_processor_handle))
		{
			printf("Failed to destroy mono to color processor\n");
			num_errors++;
		}
		mono_to_color_processor_handle = 0;
	}
	if(is_mono_to_color_sdk_open)
	{
		if(tl_mono_to_color_processing_terminate())
		{
			printf("Failed to close mono to color SDK!\n");
			num_errors++;
		}
		is_mono_to_color_sdk_open = 0;
	}
	if (frame_acquired_event)
	{
		if (!CloseHandle(frame_acquired_event))
		{
			printf("Failed to close concurrent data structure!\n");
			num_errors++;
		}
	}
	if(callback_image_buffer_copy)
	{
		free(callback_image_buffer_copy);
		callback_image_buffer_copy = 0;
	}
	if(output_buffer)
	{
		free(output_buffer);
		output_buffer = 0;
	}

	printf("Closing resources finished.\n");
	return num_errors;
}
