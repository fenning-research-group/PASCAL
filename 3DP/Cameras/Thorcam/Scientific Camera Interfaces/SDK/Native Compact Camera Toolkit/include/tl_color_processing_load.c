#include "tl_color_processing_load.h"
#include "tl_color_error.h"
#include <math.h>

#ifndef THORLABS_TSI_BUILD_DLL

TL_COLOR_CREATE_COLOR_PROCESSOR tl_color_create_color_processor;
TL_COLOR_GET_BLUE_INPUT_LUT tl_color_get_blue_input_LUT;
TL_COLOR_GET_GREEN_INPUT_LUT tl_color_get_green_input_LUT;
TL_COLOR_GET_RED_INPUT_LUT tl_color_get_red_input_LUT;
TL_COLOR_ENABLE_INPUT_LUTS tl_color_enable_input_LUTs;
TL_COLOR_APPEND_MATRIX tl_color_append_matrix;
TL_COLOR_CLEAR_MATRIX tl_color_clear_matrix;
TL_COLOR_GET_BLUE_OUTPUT_LUT tl_color_get_blue_output_LUT;
TL_COLOR_GET_GREEN_OUTPUT_LUT tl_color_get_green_output_LUT;
TL_COLOR_GET_RED_OUTPUT_LUT tl_color_get_red_output_LUT;
TL_COLOR_ENABLE_OUTPUT_LUTS tl_color_enable_output_LUTs;
TL_COLOR_TRANSFORM_48_TO_48 tl_color_transform_48_to_48;
TL_COLOR_TRANSFORM_48_TO_32 tl_color_transform_48_to_32;
TL_COLOR_TRANSFORM_48_TO_24 tl_color_transform_48_to_24;
TL_COLOR_DESTROY_COLOR_PROCESSOR tl_color_destroy_color_processor;

static void* color_processing_handle = 0;

static TL_COLOR_PROCESSING_MODULE_INITIALIZE tl_color_processing_module_initialize = 0;
static TL_COLOR_PROCESSING_MODULE_TERMINATE tl_color_processing_module_terminate = 0;

#ifdef _WIN32
#include "windows.h"
#endif

#ifdef _WIN32
static const char* COLOR_PROCESSING_MODULE_NAME = "thorlabs_tsi_color_processing.dll";
static HMODULE color_processing_obj = NULL;
#else
// Linux stuff here
#endif

/// <summary>
///     Initializes the color_processing function pointers to 0.
/// </summary>
static void init_color_processing_function_pointers()
{
	tl_color_create_color_processor = 0;
	tl_color_get_blue_input_LUT = 0;
	tl_color_get_green_input_LUT = 0;
	tl_color_get_red_input_LUT = 0;
	tl_color_enable_input_LUTs = 0;
	tl_color_append_matrix = 0;
	tl_color_clear_matrix = 0;
	tl_color_get_blue_output_LUT = 0;
	tl_color_get_green_output_LUT = 0;
	tl_color_get_red_output_LUT = 0;
	tl_color_enable_output_LUTs = 0;
	tl_color_transform_48_to_48 = 0;
	tl_color_transform_48_to_32 = 0;
	tl_color_transform_48_to_24 = 0;
	tl_color_destroy_color_processor = 0;
}

static int init_error_cleanup()
{
#ifdef _WIN32
	if (color_processing_obj != NULL)
	{
		FreeLibrary(color_processing_obj);
		color_processing_obj = NULL;
	}
#else
	//Linux specific stuff
#endif
	init_color_processing_function_pointers();
	tl_color_processing_module_initialize = 0;
	tl_color_processing_module_terminate = 0;
	return (1);
}

