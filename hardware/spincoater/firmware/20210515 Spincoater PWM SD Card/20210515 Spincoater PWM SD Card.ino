// ------ Imports and Variable Definitions
#include "spincoater.h"

/*Motor*/
#include <ServoTimer2.h>
ServoTimer2 ESC1;

/*RPM Sensor*/
#include <FreqMeasure.h> // Can only use Pin 8
double sum = 0;
int count = 0;
double rpm_window[RPM_WINDOW_SIZE];
double rpm_sense = 0;

/*Serial Communication*/
char rxChar; // RXcHAR holds the received command.

/*RPM Setpoint Calculation*/
unsigned int rpm0 = 0;
unsigned int rpm1 = 0;
unsigned long time0 = millis();
unsigned long time1 = time0;
int pwm_current = 0;
int pwm_target = 0;
double rpm_target = 0;

/* SD Card + RTC (real time clock) */
#include "SD.h"
#include <Wire.h>
#include "RTClib.h"
RTC_DS1307 RTC; // define the Real Time Clock object
File logfile;
char filename[] = "RPMLOG.CSV";
bool loggingactive = false;

// ------ Functions
/*Relay Control*/
void relay_off(int pin) { digitalWrite(pin, LOW) }
void relay_on(int pin) { digitalWrite(pin, HIGH) }

void esc_off() { relay_off(ESC_RELAY) }
void esc_on() { relay_on(ESC_RELAY) }
void vacuum_off() { relay_off(VACUUM_SOLENOID_RELAY) }
void vacuum_on() { relay_on(VACUUM_SOLENOID_RELAY) }
void lock_chuck() { relay_on(ELECTROMAGNET_RELAY) }
void unlock_chuck() { relay_off(ELECTROMAGNET_RELAY) }

void relaysetup()
{
  pinMode(ESC_RELAY, OUTPUT);
  pinMode(ELECTROMAGNET_RELAY, OUTPUT);
  pinMode(VACUUM_SOLENOID_RELAY, OUTPUT);

  relay_off(ESC_RELAY);
  relay_off(ELECTROMAGNET_RELAY);
  relay_off(VACUUM_SOLENOID_RELAY);
}

/*Rotor Control*/
void calibrateESC() // recalibrates the PWM settings on the spincoater ESC
{
  esc_off();
  delay(2000);
  esc_on();
  ESC1.write(MAX_SIGNAL); //option to calibrate ESC
  delay(5000);
  ESC1.write(MIN_SIGNAL); // ESC initialization procedure requires 3s of min throttle
  delay(4000);
}

void senseRPM()
{
  if (FreqMeasure.available())
  {
    // average several reading together
    sum -= rpm_window[count];
    rpm_window[count] = FreqMeasure.read();
    sum += rpm_window[count];
    count += 1;
    if (count >= RPM_WINDOW_SIZE)
    {
      count = 0;
    }
    float frequency = FreqMeasure.countToFrequency(sum / RPM_WINDOW_SIZE);
    rpm_sense = frequency * 2 / MOTOR_POLES * 60;
  }
}

// void jumpstartRPM(void)
// {
//   ESC1.write(JUMPSTART_SIGNAL);
//   delay(JUMPSTART_DELAY);
// }

void setRPM(int rpm_setpoint, int duration)
{
  rpm0 = rpm1;
  rpm1 = rpm_setpoint;
  time0 = millis();
  time1 = time0 + duration;
}

void executeRPM()
{
  // unsigned int time_now = millis()
  rpm_target = map(millis(), time0, time1, rpm0, rpm1);
  if (rpm1 > rpm0)
  {
    rpm_target = constrain(rpm_target, rpm0, rpm1);
  }
  else
  {
    rpm_target = constrain(rpm_target, rpm1, rpm0);
  }

  if (rpm_target == 0)
  {
    pwm_target = 0;
  }
  else
  {
    pwm_target = map(rpm_target, MIN_RPM, MAX_RPM, MIN_SIGNAL, MAX_SIGNAL);
  }

  if (pwm_target != pwm_current)
  {
    ESC.write(pwm_target);
    pwm_current = pwm_target;
  }
}

