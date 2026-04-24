void setup() {
  Serial.begin(115200);
  Serial.println("t_us,pressV,pressPsi,loadKg,rpm");
}

void loop() {
  static unsigned long nextLogUs = micros();
  unsigned long nowUs = micros();

  if ((long)(nowUs - nextLogUs) >= 0) {
    static int n = 0;
    n++;

    float rpm = 1200 + 8.0f * n + 300.0f * sin(n / 18.0f);
    float pressV = 1.0f + 0.00018f * rpm + 0.03f * sin(n / 10.0f);
    float pressPsi = (1190.13f * pressV) - 1171.62f;
    float loadKg = 0.4f + 0.00025f * rpm + 0.05f * sin(n / 12.0f);

    Serial.print(nowUs);
    Serial.print(',');
    Serial.print(pressV, 6);
    Serial.print(',');
    Serial.print(pressPsi, 2);
    Serial.print(',');
    Serial.print(loadKg, 3);
    Serial.print(',');
    Serial.print(rpm, 1);
    Serial.println();

    nextLogUs += 10000;
  }
}