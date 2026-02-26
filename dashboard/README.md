# Durham Weather Dashboard

A modern, responsive weather dashboard for monitoring indoor and outdoor environmental sensors with Appwrite authentication.

![Dashboard Preview](docs/dashboard-preview.png)

## Features

- **User Authentication**: Secure login/registration using Appwrite
- **Dual Sensor Support**: Monitor both indoor (TSI) and outdoor (Weather Underground) sensors
- **Real-time Data**: Auto-refreshing data displays with configurable intervals
- **Interactive Charts**: Beautiful visualizations powered by Chart.js
- **Air Quality Monitoring**: PM2.5, PM10, CO2, VOCs, and more
- **Weather Metrics**: Temperature, humidity, wind, precipitation, UV index
- **Historical Data**: View and export historical sensor data
- **Dark Mode**: Toggle between light and dark themes
- **Responsive Design**: Works on desktop, tablet, and mobile

## Sensor Data

### Outdoor Sensor (Weather Underground)

- Temperature (with high/low)
- Humidity
- Wind Speed & Gusts
- Precipitation
- Pressure
- UV Index
- Solar Radiation
- Dew Point

### Indoor Sensor (TSI)

- Temperature
- Humidity
- PM1.0, PM2.5, PM4.0, PM10
- CO2
- VOCs
- O3 (Ozone)
- NO2 (Nitrogen Dioxide)
- SO2 (Sulfur Dioxide)
- CH2O (Formaldehyde)
- Barometric Pressure

## Setup

### 1. Create an Appwrite Project

1. Sign up at [Appwrite Cloud](https://cloud.appwrite.io) or self-host Appwrite
2. Create a new project
3. Note your **Project ID** and **Endpoint**

### 2. Configure Appwrite

1. In your Appwrite Console, go to **Auth** > **Settings**
2. Add your dashboard's URL to the allowed platforms (e.g., `localhost`, `yourdomain.com`)
3. Enable **Email/Password** authentication

### 3. Update Configuration

Edit `dashboard/appwrite.js` and update the configuration:

```javascript
const APPWRITE_CONFIG = {
  endpoint: "https://cloud.appwrite.io/v1", // Your Appwrite endpoint
  projectId: "YOUR_PROJECT_ID", // Your Appwrite project ID
};
```

### 4. Serve the Dashboard

You can serve the dashboard using any static file server:

**Using Python:**

```bash
cd dashboard
python -m http.server 8080
```

**Using Node.js (serve):**

```bash
npx serve dashboard
```

**Using VS Code Live Server:**
Right-click on `index.html` and select "Open with Live Server"

### 5. Access the Dashboard

Open your browser and navigate to:

- `http://localhost:8080` (or your configured port)

### Mock Login (Quick demo)

If you haven't configured Appwrite yet, the dashboard automatically falls back to a local **mock login** so you can try the UI immediately. To use it:

- Click the **Use Demo Account** button on the login form (visible when mock mode is active) to sign in as a seeded demo user. Demo credentials: **demo@local.test / demo1234**.
- Or, open the login form and enter any **email** and **password** (or click Create Account to register). The mock auth accepts any credentials and stores the user and preferences in `localStorage`.
- Preferences (sensor IDs, units, dark mode) for the demo account are pre-seeded — see `dashboard/appwrite.js` if you want to change them.
- If you'd rather force mock mode, set `useMockAuth: true` in `dashboard/appwrite.js` under `APPWRITE_CONFIG`.

This is intended for local development/demo only — switch to a real Appwrite project to persist users and preferences across devices.

## Project Structure

```
dashboard/
├── index.html        # Main HTML file
├── styles.css        # All CSS styles (light/dark mode)
├── app.js            # Main application logic
├── appwrite.js       # Appwrite authentication service
├── data-service.js   # Mock data service (replace with real API)
└── README.md         # This file
```

## Customization

### Connecting to Real Data

The dashboard currently uses mock data from `data-service.js`. To connect to your actual BigQuery data:

1. Create a backend API that queries BigQuery
2. Update `data-service.js` to fetch from your API:

```javascript
export async function getOutdoorData() {
  const response = await fetch("/api/sensors/outdoor/current");
  return response.json();
}
```

### Adding Custom Metrics

To add new metrics:

1. Update the HTML in `index.html` with new metric cards
2. Add corresponding data fields in `data-service.js`
3. Update `app.js` to populate the new fields

### Theming

CSS variables in `styles.css` make it easy to customize colors:

```css
:root {
  --primary: #3b82f6;
  --success: #10b981;
  --warning: #f59e0b;
  --danger: #ef4444;
  /* ... more variables */
}
```

## API Integration

### Expected Data Format

**Outdoor Sensor:**

```json
{
  "sensorId": "WU-STATION-001",
  "timestamp": "2026-01-04T12:00:00Z",
  "temperature": 22.5,
  "humidity": 55,
  "windSpeed": 12.3,
  "precipitation": 0,
  "pressure": 1015.2,
  "uvIndex": 4
}
```

**Indoor Sensor:**

```json
{
  "sensorId": "TSI-001",
  "timestamp": "2026-01-04T12:00:00Z",
  "temperature": 23.1,
  "humidity": 45,
  "pm25": 8.5,
  "pm10": 15.2,
  "co2": 650,
  "voc": 0.3,
  "pressure": 29.92
}
```

## Browser Support

- Chrome (latest)
- Firefox (latest)
- Safari (latest)
- Edge (latest)

## Dependencies

- [Appwrite SDK](https://www.npmjs.com/package/appwrite) - Authentication
- [Chart.js](https://www.chartjs.org/) - Data visualization
- [Font Awesome](https://fontawesome.com/) - Icons
- [Inter Font](https://fonts.google.com/specimen/Inter) - Typography

## License

MIT License - See [LICENSE](../LICENSE) file for details.
