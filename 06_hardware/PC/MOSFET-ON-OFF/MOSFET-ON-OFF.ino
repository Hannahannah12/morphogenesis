const int PELTIER_MOSFET_PIN = 6;
const int PUMP_MOSFET_PIN = 7;

void setup() {
  pinMode(PELTIER_MOSFET_PIN, OUTPUT);
  pinMode(PUMP_MOSFET_PIN, OUTPUT);

  // 启动时先全部关闭
  digitalWrite(PELTIER_MOSFET_PIN, LOW);
  digitalWrite(PUMP_MOSFET_PIN, LOW);
}

void loop() {
  // Peltier 开启
  digitalWrite(PELTIER_MOSFET_PIN, HIGH);

  // 水泵开启 2 秒
  digitalWrite(PUMP_MOSFET_PIN, HIGH);
  delay(2000);

  // 水泵关闭
  digitalWrite(PUMP_MOSFET_PIN, LOW);

  // Peltier 继续运行 20 秒
  delay(20000);

  // Peltier 关闭
  digitalWrite(PELTIER_MOSFET_PIN, LOW);

  // 全部停止 10 秒
  delay(10000);
}