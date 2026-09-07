const int STEP_PIN = 2;
const int DIR_PIN = 3;

const long STEPS_PER_MOVE = 18000;

const int START_DELAY_US = 700;
const int FAST_DELAY_US = 200;
const long ACCEL_STEPS = 1000;

void pulseStep(int delayUs) {
  digitalWrite(STEP_PIN, LOW);
  delayMicroseconds(delayUs);
  digitalWrite(STEP_PIN, HIGH);
  delayMicroseconds(delayUs);
}

void moveSteps(long totalSteps) {
  long rampSteps = min(ACCEL_STEPS, totalSteps / 2);

  for (long i = 0; i < totalSteps; i++) {
    int delayUs;

    if (i < rampSteps) {
      delayUs = START_DELAY_US -
                (long)(START_DELAY_US - FAST_DELAY_US) * i / rampSteps;
    } else if (i >= totalSteps - rampSteps) {
      long remaining = totalSteps - 1 - i;
      delayUs = START_DELAY_US -
                (long)(START_DELAY_US - FAST_DELAY_US) * remaining / rampSteps;
    } else {
      delayUs = FAST_DELAY_US;
    }

    pulseStep(delayUs);
  }
}

void setup() {
  pinMode(STEP_PIN, OUTPUT);
  pinMode(DIR_PIN, OUTPUT);

  digitalWrite(STEP_PIN, HIGH);
}

void loop() {
  digitalWrite(DIR_PIN, HIGH);
  delay(50);
  moveSteps(STEPS_PER_MOVE);

  delay(1000);

  digitalWrite(DIR_PIN, LOW);
  delay(50);
  moveSteps(STEPS_PER_MOVE);

  delay(1000);
}