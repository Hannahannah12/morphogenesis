/*
  MLX90640 raw-data streamer for Arduino Mega 2560

  This sketch does not calculate 768 temperatures on the Mega.
  It sends factory calibration and live raw frames to the companion HTML page.

  Waveshare MLX90640-D55 -> Mega 2560
  VCC -> 5V
  GND -> GND
  SDA -> pin 20 (SDA)
  SCL -> pin 21 (SCL)

  Serial protocol is binary at 115200 baud. Do not open Arduino Serial Monitor
  while the HTML viewer is connected.
*/

#include <Wire.h>

const uint8_t MLX_ADDR = 0x33;
const uint16_t EEPROM_BASE = 0x2400;
const uint16_t STATUS_REG = 0x8000;
const uint16_t CONTROL_REG = 0x800D;

const uint8_t PACKET_CALIBRATION = 1;
const uint8_t PACKET_FRAME = 2;
const uint16_t CAL_WORDS = 832;
const uint16_t FRAME_WORDS = 834;
const uint8_t I2C_CHUNK_WORDS = 16;  // AVR Wire buffer is 32 bytes.

uint16_t frameData[FRAME_WORDS];     // 1668 bytes; safe on Mega's 8 KB RAM.
uint16_t transferBuffer[I2C_CHUNK_WORDS];
uint8_t sequenceNumber = 0;
bool sensorOK = false;

bool readWords(uint16_t startAddress, uint8_t wordCount, uint16_t *destination) {
  if (wordCount == 0 || wordCount > I2C_CHUNK_WORDS) return false;

  Wire.beginTransmission(MLX_ADDR);
  Wire.write((uint8_t)(startAddress >> 8));
  Wire.write((uint8_t)(startAddress & 0xFF));
  if (Wire.endTransmission(false) != 0) return false;

  uint8_t byteCount = (uint8_t)(wordCount * 2);
  uint8_t received = Wire.requestFrom(MLX_ADDR, byteCount);
  if (received != byteCount) {
    while (Wire.available()) Wire.read();
    return false;
  }

  for (uint8_t i = 0; i < wordCount; i++) {
    if (Wire.available() < 2) return false;
    destination[i] = ((uint16_t)Wire.read() << 8) | (uint16_t)Wire.read();
  }
  return true;
}

bool readWord(uint16_t address, uint16_t &value) {
  return readWords(address, 1, &value);
}

bool writeWord(uint16_t address, uint16_t value) {
  Wire.beginTransmission(MLX_ADDR);
  Wire.write((uint8_t)(address >> 8));
  Wire.write((uint8_t)(address & 0xFF));
  Wire.write((uint8_t)(value >> 8));
  Wire.write((uint8_t)(value & 0xFF));
  return Wire.endTransmission() == 0;
}

bool configureSensor() {
  uint16_t control;
  if (!readWord(CONTROL_REG, control)) return false;

  // 2 Hz refresh rate, 18-bit ADC resolution, chess mode.
  control &= (uint16_t)~0x0380;
  control |= (uint16_t)(2 << 7);
  control &= (uint16_t)~0x0C00;
  control |= (uint16_t)(2 << 10);
  control |= 0x1000;
  return writeWord(CONTROL_REG, control);
}

uint16_t crc16Update(uint16_t crc, uint8_t data) {
  crc ^= (uint16_t)data << 8;
  for (uint8_t bit = 0; bit < 8; bit++) {
    if (crc & 0x8000) crc = (uint16_t)((crc << 1) ^ 0x1021);
    else crc <<= 1;
  }
  return crc;
}

void writePacketHeader(uint8_t type, uint8_t sequence, uint16_t wordCount,
                       uint16_t &crc) {
  const uint8_t magic[4] = {'M', 'L', 'X', '4'};
  Serial.write(magic, 4);

  uint8_t countLow = (uint8_t)(wordCount & 0xFF);
  uint8_t countHigh = (uint8_t)(wordCount >> 8);
  Serial.write(type);
  Serial.write(sequence);
  Serial.write(countLow);
  Serial.write(countHigh);

  crc = 0xFFFF;
  crc = crc16Update(crc, type);
  crc = crc16Update(crc, sequence);
  crc = crc16Update(crc, countLow);
  crc = crc16Update(crc, countHigh);
}

