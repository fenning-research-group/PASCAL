#include <spincoater.h> 

// --------- Motor
#include <ServoTimer2.h>
ServoTimer2 ESC1;


// --------- RPM Sensor
#include <FreqMeasure.h> // Can only use Pin 8
double sum = 0;
int count = 0;
double rpm_window = {0,0,0,0,0};
double rpm_sense = 0;

// --------- PID Control
#include <PID_v1.h>
//Specify the links and initial tuning parameters
double pwm_output = 0;
double rpm_setpoint = 0;
PID myPID(&rpm_sense, &pwm_output, &rpm_setpoint, .1, .1, 0, P_ON_E, DIRECT); // PID values are not optimized, P_ON_M vs P_ON_M not tested
bool pid_switch = false;


// --------- Serial Communication
char rxChar = 0;        // RXcHAR holds the received command.
unsigned int rpm = 0;
unsigned int rpm2 = 0;
unsigned int duration = 0;

// --------- Setup

void setup() {
  Serial.begin(57600);  // Open serial port (9600 bauds).try changing to higher frequency to see if we can use the same line as the senseRPM
  pinMode(LED, OUTPUT); // Sets pin 13 as OUTPUT.
  Serial.flush();       // Clear receive buffer.

  ESC1.attach(ESC_PIN);
  calibrateESC();
  // ESC1.write(MIN_SIGNAL);// ESC initialization procedure requires 3s of min throttle
  // delay(4000); // to hold at least 3s  

  FreqMeasure.begin(); //comment out for comLINK to run
  myPID.SetOutputLimits(MIN_USABLE_SIGNAL, MAX_USABLE_SIGNAL); // if min is set to MIN_SIGNAL, off can be achieved but stabilization may be an issue
  myPID.SetMode(AUTOMATIC); // turns on PID
}


// --------- Functions

void calibrateESC(){
  ESC1.write(MAX_SIGNAL); //option to calibrate ESC, (1 of 2)
  delay(5000);            // (2 of 2)
  ESC1.write(MIN_SIGNAL);// ESC initialization procedure requires 3s of min throttle
  delay(4000); // to hold at least 3s  
}

void senseRPM() {
  if (FreqMeasure.available()) {
    // average several reading together
    sum -= rpm_window[count]
    rpm_window[count] = FreqMeasure.read();
    sum += rpm_window[count];
    count += 1;
    if (count >= RPM_WINDOW_SIZE){
      count = 0;
    }
    float frequency = FreqMeasure.countToFrequency(sum / RPM_WINDOW_SIZE);
    rpm_sense = frequency * 2 / MOTOR_POLES * 60;
  }
}

void jumpstartRPM(void){
  ESC1.write(JUMPSTART_SIGNAL);
  delay(JUMPSTART_DELAY);
}

void setRPM(int rpm) {

  rpm_setpoint = rpm;
  if(rpm_setpoint == 0){
    ESC1.write(0);
  }else if(rpm_setpoint <= JUMPSTART_RPM_CUTOFF){
    jumpstartRPM();
  }

  int pwm = map(rpm, MIN_RPM, MAX_RPM, MIN_SIGNAL, MAX_SIGNAL);

  /* REK debugging start */
  // char buffer[32];
  // sprintf(buffer, "=== Sending %d  pwm for %d rpm ===", pwm, rpm);
  // Serial.println(buffer);
  /* REK debugging end*/

  ESC1.write(pwm);
}


void rampRPM(int rpm0, int rpm1, int duration) {
  unsigned int long t0 = millis();
  unsigned int long t1 = t0 + duration;
  unsigned int long tnow = millis();
  while (tnow < t1) {
    setRPM(map(tnow, t0, t1, rpm0, rpm1));
    delay(5);
    tnow = millis();
  }
  setRPM(rpm1);
}

void comLINK() {
  if (Serial.available()) {            // Check receive buffer.
    rxChar = Serial.read();            // Save character received.
    switch (rxChar) {
      case 'a': //set RPM, trigger PID loop
      case 'A':
        rpm = Serial.parseInt();
        setRPM(rpm);
        pid_switch = true;
        break;

      case 'b': //set RPM, no PID loop
      case 'B':
        rpm = Serial.parseInt();
        setRPM(rpm);
        break;

      case 'r': // ramp RPM with PID loop
      case 'R':
        pid_switch = true;
        rpm2 = Serial.parseInt();
        duration = Serial.parseInt();
        rampRPM(rpm, rpm2, duration);
        rpm = rpm2;
        break;

      case 'c': //return current rpm reading
      case 'C':
        Serial.println(rpm_sense);
        break;
      case 'z': // stop the spincoater
      case 'Z':
        pid_switch = 0;
        setRPM(0);
        break;
  }
}

void runPID() {
  myPID.Compute(); // calculates new 'pwm_output'
  pwm_send = (int) pwm_output; //needs to be converted to integer to be able to write it
  ESC1.write(pwm_send);
}

// --------- Loop
void loop() {
  senseRPM();
  comLINK();
  if (pid_switch) {
    runPID(); // this will make PID constantly write new pwm value to motor
  }
}
