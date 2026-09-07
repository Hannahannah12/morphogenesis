#include <Wire.h>
#include <Adafruit_MLX90614.h>

Adafruit_MLX90614 mlx = Adafruit_MLX90614();

void setup() {
  Serial.begin(9600);
  Wire.begin();

  Serial.println("Starting GY-906 / MLX90614...");

  if (!mlx.begin()) {
    Serial.println("Sensor not found. Check VCC, GND, SDA and SCL.");
    while (true) {
      delay(1000);
    }
  }

  Serial.println("Sensor ready.");
}

void loop() {
  float ambientTemperature = mlx.readAmbientTempC();
  float objectTemperature = mlx.readObjectTempC();

  Serial.print("Ambient: ");
  Serial.print(ambientTemperature, 2);
  Serial.print(" C    Object: ");
  Serial.print(objectTemperature, 2);
  Serial.println(" C");

  delay(500);
}