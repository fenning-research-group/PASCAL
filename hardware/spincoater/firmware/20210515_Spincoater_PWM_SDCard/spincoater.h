// ------ Pin Definitions
#define ESC_PWM 9               // PWM pin for ESC control
#define RPM_SENSOR 8            // FreqMeasure library only works on pin 8!
#define ESC_RELAY 3             // Relay to provide power to ESC
#define ELECTROMAGNET_RELAY 4   // Relay to provide power to electromagnet to lock rotor
#define VACUUM_SOLENOID_RELAY 2 // Relay to provide power to solenoid to pull vacuum on chuck
#define SD_CHIP_SELECT 10       // Pin to activate SD card readwrite
#define SD_GREEN_LED 5          // Pin to indicate active read/write to SD
// ------ Communication
#define BAUDRATE 57600

// ------ RPM Control
/*PWM values to calibrate ESC range*/
#define MIN_SIGNAL 700
#define MAX_SIGNAL 2000

/*PWM values that will actually cause rotor to spin*/
#define MIN_USABLE_SIGNAL 802
#define JUMPSTART_SIGNAL 840 //value below which the rotor will stall unless already spinning
#define MAX_USABLE_SIGNAL 1900

/*achievable speed range*/
#define MIN_RPM 1000
#define JUMPSTART_RPM_CUTOFF 1400
#define MAX_RPM 7000
#define JUMPSTART_DELAY 1000 //ms, time to wait between jumpstarting and going to target rpm

// ------ RPM Sensing
#define RPM_WINDOW_SIZE 3 //number of rpm readings to average
#define MOTOR_POLES 14    // number of magnetic poles present in BLDC motor

// ------ SD Card Logging
#define LOG_INTERVAL 250 // delay (ms) between entries
#define WAIT_TO_START 0   // Wait for serial input in setup()
