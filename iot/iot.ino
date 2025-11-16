#include <Servo.h>
#include <DHT.h>

const int GAS_PIN   = A0;
const int LED_PIN   = 5;
const int FAN_PIN   = 7;
const int SERVO_PIN = 10;
const int ALARM_PIN = 6;
const int DHT_PIN   = 2;
const int TRIG_PIN  = 11;
const int ECHO_PIN  = 12;

#define DHTTYPE DHT11
DHT dht(DHT_PIN, DHTTYPE);

const bool USE_ULTRASONIC = true;

int thrLow  = 380;
int thrHigh = 450;
bool modeAuto = true;

int ledVal   = 0;
int fanVal   = 0;
int servoDeg = 0;

// ⚠ ALARM KHÔNG BAO GIỜ CHO MANUAL
int alarmVal = 0;

Servo myServo;
unsigned long lastStatusMs = 0;
bool busySerial = false;

int clamp01(int x){ return x<=0?0:1; }

// ----------------- SIÊU ÂM -----------------
long readDistanceCm(){
  if(!USE_ULTRASONIC) return -1;
  digitalWrite(TRIG_PIN, LOW); delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH); delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);
  unsigned long dur = pulseIn(ECHO_PIN, HIGH, 25000UL);
  if(!dur) return -1;
  return (long)(dur / 58);
}


// ----------------- GỬI JSON + AUTO LOGIC -----------------
void sendStatus(bool force=false){
  unsigned long now = millis();
  if(!force && now - lastStatusMs < 1000) return;
  lastStatusMs = now;

  int gas = analogRead(GAS_PIN);
  long dist = readDistanceCm();
  float temp = dht.readTemperature();
  float humi = dht.readHumidity();

  bool overHi = (gas >= thrHigh);
  bool belowLo = (gas <= thrLow);

  // ----------------- AUTO MODE -----------------
  // ----------------- AUTO MODE -----------------
if (modeAuto) {

    // ----------------- LOA THEO MQ2 -----------------
    alarmVal = overHi ? 1 : 0;
    digitalWrite(ALARM_PIN, alarmVal);

    // ----------------- FAN + LED THEO MQ2 -----------------
    if (overHi) {
        fanVal = 1; digitalWrite(FAN_PIN, HIGH);
        ledVal = 1; digitalWrite(LED_PIN, HIGH);

        // 🔥 CHÁY → MỞ CỬA, BỎ QUA SIÊU ÂM
        if (servoDeg != 90) { servoDeg = 90; myServo.write(90); }
    }
    else if (belowLo) {
        fanVal = 0; digitalWrite(FAN_PIN, LOW);
        ledVal = 0; digitalWrite(LED_PIN, LOW);

        // không cháy → cửa đóng theo MQ2
        if (servoDeg != 0) { servoDeg = 0; myServo.write(0); }
    }
    else {
        fanVal = 1; digitalWrite(FAN_PIN, HIGH);
        ledVal = 1; digitalWrite(LED_PIN, HIGH);
    }

    // ----------------- CỬA THEO SIÊU ÂM -----------------
    // ⚠ SIÊU ÂM CHỈ HOẠT ĐỘNG KHI KHÔNG CHÁY
    if (!overHi && dist > 0) {
        if (dist <= 50) {
            if (servoDeg != 90) { servoDeg = 90; myServo.write(90); }
        } else {
            if (servoDeg != 0) { servoDeg = 0; myServo.write(0); }
        }
    }
}


  // ----------- GỬI JSON -----------
  Serial.print("{\"gas\":"); Serial.print(gas);
  Serial.print(",\"distance\":"); Serial.print(dist);
  Serial.print(",\"temperature\":");
  if (isnan(temp)) Serial.print("null"); else Serial.print(temp);
  Serial.print(",\"humidity\":");
  if (isnan(humi)) Serial.print("null"); else Serial.print(humi);
  Serial.print(",\"threshold_low\":"); Serial.print(thrLow);
  Serial.print(",\"threshold_high\":"); Serial.print(thrHigh);
  Serial.print(",\"mode\":\""); Serial.print(modeAuto ? "AUTO" : "MANUAL"); Serial.print("\"");
  Serial.print(",\"led\":"); Serial.print(ledVal);
  Serial.print(",\"fan\":"); Serial.print(fanVal);
  Serial.print(",\"servo\":"); Serial.print(servoDeg);
  Serial.print(",\"alarm\":"); Serial.print(alarmVal);
  Serial.println("}");
  Serial.flush();
}


// ----------------- LỆNH TỪ GUI -----------------
bool parseIntAfterSpace(const String& s,int& v){
  int sp=s.indexOf(' ');
  if(sp<0) return false;
  v=s.substring(sp+1).toInt();
  return true;
}

void handleCommand(String cmd){
  cmd.trim(); cmd.toUpperCase();
  int v;

  if(cmd=="STATUS"){ sendStatus(true); return; }

  if(cmd.startsWith("AUTO")){
    if(parseIntAfterSpace(cmd,v)){
      modeAuto = clamp01(v);
      sendStatus(true);
    }
    return;
  }

  // ---------- LED MANUAL ----------
  if(cmd.startsWith("LED")){
    if(!modeAuto && parseIntAfterSpace(cmd,v)){
      ledVal = clamp01(v);
      digitalWrite(LED_PIN, ledVal);
      sendStatus(true);
    }
    return;
  }

  // ---------- FAN MANUAL ----------
  if(cmd.startsWith("FAN")){
    if(!modeAuto && parseIntAfterSpace(cmd,v)){
      fanVal = clamp01(v);
      digitalWrite(FAN_PIN, fanVal);
      sendStatus(true);
    }
    return;
  }

  // ---------- SERVO MANUAL ----------
  if(cmd.startsWith("SERVO")){
    if(!modeAuto && parseIntAfterSpace(cmd,v)){
      servoDeg = constrain(v,0,180);
      myServo.write(servoDeg);
      sendStatus(true);
    }
    return;
  }

  if(cmd.startsWith("THRHI")){ if(parseIntAfterSpace(cmd,v)) thrHigh=constrain(v,0,1023); return; }
  if(cmd.startsWith("THRLO")){ if(parseIntAfterSpace(cmd,v)) thrLow =constrain(v,0,1023); return; }
}


// ----------------- SETUP -----------------
void setup(){
  Serial.begin(115200);

  pinMode(GAS_PIN,INPUT);
  pinMode(LED_PIN,OUTPUT);
  pinMode(FAN_PIN,OUTPUT);
  pinMode(ALARM_PIN,OUTPUT);
  if(USE_ULTRASONIC){ pinMode(TRIG_PIN,OUTPUT); pinMode(ECHO_PIN,INPUT); }

  myServo.attach(SERVO_PIN);
  myServo.write(0);

  digitalWrite(LED_PIN,LOW);
  digitalWrite(FAN_PIN,LOW);
  digitalWrite(ALARM_PIN,LOW);

  dht.begin();
  delay(300);
  sendStatus(true);
}


// ----------------- LOOP -----------------
void loop(){
  static String buf;
  busySerial = Serial.available();

  while(Serial.available()){
    char c=(char)Serial.read();
    if(c=='\n'||c=='\r'){
      if(buf.length()){ handleCommand(buf); buf=""; }
    } 
    else if((unsigned char)c>=32) buf+=c;
  }

  if (!busySerial) sendStatus(false);
}
