// --------- Initilization 
// --------- LED
#define LED 13          // Pin 13 to simple LED

// --------- Motor
#include <ServoTimer2.h>
#define ESC_PIN 9     // Pin 9 to LED or actual ESC
ServoTimer2 ESC1;
#define MAX_SIGNAL 2000
#define MIN_SIGNAL 700
double MAX_RPM = 7000;
double MIN_RPM = 2000;

// --------- RPM Sensor
#include <FreqMeasure.h> // Can only use Pin 8
double sum = 0;
int count = 0;
double rpm_sense = 0;
double frequency;
double rpm_check = 0;

// --------- PID Control
#include <PID_v1.h>
//Specify the links and initial tuning parameters
double rpm_output = 0;
double rpm_setpoint = 0;
PID myPID(&rpm_sense, &rpm_output, &rpm_setpoint,1,1,1,P_ON_M, DIRECT); 

// --------- LCD Display
#include <LiquidCrystal.h>
const int rs = 12, en = 11, d4 = 5, d5 = 4, d6 = 3, d7 = 2;
LiquidCrystal lcd(rs, en, d4, d5, d6, d7);
// --------- Serial Communication
char rxChar= 0;         // RXcHAR holds the received command.
unsigned int rpm = 0;
unsigned int rpm2 = 0;
unsigned int duration = 0;
// --------- Setup
void setup(){
  Serial.begin(57600);  // Open serial port (9600 bauds).try changing to higher frequency to see if we can use the same line as the senseRPM
  pinMode(LED, OUTPUT); // Sets pin 13 as OUTPUT.
  Serial.flush();       // Clear receive buffer.
//  printHelp();        // Print the command list.
  lcd.begin(16, 2);
  ESC1.attach(ESC_PIN);
//  ESC1.write(MAX_SIGNAL); //option to calibrate ESC, (1 of 2)
//  delay(5000);            // (2 of 2)
  ESC1.write(MIN_SIGNAL);//start with motor off
  delay(4000);
  FreqMeasure.begin(); //comment out for comLINK to run
  myPID.SetOutputLimits(MIN_RPM, MAX_RPM);
  myPID.SetMode(AUTOMATIC); // turns on PID 
  }
// --------- Funcitons
void printHelp(void){
  Serial.println("--- Command list: ---");
  Serial.println("? -> Print this HELP");  
  Serial.println("a -> Recipe 1  \"activate\"");
  Serial.println("d -> Recipe 2 \"deactivate\"");
  Serial.println("s -> LED     \"status\"");  
  }
void updateLCD(int rpm, int pwm){
  lcd.clear();
  char buffer[16];
  sprintf(buffer, "%d rpm", rpm);
  lcd.setCursor(0,0);
  lcd.print(buffer);
  sprintf(buffer, "%d pwm", pwm);
  lcd.setCursor(0,1);
  lcd.print(buffer);
  }
void blink(){
  if (rpm == 0){
  digitalWrite(LED, LOW);
    }
  else{
  digitalWrite(LED, HIGH);
    }
  }

void senseRPM(){
 if (FreqMeasure.available()) {
  // average several reading together
    sum = sum + FreqMeasure.read();
    count = count + 1;
   // Serial.println("measuring");
  if (count > 10) {
    float frequency = FreqMeasure.countToFrequency(sum / count);
    rpm_sense = frequency *2/14*60;
    Serial.println(rpm_sense);
    sum = 0;
    count = 0;
      }  
  } 
} 
    
void setRPM(int rpm){
  blink();
  char buffer[32];
  sprintf(buffer, "Sending %d Command", rpm);
  Serial.println(buffer);
  int pwm = map(rpm, MIN_RPM, MAX_RPM, MIN_SIGNAL, MAX_SIGNAL);
  ESC1.write(pwm);
  updateLCD(rpm, pwm);
  }
void rampRPM(int rpm0, int rpm1, int duration){
  unsigned int long t0 = millis();
  unsigned int long t1 = t0 + duration;
  unsigned int long tnow = millis();
  while (tnow < t1){
    setRPM(map(tnow, t0, t1, rpm0, rpm1));
    delay(5); 
    tnow = millis();
    }
  setRPM(rpm1);
  }
void comLINK(){
  if (Serial.available()){             // Check receive buffer.
    rxChar = Serial.read();            // Save character received. 
  switch (rxChar) {
    case 'a':
    case 'A':
      rpm = Serial.parseInt();
      setRPM(rpm);
      break;
      
    case 'r':    
    case 'R':
      rpm2 = Serial.parseInt();
      duration = Serial.parseInt();
      rampRPM(rpm, rpm2, duration);
      rpm = rpm2;
      break;

    case 'c':
    case 'C':
      rpm_check = rpm_sense;
      Serial.println(rpm_check);
      break;

    case 'z':
    case 'Z':                          
      setRPM(0);
      break;  
      
    case 's':
    case 'S':                          // If received  's' or 'S':
      if (digitalRead(LED) == HIGH){        // Read LED status.
//          Serial.println("LED status: On");
      }else{ 
//        Serial.println("LED status: Off");
        break;
      }
    case '?':                          // If received a ?:
        printHelp();                   // print the command list.
        break;
//    default:                           
////      Serial.print("'");
////      Serial.print((char)rxChar);
////      Serial.println("' is not a command!");
      }
    Serial.flush(); //flush the buffer after we've finished commands... we shouldnt need this at all if we send commands responsibly, but if it goes anywhere it goes here.
    }
  }
// --------- Loop
void loop(){ 
  senseRPM();
  comLINK();
  }
