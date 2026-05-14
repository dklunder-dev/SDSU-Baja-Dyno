#include "HX711.h"

// ---------------- Pins ----------------
const int PIN_PRESS_HI = A0;
const int PIN_PRESS_LO = A1;
const int PIN_HX711_DT = 4;
const int PIN_HX711_SCK = 3;
const int PIN_RPM = 2;

// ---------------- Calibration ----------------
const float HX711_CAL_FACTOR = 37731.48f;
const float PRESS_SLOPE = 1190.13f;
const float PRESS_INTERCEPT = -1171.62f;

// ---------------- Logging ----------------
const unsigned long LOG_PERIOD_US = 10000; // 100 Hz

// ---------------- Settings ----------------
const int PRESS_AVG_SAMPLES = 4;
const unsigned long RPM_TIMEOUT_US = 500000;

// ---------------- RPM ----------------
volatile unsigned long lastPulseUs = 0;
volatile unsigned long pulsePeriodUs = 0;

void rpmISR() {
  unsigned long now = micros();
  unsigned long dt = now - lastPulseUs;
  if (lastPulseUs != 0 && dt > 0) {
    pulsePeriodUs = dt;
  }
  lastPulseUs = now;
}

// ---------------- HX711 ----------------
HX711 scale;

// ---------------- Helpers ----------------
float readVoltage(int pin) {
  return analogRead(pin) * (5.0 / 1023.0);
}

float computeRPM(unsigned long nowUs) {
  unsigned long p, last;
  noInterrupts();
  p = pulsePeriodUs;
  last = lastPulseUs;
  interrupts();

  if (last == 0 || (nowUs - last) > RPM_TIMEOUT_US || p == 0) {
    return 0.0;
  }

  return 60000000.0 / (float)p;
}

// ---------------- Setup ----------------
void setup() {
  Serial.begin(115200);

  pinMode(PIN_RPM, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(PIN_RPM), rpmISR, FALLING);

  scale.begin(PIN_HX711_DT, PIN_HX711_SCK);
  scale.set_scale(HX711_CAL_FACTOR);
  scale.tare();

  Serial.println("t_us,pressV,pressPsi,loadKg,rpm");
}

// ---------------- Loop ----------------
void loop() {
  static unsigned long nextLogUs = micros();
  static float lastLoadKg = 0.0f;

  unsigned long nowUs = micros();

  if ((long)(nowUs - nextLogUs) >= 0) {

    // Pressure
    float sumHi = 0, sumLo = 0;
    for (int i = 0; i < PRESS_AVG_SAMPLES; i++) {
      sumHi += readVoltage(PIN_PRESS_HI);
      sumLo += readVoltage(PIN_PRESS_LO);
    }

    float vHi = sumHi / PRESS_AVG_SAMPLES;
    float vLo = sumLo / PRESS_AVG_SAMPLES;
    float pressV = vHi - vLo;
    float pressPsi = PRESS_SLOPE * pressV + PRESS_INTERCEPT;

    // Load cell
    if (scale.is_ready()) {
      lastLoadKg = scale.get_units(1);
    }

    // RPM
    float rpm = computeRPM(nowUs);

    // Output CSV
    Serial.print(nowUs);
    Serial.print(",");
    Serial.print(pressV, 6);
    Serial.print(",");
    Serial.print(pressPsi, 2);
    Serial.print(",");
    Serial.print(lastLoadKg, 3);
    Serial.print(",");
    Serial.println(rpm, 1);

    nextLogUs += LOG_PERIOD_US;
  }
}
