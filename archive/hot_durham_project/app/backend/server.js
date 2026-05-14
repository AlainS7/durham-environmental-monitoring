const express = require('express');
const fetch = require('node-fetch');
const { SecretManagerServiceClient } = require('@google-cloud/secret-manager');
const app = express();
const PORT = process.env.PORT || 3000;

// --- Google Secret Manager ---
const client = new SecretManagerServiceClient();
const PROJECT_ID = process.env.PROJECT_ID || '441117079833'; // Fallback for local dev

async function getSecret(secretId, version = 'latest') {
  try {
    const name = `projects/${PROJECT_ID}/secrets/${secretId}/versions/${version}`;
    const [response] = await client.accessSecretVersion({ name });
    const payload = response.payload.data.toString('utf8');
    return JSON.parse(payload);
  } catch (error) {
    console.error(`Error accessing secret ${secretId}:`, error);
    throw new Error(`Could not access secret: ${secretId}`);
  }
}

// Asynchronously fetch secrets at startup
let wu_key, tsi_creds;

async function initializeSecrets() {
  try {
    console.log('Initializing secrets...');
    const wuSecret = await getSecret('wu_api_key');
    wu_key = wuSecret.test_api_key;
    tsi_creds = await getSecret('tsi_creds');
    console.log('✅ Secrets initialized successfully.');
  } catch (error) {
    console.error('❌ FATAL: Could not initialize secrets. Exiting.', error);
    process.exit(1);
  }
}
// --- End Secret Manager ---

async function getTSIToken() {
  const resp = await fetch('https://api-prd.tsilink.com/api/v3/external/oauth/client_credential/accesstoken?grant_type=client_credentials', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: `client_id=${tsi_creds.key}&client_secret=${tsi_creds.secret}`
  });
  const data = await resp.json();
  return data.access_token;
}

app.use(express.static('../frontend'));

app.get('/api/wu/:stationId', async (req, res) => {
  const stationId = req.params.stationId;
  const url = `https://api.weather.com/v2/pws/observations/current?stationId=${stationId}&format=json&units=m&apiKey=${wu_key}`;
  
  try {
    const response = await fetch(url);
    const json = await response.json();
    const obs = json.observations[0];

    res.json({
      temp: obs.metric.temp,
      humidity: obs.humidity,
      wind: obs.metric.windSpeed
    });
  } catch (e) {
    res.status(500).json({ error: "Failed to fetch data" });
  }
});

app.get('/api/tsi/devices', async (req, res) => {
  try {
    const token = await getTSIToken();
    const resp = await fetch('https://api-prd.tsilink.com/api/v3/external/devices', {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    const devices = await resp.json();
    res.json(devices);
  } catch (e) {
    res.status(500).json({ error: 'Failed to fetch TSI devices' });
  }
});

app.get('/api/tsi/:deviceId', async (req, res) => {
  const deviceId = req.params.deviceId;
  try {
    const token = await getTSIToken();
    // Get last 24h data (or latest)
    const now = new Date();
    const start = new Date(now.getTime() - 24*60*60*1000).toISOString();
    const end = now.toISOString();
    const url = `https://api-prd.tsilink.com/api/v3/external/telemetry?start_date=${start}&end_date=${end}&device_id=${deviceId}`;
    const resp = await fetch(url, {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    const data = await resp.json();
    // Return the latest record if available
    if (Array.isArray(data) && data.length > 0) {
      res.json(data[data.length - 1]);
    } else {
      res.status(404).json({ error: 'No data found for device' });
    }
  } catch (e) {
    res.status(500).json({ error: 'Failed to fetch TSI data' });
  }
});

// Initialize secrets and then start the server
initializeSecrets().then(() => {
  app.listen(PORT, () => {
    console.log(`API proxy running at http://localhost:${PORT}`);
  });
});