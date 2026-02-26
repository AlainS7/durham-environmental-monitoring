/**
 * Mock Data Service for Weather Dashboard
 * Generates realistic sensor data for demo purposes
 * Replace with actual BigQuery API calls in production
 */

// Sensor configurations
const SENSORS = {
  outdoor: {
    id: "WU-DURHAM-001",
    type: "WU",
    location: "Durham, NC - Research Triangle",
    latitude: 35.994,
    longitude: -78.8986,
  },
  indoor: {
    id: "TSI-LAB-001",
    type: "TSI",
    location: "Durham Environmental Lab - Room 204",
    latitude: 35.994,
    longitude: -78.8986,
  },
};

// Generate random value within range with optional decimal places
function randomInRange(min, max, decimals = 1) {
  const value = Math.random() * (max - min) + min;
  return Number(value.toFixed(decimals));
}

// Generate slightly varied value based on previous value
function varyValue(baseValue, variance, min, max, decimals = 1) {
  const change = (Math.random() - 0.5) * variance * 2;
  let newValue = baseValue + change;
  newValue = Math.max(min, Math.min(max, newValue));
  return Number(newValue.toFixed(decimals));
}

// Get AQI category based on PM2.5 value
function getAQICategory(pm25) {
  if (pm25 <= 12) return { label: "Good", class: "good" };
  if (pm25 <= 35.4) return { label: "Moderate", class: "moderate" };
  if (pm25 <= 55.4) return { label: "Unhealthy (Sensitive)", class: "warning" };
  if (pm25 <= 150.4) return { label: "Unhealthy", class: "unhealthy" };
  return { label: "Very Unhealthy", class: "unhealthy" };
}

// Get CO2 level category
function getCO2Category(co2) {
  if (co2 < 800) return { label: "Good", class: "good" };
  if (co2 < 1000) return { label: "Moderate", class: "moderate" };
  if (co2 < 1500) return { label: "Poor", class: "warning" };
  return { label: "Unhealthy", class: "unhealthy" };
}

// Get UV index category
function getUVCategory(uv) {
  if (uv < 3) return "Low";
  if (uv < 6) return "Moderate";
  if (uv < 8) return "High";
  if (uv < 11) return "Very High";
  return "Extreme";
}

// Current state for smooth transitions
let currentState = {
  outdoor: {
    temperature: 22,
    humidity: 55,
    windSpeed: 12,
    windGust: 18,
    precipitation: 0,
    precipRate: 0,
    pressure: 1015,
    uv: 4,
    solar: 450,
    dewPoint: 12,
  },
  indoor: {
    temperature: 23,
    humidity: 45,
    pm1: 5,
    pm25: 8,
    pm4: 12,
    pm10: 15,
    co2: 650,
    voc: 0.3,
    pressure: 29.92,
    o3: 15,
    no2: 10,
    so2: 3,
    ch2o: 5,
    tpsize: 0.8,
  },
};

/**
 * Get current outdoor sensor data
 */
export function getOutdoorData() {
  // Update values with slight variations for realism
  const state = currentState.outdoor;

  state.temperature = varyValue(state.temperature, 0.5, 10, 35);
  state.humidity = varyValue(state.humidity, 2, 30, 90);
  state.windSpeed = varyValue(state.windSpeed, 2, 0, 40);
  state.windGust = Math.max(
    state.windSpeed,
    varyValue(state.windGust, 3, state.windSpeed, 60)
  );
  state.precipitation = varyValue(state.precipitation, 0.5, 0, 5);
  state.precipRate =
    state.precipitation > 0 ? varyValue(state.precipRate, 1, 0, 20) : 0;
  state.pressure = varyValue(state.pressure, 1, 990, 1040);
  state.uv = varyValue(state.uv, 0.5, 0, 11);
  state.solar = varyValue(state.solar, 50, 0, 1000);
  state.dewPoint = varyValue(state.dewPoint, 0.5, 0, 25);

  return {
    sensorId: SENSORS.outdoor.id,
    location: SENSORS.outdoor.location,
    timestamp: new Date().toISOString(),
    lastUpdate: new Date().toLocaleTimeString(),
    status: "online",

    temperature: state.temperature,
    temperatureHigh: state.temperature + randomInRange(2, 5),
    temperatureLow: state.temperature - randomInRange(3, 6),

    humidity: Math.round(state.humidity),
    humidityHigh: Math.min(
      100,
      Math.round(state.humidity + randomInRange(5, 15))
    ),
    humidityLow: Math.max(0, Math.round(state.humidity - randomInRange(5, 15))),

    windSpeed: state.windSpeed,
    windGust: state.windGust,
    windDirection: Math.round(randomInRange(0, 360, 0)),

    precipitation: state.precipitation,
    precipitationRate: state.precipRate,

    pressure: state.pressure,
    pressureTrend: Math.random() > 0.5 ? "Rising" : "Falling",

    uvIndex: Math.round(state.uv),
    uvLevel: getUVCategory(state.uv),

    solarRadiation: Math.round(state.solar),

    dewPoint: state.dewPoint,

    heatIndex:
      state.temperature + (state.humidity > 60 ? randomInRange(1, 3) : 0),
    windChill:
      state.temperature - (state.windSpeed > 15 ? randomInRange(1, 4) : 0),
  };
}

