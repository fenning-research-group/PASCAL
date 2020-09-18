#include "spincoater.h"

// --------- Motor
#include <ServoTimer2.h>
ServoTimer2 ESC1;

// --------- relay 
int relay1 = 10;
int relay2 = 11;
int relay3 = 12;
int relay4 = 13;
unsigned int relay_number = 0;

// --------- RPM Sensor
#include <FreqMeasure.h> // Can only use Pin 8
double sum = 0;
int count = 0;
double rpm_window[RPM_WINDOW_SIZE];
double rpm_sense = 0;

// --------- PID Control
#include <PID_v1.h>
//Specify the links and initial tuning parameters
double pwm_output = 0;
double rpm_setpoint = 0;
PID myPID(&rpm_sense, &pwm_output, &rpm_setpoint, .08, .09, 0, P_ON_E, DIRECT); // PID values are not optimized, P_ON_M vs P_ON_M not tested
bool pid_switch = false;


// --------- Serial Communication
char rxChar = 0;        // RXcHAR holds the received command.
unsigned int rpm = 0;
unsigned int rpm2 = 0;
unsigned int duration = 0;

// --------- Setup


void calibrateESC(){
  ESC1.write(MAX_SIGNAL); //option to calibrate ESC, (1 of 2)
  delay(5000);            // (2 of 2)
  ESC1.write(MIN_SIGNAL);// ESC initialization procedure requires 3s of min throttle
  delay(4000); // to hold at least 3s  
}

void setup() {
  Serial.begin(57600);  // Open serial port (9600 bauds).try changing to higher frequency to see if we can use the same line as the senseRPM
  Serial.flush();       // Clear receive buffer.

  ESC1.attach(ESC_PIN);
  calibrateESC();
  // ESC1.write(MIN_SIGNAL);// ESC initialization procedure requires 3s of min throttle
  // delay(4000); // to hold at least 3s  

  for(int i = 0; i < RPM_WINDOW_SIZE; i++){ //initialize rpm moving average window array
    rpm_window[i] = 0;
  }
  
  FreqMeasure.begin(); //comment out for comLINK to run
  myPID.SetOutputLimits(MIN_USABLE_SIGNAL, MAX_USABLE_SIGNAL); // if min is set to MIN_SIGNAL, off can be achieved but stabilization may be an issue
  myPID.SetMode(AUTOMATIC); // turns on PID

  relaysetup();
}


// --------- Functions

void relaysetup(){
  pinMode(relay1, OUTPUT);
  pinMode(relay2, OUTPUT);
  pinMode(relay3, OUTPUT);
  pinMode(relay4, OUTPUT);

  digitalWrite(relay1, HIGH);
  digitalWrite(relay2, HIGH);
  digitalWrite(relay3, HIGH);
  digitalWrite(relay4, HIGH);
}

void relayon(int relay_number){
  if (relay_number == 1){
    relay_number = relay1;
  }

  if (relay_number == 2){
    relay_number = relay2;
  }  

  if (relay_number == 3){
    relay_number = relay3;
  }
  if (relay_number == 4){
    relay_number = relay4;
  }
     
  digitalWrite(relay_number, LOW);

  
  if (relay_number == relay1){
    calibrateESC();
  }
}

void relayoff(int relay_number){
  if (relay_number == 1){
    relay_number = relay1;
  }

  if (relay_number == 2){
    relay_number = relay2;
  }  

  if (relay_number == 3){
    relay_number = relay3;
  }
  if (relay_number == 4){
    relay_number = relay4;
  }
  
  digitalWrite(relay_number, HIGH);
}

void senseRPM() {
  if (FreqMeasure.available()) {
    // average several reading together
    sum -= rpm_window[count];
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
    analogWrite(9, 0);
  }else if(rpm_setpoint <= JUMPSTART_RPM_CUTOFF){
    jumpstartRPM();
  }
  
  int pwm = map(rpm, MIN_RPM, MAX_RPM, MIN_SIGNAL, MAX_SIGNAL);
  
  // force RPM moving average window to = target RPM initially, prevents the overshoot. 
  // should probably tune PID to address this,but this is a hacky "fix" kind of
  for(int i = 0; i < RPM_WINDOW_SIZE; i++){ //initialize rpm moving average window array
    rpm_window[i] = rpm;
  }
  sum = rpm * RPM_WINDOW_SIZE;
  ///
  
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

void runPID() {
  myPID.Compute(); // calculates new 'pwm_output'
//  pwm_send = (int) pwm_output/; //needs to be converted to integer to be able to write it
  ESC1.write((int) pwm_output);
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

      case 'i': // open a relay
      case 'I':
        
        relay_number = Serial.parseInt();
        relayon(relay_number);
        break;

      case 'o': // close a relay
      case 'O':
        
        relay_number = Serial.parseInt();
        relayoff(relay_number);
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
}
// --------- Loop
void loop() {
  senseRPM();
  comLINK();
  if (pid_switch) {
    runPID(); // this will make PID constantly write new pwm value to motor
  }
}
