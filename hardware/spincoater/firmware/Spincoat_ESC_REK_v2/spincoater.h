/* Pin Definitions */
#define ESC_PIN 9     // Pin 9 to LED or actual ESC

/* RPM Limits */
//values to calibrate ESC range
#define MIN_SIGNAL 700 //700
#define MAX_SIGNAL 2000 //2000


//values that will actually cause rotor to spin
#define MIN_USABLE_SIGNAL 802 //802
#define JUMPSTART_SIGNAL 840 //840 value below which the rotor will stall unless already spinning
#define MAX_USABLE_SIGNAL 1900 //1900

#define MIN_RPM 1000 //1000
#define JUMPSTART_RPM_CUTOFF 1400
#define MAX_RPM 7000
#define JUMPSTART_DELAY 1000 //ms, time to wait between jumpstarting and going to target rpm

/* RPM Measuring */
#define RPM_WINDOW_SIZE 3 //number of rpm readings to average
#define MOTOR_POLES 14 // number of magnetic poles present in BLDC motor