/**
 * Get current indoor sensor data
 */
export function getIndoorData() {
  // Update values with slight variations for realism
  const state = currentState.indoor;

  state.temperature = varyValue(state.temperature, 0.3, 18, 28);
  state.humidity = varyValue(state.humidity, 1, 25, 70);
  state.pm1 = varyValue(state.pm1, 1, 1, 20);
  state.pm25 = varyValue(state.pm25, 2, 2, 50);
  state.pm4 = varyValue(state.pm4, 2, state.pm25 * 1.1, state.pm25 * 2);
  state.pm10 = varyValue(state.pm10, 3, state.pm4 * 1.1, state.pm4 * 2);
  state.co2 = varyValue(state.co2, 30, 400, 2000, 0);
  state.voc = varyValue(state.voc, 0.1, 0, 2, 2);
  state.pressure = varyValue(state.pressure, 0.05, 29.5, 30.5, 2);
  state.o3 = varyValue(state.o3, 3, 0, 70, 0);
  state.no2 = varyValue(state.no2, 2, 0, 50, 0);
  state.so2 = varyValue(state.so2, 1, 0, 20, 0);
  state.ch2o = varyValue(state.ch2o, 2, 0, 30, 0);
  state.tpsize = varyValue(state.tpsize, 0.1, 0.3, 2, 2);

  const pm25Category = getAQICategory(state.pm25);
  const co2Category = getCO2Category(state.co2);

  return {
    sensorId: SENSORS.indoor.id,
    location: SENSORS.indoor.location,
    timestamp: new Date().toISOString(),
    lastUpdate: new Date().toLocaleTimeString(),
    status: "online",

    temperature: state.temperature,
    humidity: Math.round(state.humidity),

    pm1: state.pm1,
    pm25: state.pm25,
    pm25AQI: Math.round(state.pm25 * 4.16), // Approximate AQI conversion
    pm25Category: pm25Category.label,
    pm25Class: pm25Category.class,
    pm4: state.pm4,
    pm10: state.pm10,
    pm10AQI: Math.round(state.pm10 * 2),

    co2: Math.round(state.co2),
    co2Category: co2Category.label,
    co2Class: co2Category.class,

    voc: state.voc,
    pressure: state.pressure,

    o3: Math.round(state.o3),
    no2: Math.round(state.no2),
    so2: Math.round(state.so2),
    ch2o: Math.round(state.ch2o),

    tpsize: state.tpsize,

    // Particle number concentrations
    ncpm05: Math.round(state.pm1 * 100),
    ncpm1: Math.round(state.pm1 * 50),
    ncpm25: Math.round(state.pm25 * 30),
    ncpm4: Math.round(state.pm4 * 20),
    ncpm10: Math.round(state.pm10 * 10),
  };
}

/**
 * Generate historical data for charts
 * @param {string} sensorType - 'outdoor' or 'indoor'
 * @param {number} hours - Number of hours of data to generate
 * @param {number} interval - Interval in minutes between data points
 */
