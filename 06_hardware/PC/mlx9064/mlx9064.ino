#include <Wire.h>

const uint8_t MLX90640_ADDRESS = 0x33;
const uint16_t EEPROM_START = 0x2400;
const uint16_t EEPROM_WORDS = 832;

bool readWord(uint16_t registerAddress, uint16_t &value) {
  Wire.beginTransmission(MLX90640_ADDRESS);
  Wire.write(registerAddress >> 8);
  Wire.write(registerAddress & 0xFF);

  if (Wire.endTransmission(false) != 0) {
    return false;
  }

  if (Wire.requestFrom(MLX90640_ADDRESS, (uint8_t)2) != 2) {
    return false;
  }

  value = ((uint16_t)Wire.read() << 8);
  value |= Wire.read();

  return true;
}

void setup() {
  Serial.begin(115200);

  // Mega固定使用SDA 20、SCL 21
  Wire.begin();
  Wire.setClock(400000);

  delay(1000);

  Wire.beginTransmission(MLX90640_ADDRESS);

  if (Wire.endTransmission() != 0) {
    Serial.println("MLX90640 not found at 0x33.");
    Serial.println("Check VCC, GND, SDA 20 and SCL 21.");
    return;
  }

  Serial.println("MLX90640 found.");
  Serial.println("Copy everything between { and };");
  Serial.println();
  Serial.println("const PROGMEM uint16_t factoryCalData[832] = {");

  for (uint16_t i = 0; i < EEPROM_WORDS; i++) {
    uint16_t value;

    if (!readWord(EEPROM_START + i, value)) {
      Serial.println();
      Serial.print("READ ERROR at address 0x");
      Serial.println(EEPROM_START + i, HEX);
      return;
    }

    Serial.print(value);

    if (i < EEPROM_WORDS - 1) {
      Serial.print(", ");
    }

    if ((i + 1) % 8 == 0) {
      Serial.println();
    }
  }

  Serial.println();
  Serial.println("};");
  Serial.println();
  Serial.println("Calibration dump complete.");
}

void loop() {
}