/// <summary>
///     Loads the color processing module and maps all the functions so that they can be called directly.
/// </summary>
/// <returns>
///     1 for error, 0 for success
/// </returns>
int tl_color_processing_initialize(void)
{
	//printf("Entering tl_camera_sdk_dll_initialize");
	init_color_processing_function_pointers();

	// Platform specific code to get a handle to the SDK kernel module.
#ifdef _WIN32
	//printf("Before loading unified sdk kernel");
	color_processing_obj = LoadLibraryA("thorlabs_tsi_color_processing.dll");
	int lastError = GetLastError();
	if (!color_processing_obj)
	{
		return (init_error_cleanup());
	}

	tl_color_processing_module_initialize = (TL_COLOR_PROCESSING_MODULE_INITIALIZE)(GetProcAddress(color_processing_obj, (char*) "tl_color_processing_module_initialize"));
	if (!tl_color_processing_module_initialize)
	{
		return (init_error_cleanup());
	}

	tl_color_create_color_processor = (TL_COLOR_CREATE_COLOR_PROCESSOR)(GetProcAddress(color_processing_obj, (char*) "tl_color_create_color_processor"));
	if (!tl_color_create_color_processor)
	{
		return (init_error_cleanup());
	}

	tl_color_get_blue_input_LUT = (TL_COLOR_GET_BLUE_INPUT_LUT)(GetProcAddress(color_processing_obj, (char*) "tl_color_get_blue_input_LUT"));
	if (!tl_color_get_blue_input_LUT)
	{
		return (init_error_cleanup());
	}
	
	tl_color_get_green_input_LUT = (TL_COLOR_GET_GREEN_INPUT_LUT)(GetProcAddress(color_processing_obj, (char*) "tl_color_get_green_input_LUT"));
	if (!tl_color_get_green_input_LUT)
	{
		return (init_error_cleanup());
	}
	
	tl_color_get_red_input_LUT = (TL_COLOR_GET_RED_INPUT_LUT)(GetProcAddress(color_processing_obj, (char*) "tl_color_get_red_input_LUT"));
	if (!tl_color_get_red_input_LUT)
	{
		return (init_error_cleanup());
	}

	tl_color_enable_input_LUTs = (TL_COLOR_ENABLE_INPUT_LUTS)(GetProcAddress(color_processing_obj, (char*) "tl_color_enable_input_LUTs"));
	if (!tl_color_enable_input_LUTs)
	{
		return (init_error_cleanup());
	}

	tl_color_append_matrix = (TL_COLOR_APPEND_MATRIX)(GetProcAddress(color_processing_obj, (char*) "tl_color_append_matrix"));
	if (!tl_color_append_matrix)
	{
		return (init_error_cleanup());
	}

	tl_color_clear_matrix = (TL_COLOR_CLEAR_MATRIX)(GetProcAddress(color_processing_obj, (char*) "tl_color_clear_matrix"));
	if (!tl_color_clear_matrix)
	{
		return (init_error_cleanup());
	}

	tl_color_get_blue_output_LUT = (TL_COLOR_GET_BLUE_OUTPUT_LUT)(GetProcAddress(color_processing_obj, (char*) "tl_color_get_blue_output_LUT"));
	if (!tl_color_get_blue_output_LUT)
	{
		return (init_error_cleanup());
	}

	tl_color_get_green_output_LUT = (TL_COLOR_GET_GREEN_OUTPUT_LUT)(GetProcAddress(color_processing_obj, (char*) "tl_color_get_green_output_LUT"));
	if (!tl_color_get_green_output_LUT)
	{
		return (init_error_cleanup());
	}

	tl_color_get_red_output_LUT = (TL_COLOR_GET_RED_OUTPUT_LUT)(GetProcAddress(color_processing_obj, (char*) "tl_color_get_red_output_LUT"));
	if (!tl_color_get_red_output_LUT)
	{
		return (init_error_cleanup());
	}

	tl_color_enable_output_LUTs = (TL_COLOR_ENABLE_OUTPUT_LUTS)(GetProcAddress(color_processing_obj, (char*) "tl_color_enable_output_LUTs"));
	if (!tl_color_enable_output_LUTs)
	{
		return (init_error_cleanup());
	}

	tl_color_transform_48_to_48 = (TL_COLOR_TRANSFORM_48_TO_48)(GetProcAddress(color_processing_obj, (char*) "tl_color_transform_48_to_48"));
	if (!tl_color_transform_48_to_48)
	{
		return (init_error_cleanup());
	}

	tl_color_transform_48_to_32 = (TL_COLOR_TRANSFORM_48_TO_32)(GetProcAddress(color_processing_obj, (char*) "tl_color_transform_48_to_32"));
	if (!tl_color_transform_48_to_32)
	{
		return (init_error_cleanup());
	}

	tl_color_transform_48_to_24 = (TL_COLOR_TRANSFORM_48_TO_24)(GetProcAddress(color_processing_obj, (char*) "tl_color_transform_48_to_24"));
	if (!tl_color_transform_48_to_24)
	{
		return (init_error_cleanup());
	}

	tl_color_destroy_color_processor = (TL_COLOR_DESTROY_COLOR_PROCESSOR)(GetProcAddress(color_processing_obj, (char*) "tl_color_destroy_color_processor"));
	if (!tl_color_destroy_color_processor)
	{
		return (init_error_cleanup());
	}


	tl_color_processing_module_terminate = (TL_COLOR_PROCESSING_MODULE_TERMINATE)(GetProcAddress(color_processing_obj, (char*) "tl_color_processing_module_terminate"));
	if (!tl_color_processing_module_terminate)
	{
		return (init_error_cleanup());
	}
#else
	// Linux specific stuff
#endif

	if (tl_color_processing_module_initialize() != TL_COLOR_NO_ERROR)
	{
#ifdef _WIN32
		if (color_processing_obj != NULL)
		{
			FreeLibrary(color_processing_obj);
			color_processing_obj = NULL;
		}
#else
		//Linux specific stuff
#endif
		return (init_error_cleanup());
	}

	return (0);
}

int tl_color_processing_terminate(void)
{
	if (tl_color_processing_module_terminate)
	{
		tl_color_processing_module_terminate();
	}

#ifdef _WIN32
	if (color_processing_obj != NULL)
	{
		FreeLibrary(color_processing_obj);
		color_processing_obj = NULL;
	}
#else
	//Linux specific stuff
#endif

	init_color_processing_function_pointers();
	return (0);
}


double sRGBCompand(double colorPixelIntensity)
{
	const double expFactor = 1 / 2.4;
	return ((colorPixelIntensity <= 0.0031308) ? colorPixelIntensity * 12.92 : ((1.055 * pow(colorPixelIntensity, expFactor)) - 0.055));
}


void sRGB_companding_LUT(int bit_depth, int* lut)
{
	int max_pixel_value = (1 << bit_depth) - 1;
	int LUT_size = max_pixel_value + 1;
	const double dMaxValue = (double) (max_pixel_value);
	for (int i = 0; i < LUT_size; ++i)
		lut[i] = (unsigned short) (sRGBCompand((double) (i) / dMaxValue) * dMaxValue);
}

#endif
