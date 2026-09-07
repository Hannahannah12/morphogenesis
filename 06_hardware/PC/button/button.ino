const int BUTTON_PIN = 2;
const int PRESSED_STATE = HIGH;

int stableState;
int lastReading;

unsigned long lastChangeTime = 0;
const unsigned long debounceDelay = 30;  // 消抖时间，单位 ms

void setup() {
  Serial.begin(115200);

  pinMode(BUTTON_PIN, INPUT);

  lastReading = digitalRead(BUTTON_PIN);
  stableState = lastReading;

  Serial.println("Button test started.");
}

void loop() {
  int reading = digitalRead(BUTTON_PIN);

  // 检测原始信号变化
  if (reading != lastReading) {
    lastChangeTime = millis();
    lastReading = reading;
  }

  // 信号稳定超过 30 ms 后，才确认状态变化
  if (millis() - lastChangeTime >= debounceDelay) {
    if (reading != stableState) {
      stableState = reading;

      if (stableState == PRESSED_STATE) {
        Serial.println("Button clicked successfully!");
      } else {
        Serial.println("Button released.");
      }
    }
  }
}