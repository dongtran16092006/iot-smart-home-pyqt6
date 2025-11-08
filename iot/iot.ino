#include <Servo.h>
#include <DHT.h>

// ---------------- Pins ----------------
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

// ---------------- State ----------------
int thrLow  = 380;
int thrHigh = 450;
bool modeAuto = true;  // luôn Auto
int ledVal   = 0;
int fanVal   = 0;
int servoDeg = 0;
int alarmVal = 0;

Servo myServo;
unsigned long lastStatusMs = 0;
unsigned long lastManualServoMs = 0;

// ---------------- Helpers ----------------
int clamp01(int x){ return x<=0?0:1; }

long readDistanceCm(){
  if(!USE_ULTRASONIC) return -1;
  digitalWrite(TRIG_PIN, LOW); delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH); delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);
  unsigned long dur = pulseIn(ECHO_PIN, HIGH, 30000UL);
  if(!dur) return -1;
  return (long)(dur / 58);
}

// ---------------- Serial JSON status ----------------
void sendStatus(bool force=false){
  unsigned long now = millis();
  if(!force && now - lastStatusMs < 1000) return;  // 1 Hz
  lastStatusMs = now;

  int gas = analogRead(GAS_PIN);
  long dist = readDistanceCm();
  float temp = dht.readTemperature();
  float humi = dht.readHumidity();

  bool overHi = (gas >= thrHigh);
  bool belowLo = (gas <= thrLow);
  bool recentlyManual = (millis() - lastManualServoMs < 5000);

  // ---------------- AUTO LOGIC ----------------
  if (!recentlyManual) {
    if (overHi) {  // 🚨 GAS cao
      alarmVal = 1;
      digitalWrite(ALARM_PIN, HIGH);
      digitalWrite(FAN_PIN, HIGH);
      digitalWrite(LED_PIN, HIGH);
      fanVal = 1;   // ✅ cập nhật giá trị logic
      ledVal = 1;   // ✅ để GUI nhận đúng
      if (servoDeg != 90) { servoDeg = 90; myServo.write(servoDeg); }
    } 
    else if (belowLo) {  // 🟢 GAS thấp → tắt auto, về manual
      alarmVal = 0;
      digitalWrite(ALARM_PIN, LOW);
      digitalWrite(FAN_PIN, fanVal);
    
      ledVal = 0;                        // ✅ reset LED về 0
      digitalWrite(LED_PIN, ledVal);     // tắt đèn
    }
    else {  // 🟡 Giữa hai ngưỡng
      alarmVal = 1;
      digitalWrite(ALARM_PIN, HIGH);
      digitalWrite(FAN_PIN, HIGH);
      digitalWrite(LED_PIN, HIGH);
      fanVal = 1;
      ledVal = 1;
    }

    // --- AUTO DISTANCE ---
    if (dist > 0) {
      if (dist <= 50) {
        if (servoDeg != 90) { servoDeg = 90; myServo.write(servoDeg); }
      } 
      else if (dist > 50 && !overHi) {
        if (servoDeg != 0) { servoDeg = 0; myServo.write(servoDeg); }
      }
    }
  }

  // ---------------- GỬI JSON ----------------
  Serial.print("{\"gas\":"); Serial.print(gas);
  Serial.print(",\"distance\":"); Serial.print(dist);
  Serial.print(",\"temperature\":");
  if (isnan(temp)) Serial.print("null"); else Serial.print(temp);
  Serial.print(",\"humidity\":");
  if (isnan(humi)) Serial.print("null"); else Serial.print(humi);
  Serial.print(",\"threshold_low\":"); Serial.print(thrLow);
  Serial.print(",\"threshold_high\":"); Serial.print(thrHigh);
  Serial.print(",\"mode\":\"AUTO\"");
  Serial.print(",\"led\":"); Serial.print(ledVal);
  Serial.print(",\"fan\":"); Serial.print(fanVal);
  Serial.print(",\"servo\":"); Serial.print(servoDeg);
  Serial.print(",\"alarm\":"); Serial.print(alarmVal);
  Serial.println("}");
  Serial.flush();
}

// ---------------- Command Parser ----------------
bool parseIntAfterSpace(const String& s,int& v){
  int sp=s.indexOf(' '); if(sp<0)return false;
  v=s.substring(sp+1).toInt(); return true;
}

void handleCommand(String cmd){
  cmd.trim(); cmd.toUpperCase();
  int v;

  if(cmd=="STATUS"){ sendStatus(true); return; }

  if(cmd.startsWith("LED")){ 
    if(parseIntAfterSpace(cmd,v)){ 
      ledVal = clamp01(v);
      digitalWrite(LED_PIN, ledVal);
      sendStatus(true);   // ✅ phản hồi ngay cho GUI

    } 
    return;
  }

  if(cmd.startsWith("FAN")){ 
    if(parseIntAfterSpace(cmd,v)){ 
      fanVal = clamp01(v);
      digitalWrite(FAN_PIN, fanVal);
    } 
    return;
  }

  if(cmd.startsWith("SERVO")){ 
    if(parseIntAfterSpace(cmd,v)){ 
      servoDeg = constrain(v, 0, 180);
      myServo.write(servoDeg);
      lastManualServoMs = millis();
      sendStatus(true);
    } 
    return;
  }

  if(cmd.startsWith("THRHI")){ 
    if(parseIntAfterSpace(cmd,v)){ thrHigh=constrain(v,0,1023);} 
    return;
  }

  if(cmd.startsWith("THRLO")){ 
    if(parseIntAfterSpace(cmd,v)){ thrLow=constrain(v,0,1023);} 
    return;
  }

  if(cmd.startsWith("ALARM")){ 
    if(parseIntAfterSpace(cmd,v)){ 
      alarmVal=clamp01(v);
      digitalWrite(ALARM_PIN,alarmVal);
    } 
    return; 
  }
}

// ---------------- Setup & Loop ----------------
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

  lastManualServoMs = millis();
  sendStatus(true);
}

void loop(){
  static String buf;
  while(Serial.available()){
    char c=(char)Serial.read();
    if(c=='\n'||c=='\r'){ 
      if(buf.length()){ handleCommand(buf); buf=""; } 
    } else if((unsigned char)c>=32) buf+=c;
  }

  sendStatus(false); // gửi 1 Hz
}