export function getHistoricalData(sensorType, hours = 24, interval = 60) {
  const data = [];
  const now = new Date();
  const points = Math.floor((hours * 60) / interval);

  // Initialize base values
  let baseTemp = sensorType === "outdoor" ? 18 : 22;
  let baseHumidity = sensorType === "outdoor" ? 60 : 45;
  let basePm25 = 10;
  let baseCo2 = 600;

  for (let i = points; i >= 0; i--) {
    const timestamp = new Date(now.getTime() - i * interval * 60 * 1000);
    const hour = timestamp.getHours();

    // Simulate daily patterns
    const dayFactor = Math.sin(((hour - 6) * Math.PI) / 12); // Peak at noon
    const nightFactor = hour >= 22 || hour <= 6 ? 0.8 : 1;

    if (sensorType === "outdoor") {
      const temp = baseTemp + dayFactor * 6 + randomInRange(-1, 1);
      const humidity = baseHumidity - dayFactor * 10 + randomInRange(-3, 3);

      data.push({
        timestamp: timestamp.toISOString(),
        label: timestamp.toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
        }),
        temperature: Number(temp.toFixed(1)),
        humidity: Math.max(0, Math.min(100, Math.round(humidity))),
        windSpeed: randomInRange(5, 25),
        precipitation: Math.random() > 0.8 ? randomInRange(0, 5) : 0,
        pressure: randomInRange(1010, 1020),
      });

      baseTemp = varyValue(baseTemp, 0.3, 15, 25);
      baseHumidity = varyValue(baseHumidity, 1, 40, 80);
    } else {
      const temp = baseTemp + randomInRange(-0.5, 0.5);
      const humidity = baseHumidity + randomInRange(-2, 2);
      const pm25 = basePm25 * nightFactor + randomInRange(-2, 3);
      const co2 =
        baseCo2 + (hour >= 9 && hour <= 18 ? 200 : 0) + randomInRange(-50, 50);

      data.push({
        timestamp: timestamp.toISOString(),
        label: timestamp.toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
        }),
        temperature: Number(temp.toFixed(1)),
        humidity: Math.max(0, Math.min(100, Math.round(humidity))),
        pm25: Math.max(0, Number(pm25.toFixed(1))),
        co2: Math.max(400, Math.round(co2)),
        pressure: Number((29.92 + randomInRange(-0.1, 0.1)).toFixed(2)),
      });

      baseTemp = varyValue(baseTemp, 0.2, 20, 25);
      baseHumidity = varyValue(baseHumidity, 0.5, 40, 55);
      basePm25 = varyValue(basePm25, 1, 5, 20);
      baseCo2 = varyValue(baseCo2, 20, 500, 800, 0);
    }
  }

  return data;
}

/**
 * Get sensor configuration
 */
export function getSensorConfig() {
  return SENSORS;
}

/**
 * Generate table data for history section
 */
export function getHistoryTableData(startDate, endDate, limit = 50) {
  const data = [];
  const start = new Date(startDate);
  const end = new Date(endDate);
  const diff = end - start;
  const interval = diff / limit;

  for (let i = 0; i < limit; i++) {
    const timestamp = new Date(start.getTime() + i * interval);

    // Outdoor reading
    data.push({
      timestamp: timestamp.toISOString(),
      displayTime: timestamp.toLocaleString(),
      sensor: "Outdoor (WU)",
      temperature: randomInRange(15, 30),
      humidity: Math.round(randomInRange(40, 80)),
      pm25: "-",
      pressure: randomInRange(1010, 1020),
    });

    // Indoor reading
    data.push({
      timestamp: timestamp.toISOString(),
      displayTime: timestamp.toLocaleString(),
      sensor: "Indoor (TSI)",
      temperature: randomInRange(20, 25),
      humidity: Math.round(randomInRange(40, 55)),
      pm25: randomInRange(5, 25),
      pressure: randomInRange(29.8, 30.1, 2),
    });
  }

  return data.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
}

export default {
  getOutdoorData,
  getIndoorData,
  getHistoricalData,
  getSensorConfig,
  getHistoryTableData,
  getAQICategory,
  getCO2Category,
  getUVCategory,
};