void writePayloadWord(uint16_t value, uint16_t &crc) {
  uint8_t highByte = (uint8_t)(value >> 8);
  uint8_t lowByte = (uint8_t)(value & 0xFF);
  Serial.write(highByte);
  Serial.write(lowByte);
  crc = crc16Update(crc, highByte);
  crc = crc16Update(crc, lowByte);
}

void writePacketCRC(uint16_t crc) {
  // CRC itself is little-endian.
  Serial.write((uint8_t)(crc & 0xFF));
  Serial.write((uint8_t)(crc >> 8));
}

bool sendCalibration() {
  uint16_t crc;
  writePacketHeader(PACKET_CALIBRATION, sequenceNumber++, CAL_WORDS, crc);

  uint16_t sent = 0;
  while (sent < CAL_WORDS) {
    uint8_t count = I2C_CHUNK_WORDS;
    if ((uint16_t)(CAL_WORDS - sent) < count) {
      count = (uint8_t)(CAL_WORDS - sent);
    }

    if (!readWords(EEPROM_BASE + sent, count, transferBuffer)) return false;
    for (uint8_t i = 0; i < count; i++) {
      writePayloadWord(transferBuffer[i], crc);
    }
    sent += count;
  }

  writePacketCRC(crc);
  return true;
}

bool waitForFrame(uint16_t &status) {
  uint32_t started = millis();
  while ((uint32_t)(millis() - started) < 1500UL) {
    if (readWord(STATUS_REG, status) && (status & 0x0008)) return true;
    delay(3);
  }
  return false;
}

bool readRegionIntoFrame(uint16_t sensorAddress, uint16_t frameIndex,
                         uint16_t wordCount) {
  uint16_t done = 0;
  while (done < wordCount) {
    uint8_t count = I2C_CHUNK_WORDS;
    if ((uint16_t)(wordCount - done) < count) {
      count = (uint8_t)(wordCount - done);
    }
    if (!readWords(sensorAddress + done, count, &frameData[frameIndex + done])) {
      return false;
    }
    done += count;
  }
  return true;
}

bool captureFrame() {
  uint16_t status;
  if (!waitForFrame(status)) return false;

  uint8_t subpage = (uint8_t)(status & 0x0001);
  if (!writeWord(STATUS_REG, 0x0030)) return false;

  // Read all data quickly first; serial transmission happens afterwards.
  if (!readRegionIntoFrame(0x0400, 0, 768)) return false;
  if (!readRegionIntoFrame(0x0700, 768, 64)) return false;
  if (!readWord(CONTROL_REG, frameData[832])) return false;
  frameData[833] = subpage;
  return true;
}

void sendFrame() {
  uint16_t crc;
  writePacketHeader(PACKET_FRAME, sequenceNumber++, FRAME_WORDS, crc);
  for (uint16_t i = 0; i < FRAME_WORDS; i++) {
    writePayloadWord(frameData[i], crc);
  }
  writePacketCRC(crc);
}

void showError() {
  sensorOK = false;
  digitalWrite(LED_BUILTIN, HIGH);
  delay(150);
  digitalWrite(LED_BUILTIN, LOW);
  delay(150);
}

void setup() {
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW);

  Serial.begin(115200);
  Wire.begin();                 // Mega: SDA=20, SCL=21
  Wire.setClock(400000UL);
  delay(600);

  uint16_t check;
  sensorOK = readWord(EEPROM_BASE, check) && configureSensor();
  if (sensorOK) {
    delay(100);
    sensorOK = sendCalibration();
  }
}

void loop() {
  // The HTML viewer sends 'C' after connecting to request calibration again.
  while (Serial.available()) {
    if (Serial.read() == 'C' && sensorOK) sendCalibration();
  }

  if (!sensorOK) {
    // Retry the sensor periodically. LED flashes while disconnected/error.
    showError();
    uint16_t check;
    sensorOK = readWord(EEPROM_BASE, check) && configureSensor();
    if (sensorOK) sensorOK = sendCalibration();
    return;
  }

  if (!captureFrame()) {
    showError();
    return;
  }

  sendFrame();
}
