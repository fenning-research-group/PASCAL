#include "tl_color_demosaic_load.h"

#ifndef THORLABS_TSI_BUILD_DLL

TL_DEMOSAIC_TRANSFORM_16_TO_48 tl_demosaic_transform_16_to_48;

static void* demosaic_handle = 0;

static TL_DEMOSAIC_MODULE_INITIALIZE tl_demosaic_module_initialize = 0;
static TL_DEMOSAIC_MODULE_TERMINATE tl_demosaic_module_terminate = 0;

#ifdef _WIN32
#include "windows.h"
#endif

#ifdef _WIN32
static const char* DEMOSAIC_MODULE_NAME = "thorlabs_tsi_demosaic.dll";
static HMODULE demosaic_obj = NULL;
#else
// Linux stuff here
#endif

/// <summary>
///     Initializes the demosaic function pointers to 0.
/// </summary>
static void init_demosaic_function_pointers()
{
	tl_demosaic_transform_16_to_48 = 0;
}

static int init_error_cleanup()
{
	#ifdef _WIN32
		if (demosaic_obj != NULL)
		{
			FreeLibrary(demosaic_obj);
			demosaic_obj = NULL;
		}
	#else
		//Linux specific stuff
	#endif
	init_demosaic_function_pointers();
	tl_demosaic_module_initialize = 0;
	tl_demosaic_module_terminate = 0;
	return (1);
}

/// <summary>
///     Loads the demosaic module and maps all the functions so that they can be called directly.
/// </summary>
/// <returns>
///     1 for error, 0 for success
/// </returns>
int tl_demosaic_initialize(void)
{
	//printf("Entering tl_camera_sdk_dll_initialize");
	init_demosaic_function_pointers();

	// Platform specific code to get a handle to the SDK kernel module.
#ifdef _WIN32
	//printf("Before loading unified sdk kernel");
	demosaic_obj = LoadLibraryA("thorlabs_tsi_demosaic.dll");
	int lastError = GetLastError();
	if (!demosaic_obj)
	{
		return (init_error_cleanup());
	}

	tl_demosaic_module_initialize = (TL_DEMOSAIC_MODULE_INITIALIZE)(GetProcAddress(demosaic_obj, (char*) "tl_demosaic_module_initialize"));
	if (!tl_demosaic_module_initialize)
	{
		return (init_error_cleanup());
	}

	tl_demosaic_transform_16_to_48 = (TL_DEMOSAIC_TRANSFORM_16_TO_48)(GetProcAddress(demosaic_obj, (char*) "tl_demosaic_transform_16_to_48"));
	if (!tl_demosaic_module_initialize)
	{
		return (init_error_cleanup());
	}

	tl_demosaic_module_terminate = (TL_DEMOSAIC_MODULE_TERMINATE)(GetProcAddress(demosaic_obj, (char*) "tl_demosaic_module_terminate"));
	if (!tl_demosaic_module_terminate)
	{
		return (init_error_cleanup());
	}
#else
	// Linux specific stuff
#endif

	if (tl_demosaic_module_initialize())
	{
#ifdef _WIN32
		if (demosaic_obj != NULL)
		{
			FreeLibrary(demosaic_obj);
			demosaic_obj = NULL;
		}
#else
		//Linux specific stuff
#endif
		return (init_error_cleanup());
	}

	return (0);
}

int tl_demosaic_terminate(void)
{
	if (tl_demosaic_module_terminate)
	{
		tl_demosaic_module_terminate();
	}
	
#ifdef _WIN32
	if (demosaic_obj != NULL)
	{
		FreeLibrary(demosaic_obj);
		demosaic_obj = NULL;
	}
#else
	//Linux specific stuff
#endif

	init_demosaic_function_pointers();
	return (0);
}

#endif
