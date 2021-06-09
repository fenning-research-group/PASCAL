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
char rxChar = 0; // RXcHAR holds the received command.
int state;       //whether relays turn on or off
unsigned int rpm_setpoint;
unsigned int duration;

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
#include <TimeLib.h>
RTC_DS1307 RTC; // define the Real Time Clock object
File logfile;
char filename[] = "RPMLOG.CSV";
bool loggingactive = false;
unsigned long last_logged = 0;

// ------ Functions
/*Relay Control*/
void relay_off(int pin) { digitalWrite(pin, HIGH); }
void relay_on(int pin) { digitalWrite(pin, LOW); }

void esc_off() { relay_off(ESC_RELAY); }
void esc_on() { relay_on(ESC_RELAY); }
void vacuum_off() { relay_off(VACUUM_SOLENOID_RELAY); }
void vacuum_on() { relay_on(VACUUM_SOLENOID_RELAY); }
void lock_chuck() { relay_on(ELECTROMAGNET_RELAY); }
void unlock_chuck() { relay_off(ELECTROMAGNET_RELAY); }

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
  delay(1000);
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
  rpm_target = constrain(map(millis(), time0, time1, rpm0, rpm1), MIN_RPM, MAX_RPM);
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
    pwm_target = MIN_SIGNAL;
  }
  else
  {
    pwm_target = constrain(map(rpm_target, MIN_RPM, MAX_RPM, MIN_USABLE_SIGNAL, MAX_USABLE_SIGNAL), MIN_USABLE_SIGNAL, MAX_USABLE_SIGNAL);
  }

  //  if (pwm_target != pwm_current)
  //  {
  //    ESC1.write((int) pwm_target);
  //    pwm_current = pwm_target;
  //  }
  ESC1.write(pwm_target);
  pwm_current = pwm_target;
}

/* SD Card */
void SDcardsetup()
{
  pinMode(SD_CHIP_SELECT, OUTPUT);
  SD.begin(SD_CHIP_SELECT); // Activate SD card

  Wire.begin(); // Activate realtime clock
  RTC.begin();
  RTC.adjust(DateTime(__DATE__, __TIME__));
}

void logging_start()
{
  if (SD.exists(filename))
  {
    SD.remove(filename);
  }
  logfile = SD.open(filename, FILE_WRITE);
  loggingactive = true;
  //write header
  logfile.println("Datetime, Target RPM, Actual RPM, PWM Signal");
}

void writetolog()
{
  if (millis() > (last_logged + LOG_INTERVAL))
  {
    last_logged = millis();
  }
  else
  {
    return;
  }
  digitalWrite(SD_GREEN_LED, HIGH);
  //  DateTime now = RTC.now()
  // fetch the time

  // log time
  logfile.print(year(), DEC);
  logfile.print("/");
  logfile.print(month(), DEC);
  logfile.print("/");
  logfile.print(day(), DEC);
  logfile.print(" ");
  logfile.print(hour(), DEC);
  logfile.print(":");
  logfile.print(minute(), DEC);
  logfile.print(":");
  logfile.print(second(), DEC);
  // log target rpm
  logfile.print(",");
  logfile.print(rpm_target);
  logfile.print(',');
  logfile.print(rpm_sense);
  logfile.print(',');
  logfile.println(pwm_current);

  digitalWrite(SD_GREEN_LED, LOW);
}

void logging_stop()
{
  logfile.close();
  loggingactive = false;
}

void printlogtoserial()
{
  if (loggingactive)
  { // cant read while logging is active
    Serial.println("Error: Cannot read log while logging is active!");
    return;
  }
  logfile = SD.open(filename, FILE_READ);
  digitalWrite(SD_GREEN_LED, HIGH);
  while (logfile.available())
  {
    Serial.write(logfile.read());
  }
  logfile.close();
  digitalWrite(SD_GREEN_LED, LOW);
}
/* Realtime Clock */
time_t time_provider()
{
  return RTC.now().unixtime();
}

/*Communication*/
void comLINK()
{
  if (Serial.available())
  {                         // Check receive buffer.
    rxChar = Serial.read(); // Save character received.
    Serial.println(rxChar);
    switch (rxChar)
    {
    case 'r': //set RPM
    case 'R':
      rpm_setpoint = Serial.parseInt();
      duration = Serial.parseInt(SKIP_WHITESPACE);
      setRPM(rpm_setpoint, duration);
      break;
    case 'c': //control the chuck electromagnet
    case 'C':
      //      Serial.println("Received C");
      state = Serial.parseInt();
      if (state == 1)
      {
        lock_chuck();
        //        Serial.println("Electromagnet engaged");
      }
      else
      {
        unlock_chuck();
        //        Serial.println("Electromagnet disengaged");
      }
      break;
    case 'v': //control the vacuum line solenoid
    case 'V':
      state = Serial.parseInt();
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
      state = Serial.parseInt();
      if (state == 1)
      {
        logging_start();
        Serial.println("Starting log");
      }
      else
      {
        logging_stop();
        Serial.println("Stopping log");
      }
      break;
    case 'd': // dump log data to serial buffer.
    case 'D':
      printlogtoserial();
      Serial.println("dumping log");
      break;
    case 'e': //recalibrate ESC
    case 'E':
      calibrateESC();
      break;
    case 't': //set the RTC
    case 'T':
      int y = Serial.parseInt(SKIP_WHITESPACE);
      int m = Serial.parseInt(SKIP_WHITESPACE);
      int d = Serial.parseInt(SKIP_WHITESPACE);
      int hh = Serial.parseInt(SKIP_WHITESPACE);
      int mm = Serial.parseInt(SKIP_WHITESPACE);
      int ss = Serial.parseInt(SKIP_WHITESPACE);
      RTC.adjust(DateTime(y, m, d, hh, mm, ss));
      break;
    }
  }
}

void debugReport()
{
  Serial.print("Target rpm: ");
  Serial.print(rpm_target);
  Serial.print(" Current RPM: ");
  Serial.print(rpm_sense);
  Serial.print(" Target pwm: ");
  Serial.print(pwm_target);
  Serial.print(" Current PWM: ");
  Serial.print(pwm_current);
  Serial.print(" rpm0, rpm1 ");
  Serial.print(rpm0);
  Serial.print(",");
  Serial.println(rpm1);
}
// ------ Setup

void setup()
{
  Serial.begin(BAUDRATE); // Open serial port (57600 bauds).try changing to higher frequency to see if we can use the same line as the senseRPM
  Serial.flush();         // Clear receive buffer.

  relaysetup(); // initialize all relay pins + set to off

  ESC1.attach(ESC_PWM);
  //  calibrateESC(); //calibrate PWM range for rotor control - takes about 10 seconds
  ESC1.write(MIN_SIGNAL);
  for (int i = 0; i < RPM_WINDOW_SIZE; i++) //initialize rpm moving average window array
  {
    rpm_window[i] = 0;
  }

  FreqMeasure.begin(); //start measuring RPM

  SDcardsetup();

  DateTime now = RTC.now();
  setSyncProvider(time_provider); //sets Time Library to RTC time
  setSyncInterval(5);             //sync Time Library to RTC every 5 seconds
}

// ------ Main Loop
void loop()
{
  comLINK();
  senseRPM();
  executeRPM();
  if (loggingactive)
  {
    writetolog();
  }
  debugReport();
}