/* SD Card */
void SDcardsetup()
{
  pinMode(SD_CHIP_SELECT, OUTPUT);
  SD.begin(SD_CHIP_SELECT); // Activate SD card

  Wire.begin(); // Activate realtime clock
  RTC.begin();
}

void logging_start()
{
  logfile = SD.open(filename, FILE_WRITE);
  loggingactive = true;
  //write header
  logfile.println('Datetime, Target RPM, Actual RPM')
}

void writetolog()
{
  DateTime now;

  digitalWrite(SD_GREEN_LED, HIGH);

  // fetch the time
  now = RTC.now();
  // log time
  logfile.print(now.year(), DEC);
  logfile.print("/");
  logfile.print(now.month(), DEC);
  logfile.print("/");
  logfile.print(now.day(), DEC);
  logfile.print(" ");
  logfile.print(now.hour(), DEC);
  logfile.print(":");
  logfile.print(now.minute(), DEC);
  logfile.print(":");
  logfile.print(now.second(), DEC);
  // log target rpm
  logfile.print(rpm_target);
  logfile.print(',');
  logfile.println(rpm_sense);

  digitalWrite(SD_GREEN_LED, LOW);
}

void logging_stop()
{
  logfile.close();
  loggingactive = false;
}

void printlogtoserial()
{
  if loggingactive: // cant read while logging is active
    Serial.println("Error: Cannot read log while logging is active!")
    return
  logfile = SD.open(filename, FILE_READ);
  digitalWrite(SD_GREEN_LED, HIGH);
  while (logfile.available())
  {
    Serial.write(logfile.read());
  }
  logfile.close();
  digitalWrite(SD_GREEN_LED, LOW);
}

/*Communication*/
void comLINK()
{
  if (Serial.available())
  {                         // Check receive buffer.
    rxChar = Serial.read(); // Save character received.
    switch (rxChar)
    {
    case 'r': //set RPM
    case 'R':
      int rpm = Serial.parseInt();
      int duration = Serial.parseInt(SKIP_WHITESPACE);
      setRPM(rpm, duration);
      break;
    case 'c': //control the chuck electromagnet
    case 'C':
      int state = Serial.parseInt();
      if (state == 1)
      {
        lock_chuck();
      }
      else
      {
        unlock_chuck();
      }
      break;
    case 'v': //control the vacuum line solenoid
    case 'V':
      int state = Serial.parseInt();
      if (state == 1)
      {
        vacuum_on();
      }
      else
      {
        vacuum_off();
      }
      break;
    case 'l': //start/stop rpm logging to SD card
    case 'L':
      int state = Serial.parseInt();
      if (state == 1)
      {
        logging_start();
      }
      else
      {
        logging_stop();
      }
      break;
    case 'd': // dump log data to serial buffer.
    case 'D':
      printlogtoserial();
      break;
    }
  }
}

// ------ Setup

void setup()
{
  Serial.begin(BAUDRATE); // Open serial port (57600 bauds).try changing to higher frequency to see if we can use the same line as the senseRPM
  Serial.flush();         // Clear receive buffer.

  relaysetup(); // initialize all relay pins + set to off

  ESC1.attach(ESC_PIN);
  calibrateESC(); //calibrate PWM range for rotor control - takes about 10 seconds

  for (int i = 0; i < RPM_WINDOW_SIZE; i++) //initialize rpm moving average window array
  {
    rpm_window[i] = 0;
  }

  FreqMeasure.begin(); //start measuring RPM
}

// ------ Main Loop
void loop()
{
  comLINK();
  senseRPM();
  executeRPM();
  if loggingactive:
    writetolog();
}
