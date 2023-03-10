#pragma once

#include "tsi_log_priority.h"

typedef void* (*TSI_GET_LOG) (const char*, const char*);
typedef int (*TSI_LOG) (void*, enum TSI_LOG_PRIORITY, const char*, int, const char*, const char*);
typedef void (*TSI_FREE_LOG) (const char*, const char*);
