/*
 * Drive-Thru Sensor Node
 * ESP32 + JSN-SR04T Ultrasonic Sensor over RS485
 *
 * Detects car presence using distance thresholds with hysteresis timing
 * to filter out pedestrians and transient objects.
 *
 * Serial output at 115200 baud:
 *   CAR_ARRIVED    - Car detected (below threshold for 2s)
 *   CAR_LEFT       - Car departed (above threshold for 3s)
 *   HB <dist_cm>   - Heartbeat every 5s with current distance
 */

// Pin definitions
#define TRIG_PIN 5
#define ECHO_PIN 18

// Detection thresholds (adjustable)
#define DETECT_CM 150           // Distance threshold in cm
#define ARRIVAL_HOLD_MS 2000    // Must be below threshold for 2s to confirm arrival
#define DEPARTURE_HOLD_MS 3000  // Must be above threshold for 3s to confirm departure

// Timing
#define MEASURE_INTERVAL_MS 100 // Measure every 100ms
#define HEARTBEAT_INTERVAL_MS 5000

// JSN-SR04T specs
#define SOUND_SPEED_CM_US 0.0343  // Speed of sound in cm/microsecond
#define MAX_DISTANCE_CM 400       // Max range of sensor
#define TIMEOUT_US (MAX_DISTANCE_CM * 2 / SOUND_SPEED_CM_US)

// State machine
enum State {
  STATE_IDLE,           // No car, waiting for detection
  STATE_DETECTING,      // Object detected, waiting for confirmation
  STATE_CAR_PRESENT,    // Car confirmed present
  STATE_DEPARTING       // Object gone, waiting for departure confirmation
};

State currentState = STATE_IDLE;
unsigned long stateEntryTime = 0;
unsigned long lastMeasureTime = 0;
unsigned long lastHeartbeatTime = 0;
int lastFilteredDistance = 0;

// Median filter buffer
int distanceBuffer[3] = {MAX_DISTANCE_CM, MAX_DISTANCE_CM, MAX_DISTANCE_CM};
int bufferIndex = 0;

void setup() {
  Serial.begin(115200);

  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);

  digitalWrite(TRIG_PIN, LOW);

  // Initial delay for sensor stabilization
  delay(500);

  Serial.println("SENSOR_READY");
}

// Measure single distance reading
int measureDistance() {
  // Ensure trigger is low
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);

  // Send 10us trigger pulse
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);

  // Read echo pulse with timeout
  unsigned long duration = pulseIn(ECHO_PIN, HIGH, TIMEOUT_US);

  if (duration == 0) {
    return MAX_DISTANCE_CM; // No echo received
  }

  // Calculate distance in cm
  int distance = duration * SOUND_SPEED_CM_US / 2;

  // Clamp to valid range
  if (distance > MAX_DISTANCE_CM) {
    distance = MAX_DISTANCE_CM;
  }
  if (distance < 2) {
    distance = 2; // Minimum valid reading
  }

  return distance;
}

// Get median of 3 readings
int getMedianDistance() {
  int sorted[3];
  memcpy(sorted, distanceBuffer, sizeof(sorted));

  // Simple bubble sort for 3 elements
  for (int i = 0; i < 2; i++) {
    for (int j = 0; j < 2 - i; j++) {
      if (sorted[j] > sorted[j + 1]) {
        int temp = sorted[j];
        sorted[j] = sorted[j + 1];
        sorted[j + 1] = temp;
      }
    }
  }

  return sorted[1]; // Return median
}

// Update state machine
void updateState(int distance, unsigned long now) {
  bool objectNear = distance < DETECT_CM;

  switch (currentState) {
    case STATE_IDLE:
      if (objectNear) {
        currentState = STATE_DETECTING;
        stateEntryTime = now;
      }
      break;

    case STATE_DETECTING:
      if (!objectNear) {
        // Object moved away before confirmation
        currentState = STATE_IDLE;
      } else if (now - stateEntryTime >= ARRIVAL_HOLD_MS) {
        // Object stayed long enough - car arrived
        currentState = STATE_CAR_PRESENT;
        Serial.println("CAR_ARRIVED");
      }
      break;

    case STATE_CAR_PRESENT:
      if (!objectNear) {
        currentState = STATE_DEPARTING;
        stateEntryTime = now;
      }
      break;

    case STATE_DEPARTING:
      if (objectNear) {
        // Object returned - cancel departure
        currentState = STATE_CAR_PRESENT;
      } else if (now - stateEntryTime >= DEPARTURE_HOLD_MS) {
        // Object gone long enough - car left
        currentState = STATE_IDLE;
        Serial.println("CAR_LEFT");
      }
      break;
  }
}

void loop() {
  unsigned long now = millis();

  // Measure at regular intervals
  if (now - lastMeasureTime >= MEASURE_INTERVAL_MS) {
    lastMeasureTime = now;

    // Take a measurement and add to buffer
    int rawDistance = measureDistance();
    distanceBuffer[bufferIndex] = rawDistance;
    bufferIndex = (bufferIndex + 1) % 3;

    // Get filtered distance
    lastFilteredDistance = getMedianDistance();

    // Update state machine
    updateState(lastFilteredDistance, now);
  }

  // Send heartbeat
  if (now - lastHeartbeatTime >= HEARTBEAT_INTERVAL_MS) {
    lastHeartbeatTime = now;
    Serial.print("HB ");
    Serial.println(lastFilteredDistance);
  }
}
