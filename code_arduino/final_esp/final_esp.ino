#include <DHT.h>
#include <Servo.h>

// ===== PINS =====
#define DHTPIN 7
#define DHTTYPE DHT11
#define TRIG 9
#define ECHO 10
#define LM_PIN A0
#define LDR_PIN A1
#define IR_PIN A2
#define SERVO_PIN 8

// ===== OBJETS =====
DHT dht(DHTPIN, DHTTYPE);
Servo myServo;

// ===== VARIABLES =====
float dist = 0;
float temp = 0;
float lm = 0;
int hum = 0;
int ldr = 0;
int ir = 0;
int irMax = 0;


unsigned long lastSend = 0;
unsigned long lastServo = 0;


// ================== BILLE ==================
const int pinGauche = 2;
const int pinDroite = 3;
int lastEtatG = HIGH;
int lastEtatD = HIGH;
int compteurMouvement = 0;
unsigned long lastCheckBille = 0;
char position[12] = "DROIT";
char secousse[8] = "STABLE";


// ===== DISTANCE SIMPLE ET FIABLE =====
float lireDistance() {
  digitalWrite(TRIG, LOW);
  delayMicroseconds(2);

  digitalWrite(TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG, LOW);

  long d = pulseIn(ECHO, HIGH, 30000);

  if (d == 0) return -1;

  float distance = d * 0.034 / 2;

  if (distance < 2 || distance > 400) return -1;

  return distance;
}

// ===== LECTURE CAPTEURS =====
void lireCapteurs() {
  dist = lireDistance();
int irActuel = analogRead(IR_PIN);

if (irActuel > irMax) {
  irMax = irActuel;
}

  

  lm = analogRead(LM_PIN) * 0.37;
  ldr = analogRead(LDR_PIN);

  float t = dht.readTemperature();
  float h = dht.readHumidity();

  if (!isnan(t)) temp = t;
  if (!isnan(h)) hum = (int)h;
}


// ================== BILLE ==================
void lireBille() {
  int etatG = digitalRead(pinGauche);
  int etatD = digitalRead(pinDroite);

  if (etatG != lastEtatG || etatD != lastEtatD) compteurMouvement++;
  lastEtatG = etatG;
  lastEtatD = etatD;

  if (millis() - lastCheckBille > 1000) {
    lastCheckBille = millis();

    // Secousse
    if (compteurMouvement > 5) strcpy(secousse, "SECOUE");
    else                        strcpy(secousse, "STABLE");
    compteurMouvement = 0;

    // Position
    if      (etatG == HIGH && etatD == LOW)  strcpy(position, "GAUCHE");
    else if (etatD == HIGH && etatG == LOW)  strcpy(position, "DROITE");
    else if (etatG == HIGH && etatD == HIGH) strcpy(position, "RETOURNE");
    else                                      strcpy(position, "DROIT");
  }
}


// ===== ENVOI JSON SIMPLE =====
void sendToESP() {
  Serial.println(); // IMPORTANT séparation ligne

  Serial.print("{");
  Serial.print("\"dist\":"); Serial.print(dist); Serial.print(",");
  Serial.print("\"temp\":"); Serial.print(temp); Serial.print(",");
  Serial.print("\"hum\":");  Serial.print(hum); Serial.print(",");
  Serial.print("\"lm\":");   Serial.print(lm); Serial.print(",");
  Serial.print("\"ldr\":");  Serial.print(ldr); Serial.print(",");
  Serial.print("\"ir\":");   Serial.print(irMax); Serial.print(",");
  Serial.print("\"pos\":\""); Serial.print(position); Serial.print("\",");
  Serial.print("\"stab\":\""); Serial.print(secousse); Serial.print("\"");
  Serial.println("}");

  irMax = 0;
}
// ===== SETUP =====
void setup() {
  Serial.begin(115200);

  pinMode(TRIG, OUTPUT);
  pinMode(ECHO, INPUT);

  dht.begin();
  delay(2000); // important pour DHT

  myServo.attach(SERVO_PIN);
  myServo.write(0);

  Serial.println("SYSTEM READY");
}

// ===== LOOP =====
void loop() {
  lireCapteurs();
  lireBille();


  // envoi vers ESP8266 toutes les 2s
  if (millis() - lastSend > 2000) {
    lastSend = millis();
    Serial.println("=== ENVOI JSON ===");
    sendToESP();
  }

  // servo toutes les 12s
  if (millis() - lastServo > 8000) {
    lastServo = millis();
    myServo.write(60);
    delay(200);
    myServo.write(0);
  }

  delay(50);
}
