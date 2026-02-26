/**
 * Durham Weather Dashboard - Main Application
 * Handles authentication, navigation, data display, and charts
 */

import AuthService, { IS_MOCK, DEMO_CREDENTIALS } from "./appwrite.js";
import DataService from "./data-service.js";

// ===== STATE MANAGEMENT =====
const state = {
  user: null,
  preferences: {
    tempUnit: "celsius",
    pressureUnit: "hpa",
    refreshInterval: 300,
    darkMode: false,
    outdoorSensorId: "",
    indoorSensorId: "",
  },
  charts: {},
  refreshTimer: null,
};

// ===== DOM ELEMENTS =====
const elements = {
  // Auth elements
  authModal: document.getElementById("auth-modal"),
  loginForm: document.getElementById("login-form"),
  registerForm: document.getElementById("register-form"),
  authError: document.getElementById("auth-error"),
  showRegister: document.getElementById("show-register"),
  showLogin: document.getElementById("show-login"),

  // Dashboard elements
  dashboard: document.getElementById("dashboard"),
  sidebarToggle: document.getElementById("sidebar-toggle"),
  sidebar: document.querySelector(".sidebar"),
  navItems: document.querySelectorAll(".nav-item"),
  sections: document.querySelectorAll(".dashboard-section"),
  sectionTitle: document.getElementById("section-title"),

  // User elements
  userName: document.getElementById("user-name"),
  userEmail: document.getElementById("user-email"),
  logoutBtn: document.getElementById("logout-btn"),

  // Header elements
  currentDate: document.getElementById("current-date"),
  currentTime: document.getElementById("current-time"),
  refreshBtn: document.getElementById("refresh-btn"),

  // Toast container
  toastContainer: document.getElementById("toast-container"),
  loadingOverlay: document.getElementById("loading-overlay"),
};

// ===== INITIALIZATION =====
document.addEventListener("DOMContentLoaded", async () => {
  console.log("Durham Weather Dashboard initializing...");

  // Show mock auth indicator if enabled
  const authModeEl = document.getElementById("auth-mode");
  if (authModeEl) {
    if (typeof IS_MOCK !== "undefined" && IS_MOCK) {
      authModeEl.textContent =
        "Mock login enabled — local demo (any email/password)";
      authModeEl.style.color = "#f59e0b";
    } else {
      authModeEl.textContent = "";
    }
  }

  // Show "Use Demo" button when mock auth is enabled
  const useDemoBtn = document.getElementById("use-demo");
  if (useDemoBtn) {
    useDemoBtn.hidden = !(typeof IS_MOCK !== "undefined" && IS_MOCK);
    useDemoBtn.addEventListener("click", async (e) => {
      e.preventDefault();
      showLoading(true);
      try {
        let result;
        // Prefer explicit demoLogin if available
        if (typeof AuthService.demoLogin === "function") {
          result = await AuthService.demoLogin();
        } else {
          // Fallback to using demo credentials
          result = await AuthService.login(
            DEMO_CREDENTIALS.email,
            DEMO_CREDENTIALS.password
          );
        }

        if (result.success) {
          // Ensure current user and preferences are picked up
          const current = await AuthService.getCurrentUser();
          if (current.success) {
            state.user = current.user;
            await loadUserPreferences();
            showDashboard();
            showToast("Signed in as demo user", "success");
          } else {
            showToast(
              "Demo login succeeded but could not retrieve user",
              "warning"
            );
          }
        } else {
          showToast("Demo sign-in failed", "error");
        }
      } catch (err) {
        console.error("Demo login error:", err);
        showToast("Demo sign-in error", "error");
      } finally {
        showLoading(false);
      }
    });
  }

  // Setup event listeners
  setupAuthListeners();
  setupNavigationListeners();
  setupSettingsListeners();

  // Start date/time updates
  updateDateTime();
  setInterval(updateDateTime, 1000);

  // Check authentication status
  await checkAuth();
});

// ===== AUTHENTICATION =====
async function checkAuth() {
  showLoading(true);

  try {
    const isLoggedIn = await AuthService.isLoggedIn();

    if (isLoggedIn) {
      const { user } = await AuthService.getCurrentUser();
      state.user = user;

      // Load user preferences
      await loadUserPreferences();

      // Show dashboard
      showDashboard();
    } else {
      // Show auth modal
      showAuthModal();
    }
  } catch (error) {
    console.error("Auth check failed:", error);
    showAuthModal();
  } finally {
    showLoading(false);
  }
}

function setupAuthListeners() {
  // Toggle between login and register forms
  elements.showRegister?.addEventListener("click", (e) => {
    e.preventDefault();
    elements.loginForm.classList.remove("active");
    elements.registerForm.classList.add("active");
    clearAuthError();
  });

  elements.showLogin?.addEventListener("click", (e) => {
    e.preventDefault();
    elements.registerForm.classList.remove("active");
    elements.loginForm.classList.add("active");
    clearAuthError();
  });

  // Login form submission
  elements.loginForm?.addEventListener("submit", async (e) => {
    e.preventDefault();

    const email = document.getElementById("login-email").value;
    const password = document.getElementById("login-password").value;

    showLoading(true);

    const result = await AuthService.login(email, password);

    if (result.success) {
      const { user } = await AuthService.getCurrentUser();
      state.user = user;
      await loadUserPreferences();
      showDashboard();
      showToast("Welcome back!", "success");
    } else {
      showAuthError(
        result.error || "Login failed. Please check your credentials."
      );
    }

    showLoading(false);
  });

  // Register form submission
  elements.registerForm?.addEventListener("submit", async (e) => {
    e.preventDefault();

    const name = document.getElementById("register-name").value;
    const email = document.getElementById("register-email").value;
    const password = document.getElementById("register-password").value;
    const confirm = document.getElementById("register-confirm").value;

    if (password !== confirm) {
      showAuthError("Passwords do not match.");
      return;
    }

    if (password.length < 8) {
      showAuthError("Password must be at least 8 characters.");
      return;
    }

    showLoading(true);

    const result = await AuthService.register(email, password, name);

    if (result.success) {
      const { user } = await AuthService.getCurrentUser();
      state.user = user;
      showDashboard();
      showToast("Account created successfully!", "success");
    } else {
      showAuthError(result.error || "Registration failed. Please try again.");
    }

    showLoading(false);
  });

  // Logout button
  elements.logoutBtn?.addEventListener("click", async () => {
    showLoading(true);

    await AuthService.logout();
    state.user = null;

    // Stop data refresh
    if (state.refreshTimer) {
      clearInterval(state.refreshTimer);
    }

    showAuthModal();
    showToast("Logged out successfully", "success");
    showLoading(false);
  });
}

function showAuthModal() {
  elements.authModal.classList.remove("hidden");
  elements.dashboard.classList.add("hidden");
  elements.loginForm.classList.add("active");
  elements.registerForm.classList.remove("active");
  clearAuthError();
}

function showDashboard() {
  elements.authModal.classList.add("hidden");
  elements.dashboard.classList.remove("hidden");

  // Update user info display
  if (state.user) {
    elements.userName.textContent = state.user.name || "User";
    elements.userEmail.textContent = state.user.email;

    // Update settings
    document.getElementById("account-name").value = state.user.name || "";
    document.getElementById("account-email").value = state.user.email;
  }

  // Apply dark mode if enabled
  if (state.preferences.darkMode) {
    document.body.classList.add("dark-mode");
    document.getElementById("dark-mode-toggle").checked = true;
  }

  // Initialize charts
  initializeCharts();

  // Load initial data
  refreshData();

  // Setup auto-refresh
  setupAutoRefresh();
}

function showAuthError(message) {
  elements.authError.textContent = message;
  elements.authError.classList.add("show");
}

function clearAuthError() {
  elements.authError.textContent = "";
  elements.authError.classList.remove("show");
}

// ===== NAVIGATION =====
function setupNavigationListeners() {
  // Sidebar toggle for mobile
  elements.sidebarToggle?.addEventListener("click", () => {
    elements.sidebar.classList.toggle("open");
  });

  // Navigation items
  elements.navItems.forEach((item) => {
    item.addEventListener("click", (e) => {
      e.preventDefault();

      const section = item.dataset.section;
      navigateToSection(section);

      // Close sidebar on mobile
      if (window.innerWidth <= 992) {
        elements.sidebar.classList.remove("open");
      }
    });
  });

  // Refresh button
  elements.refreshBtn?.addEventListener("click", () => {
    refreshData();
    showToast("Data refreshed", "success");
  });

  // Close sidebar when clicking outside on mobile
  document.addEventListener("click", (e) => {
    if (
      window.innerWidth <= 992 &&
      !elements.sidebar.contains(e.target) &&
      !elements.sidebarToggle.contains(e.target)
    ) {
      elements.sidebar.classList.remove("open");
    }
  });
}

function navigateToSection(sectionId) {
  // Update active nav item
  elements.navItems.forEach((item) => {
    item.classList.toggle("active", item.dataset.section === sectionId);
  });

  // Show active section
  elements.sections.forEach((section) => {
    section.classList.toggle("active", section.id === `${sectionId}-section`);
  });

  // Update title
  const titles = {
    overview: "Dashboard Overview",
    outdoor: "Outdoor Sensor",
    indoor: "Indoor Sensor",
    history: "Historical Data",
    settings: "Settings",
  };
  elements.sectionTitle.textContent = titles[sectionId] || "Dashboard";

  // Refresh section-specific data
  if (sectionId === "history") {
    initializeHistorySection();
  }
}

// ===== USER PREFERENCES =====
async function loadUserPreferences() {
  try {
    const result = await AuthService.getPreferences();

    if (result.success && result.prefs) {
      state.preferences = { ...state.preferences, ...result.prefs };
    }
  } catch (error) {
    console.error("Failed to load preferences:", error);
  }

  // Apply preferences to UI
  applyPreferences();
}

function applyPreferences() {
  const prefs = state.preferences;

  // Dark mode
  if (prefs.darkMode) {
    document.body.classList.add("dark-mode");
  }

  // Settings form values
  document.getElementById("temp-unit").value = prefs.tempUnit || "celsius";
  document.getElementById("pressure-unit").value = prefs.pressureUnit || "hpa";
  document.getElementById("refresh-interval").value =
    prefs.refreshInterval || 300;
  document.getElementById("dark-mode-toggle").checked = prefs.darkMode || false;
  document.getElementById("outdoor-sensor-select").value =
    prefs.outdoorSensorId || "";
  document.getElementById("indoor-sensor-select").value =
    prefs.indoorSensorId || "";
}

function setupSettingsListeners() {
  // Save preferences
  document
    .getElementById("save-preferences")
    ?.addEventListener("click", async () => {
      const prefs = {
        tempUnit: document.getElementById("temp-unit").value,
        pressureUnit: document.getElementById("pressure-unit").value,
        refreshInterval: parseInt(
          document.getElementById("refresh-interval").value
        ),
        darkMode: document.getElementById("dark-mode-toggle").checked,
      };

      state.preferences = { ...state.preferences, ...prefs };

      // Apply dark mode immediately
      document.body.classList.toggle("dark-mode", prefs.darkMode);

      // Update auto-refresh
      setupAutoRefresh();

      // Save to Appwrite
      await AuthService.updatePreferences(state.preferences);

      showToast("Preferences saved", "success");
    });

  // Save sensor configuration
  document
    .getElementById("save-sensors")
    ?.addEventListener("click", async () => {
      const outdoorId = document.getElementById("outdoor-sensor-select").value;
      const indoorId = document.getElementById("indoor-sensor-select").value;

      state.preferences.outdoorSensorId = outdoorId;
      state.preferences.indoorSensorId = indoorId;

      await AuthService.updatePreferences(state.preferences);

      refreshData();
      showToast("Sensor configuration saved", "success");
    });

  // Dark mode toggle
  document
    .getElementById("dark-mode-toggle")
    ?.addEventListener("change", (e) => {
      document.body.classList.toggle("dark-mode", e.target.checked);
    });

  // Chart period selector
  document.getElementById("chart-period")?.addEventListener("change", (e) => {
    updateChartsForPeriod(e.target.value);
  });
}

// ===== DATA UPDATES =====
function refreshData() {
  updateOutdoorData();
  updateIndoorData();
  updateCharts();
}

function setupAutoRefresh() {
  // Clear existing timer
  if (state.refreshTimer) {
    clearInterval(state.refreshTimer);
  }

  const interval = state.preferences.refreshInterval * 1000;

  if (interval > 0) {
    state.refreshTimer = setInterval(refreshData, interval);
  }
}

function updateOutdoorData() {
  const data = DataService.getOutdoorData();

  // Quick stats
  document.getElementById("outdoor-temp").textContent = formatTemperature(
    data.temperature
  );
  document.getElementById("outdoor-humidity").textContent = `${data.humidity}%`;

  // Overview detail cards
  document.getElementById("outdoor-temp-detail").textContent =
    formatTemperature(data.temperature);
  document.getElementById(
    "outdoor-humidity-detail"
  ).textContent = `${data.humidity}%`;
  document.getElementById(
    "outdoor-wind"
  ).textContent = `${data.windSpeed} km/h`;
  document.getElementById(
    "outdoor-precip"
  ).textContent = `${data.precipitation} mm`;

  // Outdoor section details
  document.getElementById("outdoor-sensor-id").textContent = data.sensorId;
  document.getElementById("outdoor-location").textContent = data.location;
  document.getElementById("outdoor-last-update").textContent = data.lastUpdate;

  document.getElementById(
    "outdoor-temp-full"
  ).textContent = `${formatTemperature(data.temperature)}`;
  document.getElementById("outdoor-temp-high").textContent = formatTemperature(
    data.temperatureHigh,
    false
  );
  document.getElementById("outdoor-temp-low").textContent = formatTemperature(
    data.temperatureLow,
    false
  );

  document.getElementById(
    "outdoor-humidity-full"
  ).textContent = `${data.humidity} %`;
  document.getElementById("outdoor-hum-high").textContent = data.humidityHigh;
  document.getElementById("outdoor-hum-low").textContent = data.humidityLow;

  document.getElementById(
    "outdoor-wind-full"
  ).textContent = `${data.windSpeed} km/h`;
  document.getElementById("outdoor-gust").textContent = data.windGust;

  document.getElementById(
    "outdoor-precip-full"
  ).textContent = `${data.precipitation} mm`;
  document.getElementById("outdoor-precip-rate").textContent =
    data.precipitationRate;

  document.getElementById("outdoor-pressure-full").textContent = formatPressure(
    data.pressure
  );
  document.getElementById("outdoor-pressure-trend").textContent =
    data.pressureTrend;

  document.getElementById("outdoor-uv").textContent = data.uvIndex;
  document.getElementById("outdoor-uv-level").textContent = data.uvLevel;

  document.getElementById(
    "outdoor-solar"
  ).textContent = `${data.solarRadiation} W/m²`;
  document.getElementById("outdoor-dewpoint").textContent = formatTemperature(
    data.dewPoint
  );

  // Status badge
  const statusBadge = document.getElementById("outdoor-status");
  statusBadge.className = `status-badge ${data.status}`;
  statusBadge.innerHTML = `<i class="fas fa-circle"></i> ${
    data.status.charAt(0).toUpperCase() + data.status.slice(1)
  }`;
}

function updateIndoorData() {
  const data = DataService.getIndoorData();

  // Quick stats
  document.getElementById("indoor-temp").textContent = formatTemperature(
    data.temperature
  );
  document.getElementById("air-quality").textContent = `${data.pm25} µg/m³`;

  const aqiBadge = document.getElementById("aqi-badge");
  aqiBadge.textContent = data.pm25Category;
  aqiBadge.className = `stat-badge ${data.pm25Class}`;

  // Overview detail cards
  document.getElementById("indoor-temp-detail").textContent = formatTemperature(
    data.temperature
  );
  document.getElementById("indoor-humidity").textContent = `${data.humidity}%`;
  document.getElementById("indoor-co2").textContent = `${data.co2} ppm`;
  document.getElementById(
    "indoor-pressure"
  ).textContent = `${data.pressure} inHg`;

  // Indoor section details
  document.getElementById("indoor-sensor-id").textContent = data.sensorId;
  document.getElementById("indoor-location").textContent = data.location;
  document.getElementById("indoor-last-update").textContent = data.lastUpdate;

  document.getElementById(
    "indoor-temp-full"
  ).textContent = `${formatTemperature(data.temperature)}`;
  document.getElementById(
    "indoor-humidity-full"
  ).textContent = `${data.humidity} %`;

  document.getElementById("indoor-pm25").textContent = `${data.pm25} µg/m³`;
  const pm25Badge = document.getElementById("indoor-pm25-badge");
  pm25Badge.textContent = data.pm25Category;
  pm25Badge.className = `metric-badge ${data.pm25Class}`;

  document.getElementById("indoor-pm10").textContent = `${data.pm10} µg/m³`;
  document.getElementById("indoor-pm1").textContent = `${data.pm1} µg/m³`;

  document.getElementById("indoor-co2-full").textContent = `${data.co2} ppm`;
  const co2Badge = document.getElementById("indoor-co2-badge");
  co2Badge.textContent = data.co2Category;
  co2Badge.className = `metric-badge ${data.co2Class}`;

  document.getElementById("indoor-voc").textContent = `${data.voc} mg/m³`;
  document.getElementById(
    "indoor-pressure-full"
  ).textContent = `${data.pressure} inHg`;
  document.getElementById("indoor-o3").textContent = `${data.o3} ppb`;
  document.getElementById("indoor-no2").textContent = `${data.no2} ppb`;
  document.getElementById("indoor-ch2o").textContent = `${data.ch2o} ppb`;
  document.getElementById("indoor-tpsize").textContent = `${data.tpsize} µm`;

  // Status badge
  const statusBadge = document.getElementById("indoor-status");
  statusBadge.className = `status-badge ${data.status}`;
  statusBadge.innerHTML = `<i class="fas fa-circle"></i> ${
    data.status.charAt(0).toUpperCase() + data.status.slice(1)
  }`;
}

// ===== CHARTS =====
function initializeCharts() {
  const chartOptions = {
    responsive: true,
    maintainAspectRatio: true,
    plugins: {
      legend: {
        display: true,
        position: "top",
        labels: {
          usePointStyle: true,
          padding: 15,
        },
      },
    },
    scales: {
      x: {
        grid: {
          display: false,
        },
      },
      y: {
        grid: {
          color: "rgba(0, 0, 0, 0.05)",
        },
      },
    },
    interaction: {
      intersect: false,
      mode: "index",
    },
  };

  // Temperature Comparison Chart
  const tempCtx = document
    .getElementById("temp-comparison-chart")
    ?.getContext("2d");
  if (tempCtx) {
    state.charts.tempComparison = new Chart(tempCtx, {
      type: "line",
      data: {
        labels: [],
        datasets: [
          {
            label: "Outdoor",
            data: [],
            borderColor: "#06b6d4",
            backgroundColor: "rgba(6, 182, 212, 0.1)",
            fill: true,
            tension: 0.4,
          },
          {
            label: "Indoor",
            data: [],
            borderColor: "#f59e0b",
            backgroundColor: "rgba(245, 158, 11, 0.1)",
            fill: true,
            tension: 0.4,
          },
        ],
      },
      options: chartOptions,
    });
  }

  // AQI Chart
  const aqiCtx = document.getElementById("aqi-chart")?.getContext("2d");
  if (aqiCtx) {
    state.charts.aqi = new Chart(aqiCtx, {
      type: "line",
      data: {
        labels: [],
        datasets: [
          {
            label: "PM2.5 (µg/m³)",
            data: [],
            borderColor: "#10b981",
            backgroundColor: "rgba(16, 185, 129, 0.1)",
            fill: true,
            tension: 0.4,
          },
        ],
      },
      options: {
        ...chartOptions,
        plugins: {
          ...chartOptions.plugins,
          annotation: {
            annotations: {
              line1: {
                type: "line",
                yMin: 12,
                yMax: 12,
                borderColor: "#f59e0b",
                borderWidth: 1,
                borderDash: [5, 5],
                label: {
                  content: "Good Limit",
                  enabled: true,
                },
              },
            },
          },
        },
      },
    });
  }

  // Humidity Chart
  const humidityCtx = document
    .getElementById("humidity-chart")
    ?.getContext("2d");
  if (humidityCtx) {
    state.charts.humidity = new Chart(humidityCtx, {
      type: "bar",
      data: {
        labels: [],
        datasets: [
          {
            label: "Outdoor",
            data: [],
            backgroundColor: "rgba(59, 130, 246, 0.7)",
            borderRadius: 4,
          },
          {
            label: "Indoor",
            data: [],
            backgroundColor: "rgba(168, 85, 247, 0.7)",
            borderRadius: 4,
          },
        ],
      },
      options: {
        ...chartOptions,
        scales: {
          ...chartOptions.scales,
          y: {
            ...chartOptions.scales.y,
            max: 100,
          },
        },
      },
    });
  }

  // Outdoor temperature chart
  const outdoorTempCtx = document
    .getElementById("outdoor-temp-chart")
    ?.getContext("2d");
  if (outdoorTempCtx) {
    state.charts.outdoorTemp = new Chart(outdoorTempCtx, {
      type: "line",
      data: {
        labels: [],
        datasets: [
          {
            label: "Temperature (°C)",
            data: [],
            borderColor: "#f59e0b",
            backgroundColor: "rgba(245, 158, 11, 0.1)",
            fill: true,
            tension: 0.4,
          },
        ],
      },
      options: chartOptions,
    });
  }

  // Outdoor wind/precip chart
  const windPrecipCtx = document
    .getElementById("outdoor-wind-precip-chart")
    ?.getContext("2d");
  if (windPrecipCtx) {
    state.charts.windPrecip = new Chart(windPrecipCtx, {
      type: "bar",
      data: {
        labels: [],
        datasets: [
          {
            label: "Wind Speed (km/h)",
            data: [],
            backgroundColor: "rgba(6, 182, 212, 0.7)",
            borderRadius: 4,
            yAxisID: "y",
          },
          {
            label: "Precipitation (mm)",
            data: [],
            backgroundColor: "rgba(99, 102, 241, 0.7)",
            borderRadius: 4,
            yAxisID: "y1",
          },
        ],
      },
      options: {
        ...chartOptions,
        scales: {
          x: { grid: { display: false } },
          y: {
            type: "linear",
            display: true,
            position: "left",
            title: { display: true, text: "Wind Speed (km/h)" },
          },
          y1: {
            type: "linear",
            display: true,
            position: "right",
            title: { display: true, text: "Precipitation (mm)" },
            grid: { drawOnChartArea: false },
          },
        },
      },
    });
  }

  // Indoor PM2.5 chart
  const pm25Ctx = document
    .getElementById("indoor-pm25-chart")
    ?.getContext("2d");
  if (pm25Ctx) {
    state.charts.indoorPm25 = new Chart(pm25Ctx, {
      type: "line",
      data: {
        labels: [],
        datasets: [
          {
            label: "PM2.5 (µg/m³)",
            data: [],
            borderColor: "#10b981",
            backgroundColor: "rgba(16, 185, 129, 0.1)",
            fill: true,
            tension: 0.4,
          },
        ],
      },
      options: chartOptions,
    });
  }

  // Indoor CO2 chart
  const co2Ctx = document.getElementById("indoor-co2-chart")?.getContext("2d");
  if (co2Ctx) {
    state.charts.indoorCo2 = new Chart(co2Ctx, {
      type: "line",
      data: {
        labels: [],
        datasets: [
          {
            label: "CO2 (ppm)",
            data: [],
            borderColor: "#84cc16",
            backgroundColor: "rgba(132, 204, 22, 0.1)",
            fill: true,
            tension: 0.4,
          },
        ],
      },
      options: chartOptions,
    });
  }
}

function updateCharts() {
  const outdoorHistory = DataService.getHistoricalData("outdoor", 24, 60);
  const indoorHistory = DataService.getHistoricalData("indoor", 24, 60);

  const labels = outdoorHistory.map((d) => d.label);

  // Temperature Comparison
  if (state.charts.tempComparison) {
    state.charts.tempComparison.data.labels = labels;
    state.charts.tempComparison.data.datasets[0].data = outdoorHistory.map(
      (d) => d.temperature
    );
    state.charts.tempComparison.data.datasets[1].data = indoorHistory.map(
      (d) => d.temperature
    );
    state.charts.tempComparison.update("none");
  }

  // AQI Chart
  if (state.charts.aqi) {
    state.charts.aqi.data.labels = labels;
    state.charts.aqi.data.datasets[0].data = indoorHistory.map((d) => d.pm25);
    state.charts.aqi.update("none");
  }

  // Humidity Chart
  if (state.charts.humidity) {
    const humidityLabels = labels.filter((_, i) => i % 4 === 0);
    state.charts.humidity.data.labels = humidityLabels;
    state.charts.humidity.data.datasets[0].data = outdoorHistory
      .filter((_, i) => i % 4 === 0)
      .map((d) => d.humidity);
    state.charts.humidity.data.datasets[1].data = indoorHistory
      .filter((_, i) => i % 4 === 0)
      .map((d) => d.humidity);
    state.charts.humidity.update("none");
  }

  // Outdoor Temperature
  if (state.charts.outdoorTemp) {
    state.charts.outdoorTemp.data.labels = labels;
    state.charts.outdoorTemp.data.datasets[0].data = outdoorHistory.map(
      (d) => d.temperature
    );
    state.charts.outdoorTemp.update("none");
  }

  // Wind & Precipitation
  if (state.charts.windPrecip) {
    const windLabels = labels.filter((_, i) => i % 4 === 0);
    state.charts.windPrecip.data.labels = windLabels;
    state.charts.windPrecip.data.datasets[0].data = outdoorHistory
      .filter((_, i) => i % 4 === 0)
      .map((d) => d.windSpeed);
    state.charts.windPrecip.data.datasets[1].data = outdoorHistory
      .filter((_, i) => i % 4 === 0)
      .map((d) => d.precipitation);
    state.charts.windPrecip.update("none");
  }

  // Indoor PM2.5
  if (state.charts.indoorPm25) {
    state.charts.indoorPm25.data.labels = labels;
    state.charts.indoorPm25.data.datasets[0].data = indoorHistory.map(
      (d) => d.pm25
    );
    state.charts.indoorPm25.update("none");
  }

  // Indoor CO2
  if (state.charts.indoorCo2) {
    state.charts.indoorCo2.data.labels = labels;
    state.charts.indoorCo2.data.datasets[0].data = indoorHistory.map(
      (d) => d.co2
    );
    state.charts.indoorCo2.update("none");
  }
}

function updateChartsForPeriod(period) {
  let hours, interval;

  switch (period) {
    case "7d":
      hours = 168;
      interval = 360; // 6 hours
      break;
    case "30d":
      hours = 720;
      interval = 1440; // 24 hours
      break;
    default:
      hours = 24;
      interval = 60;
  }

  const outdoorHistory = DataService.getHistoricalData(
    "outdoor",
    hours,
    interval
  );
  const indoorHistory = DataService.getHistoricalData(
    "indoor",
    hours,
    interval
  );

  const labels = outdoorHistory.map((d) => {
    const date = new Date(d.timestamp);
    if (period === "30d") {
      return date.toLocaleDateString([], { month: "short", day: "numeric" });
    } else if (period === "7d") {
      return date.toLocaleDateString([], { weekday: "short", hour: "2-digit" });
    }
    return d.label;
  });

  if (state.charts.tempComparison) {
    state.charts.tempComparison.data.labels = labels;
    state.charts.tempComparison.data.datasets[0].data = outdoorHistory.map(
      (d) => d.temperature
    );
    state.charts.tempComparison.data.datasets[1].data = indoorHistory.map(
      (d) => d.temperature
    );
    state.charts.tempComparison.update();
  }
}

// ===== HISTORY SECTION =====
function initializeHistorySection() {
  // Set default date range (last 7 days)
  const endDate = new Date();
  const startDate = new Date();
  startDate.setDate(startDate.getDate() - 7);

  document.getElementById("history-start-date").value = startDate
    .toISOString()
    .split("T")[0];
  document.getElementById("history-end-date").value = endDate
    .toISOString()
    .split("T")[0];

  loadHistoryData();

  // Event listeners
  document
    .getElementById("apply-date-range")
    ?.addEventListener("click", loadHistoryData);
  document.getElementById("export-csv")?.addEventListener("click", exportCSV);
  document
    .getElementById("history-metric")
    ?.addEventListener("change", updateHistoryChart);
}

function loadHistoryData() {
  const startDate = document.getElementById("history-start-date").value;
  const endDate = document.getElementById("history-end-date").value;

  if (!startDate || !endDate) {
    showToast("Please select a date range", "warning");
    return;
  }

  // Get historical data
  const tableData = DataService.getHistoryTableData(startDate, endDate, 50);

  // Update table
  const tbody = document.getElementById("history-table-body");
  tbody.innerHTML = tableData
    .map(
      (row) => `
        <tr>
            <td>${row.displayTime}</td>
            <td>${row.sensor}</td>
            <td>${formatTemperature(row.temperature)}</td>
            <td>${row.humidity}%</td>
            <td>${row.pm25 === "-" ? "-" : row.pm25 + " µg/m³"}</td>
            <td>${formatPressure(row.pressure)}</td>
        </tr>
    `
    )
    .join("");

  // Update history chart
  updateHistoryChart();
}

function updateHistoryChart() {
  const metric =
    document.getElementById("history-metric")?.value || "temperature";
  const showOutdoor = document.getElementById("show-outdoor")?.checked;
  const showIndoor = document.getElementById("show-indoor")?.checked;

  const hours = 168; // 7 days
  const interval = 120; // 2 hours

  const outdoorData = DataService.getHistoricalData("outdoor", hours, interval);
  const indoorData = DataService.getHistoricalData("indoor", hours, interval);

  const labels = outdoorData.map((d) => {
    const date = new Date(d.timestamp);
    return date.toLocaleDateString([], { weekday: "short", hour: "2-digit" });
  });

  const chartCtx = document.getElementById("history-chart")?.getContext("2d");
  if (!chartCtx) return;

  // Destroy existing chart if it exists
  if (state.charts.history) {
    state.charts.history.destroy();
  }

  const datasets = [];

  if (showOutdoor) {
    datasets.push({
      label: "Outdoor",
      data: outdoorData.map((d) => d[metric]),
      borderColor: "#06b6d4",
      backgroundColor: "rgba(6, 182, 212, 0.1)",
      fill: true,
      tension: 0.4,
    });
  }

  if (showIndoor) {
    datasets.push({
      label: "Indoor",
      data: indoorData.map((d) => d[metric]),
      borderColor: "#f59e0b",
      backgroundColor: "rgba(245, 158, 11, 0.1)",
      fill: true,
      tension: 0.4,
    });
  }

  state.charts.history = new Chart(chartCtx, {
    type: "line",
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      plugins: {
        legend: {
          display: true,
          position: "top",
        },
      },
      scales: {
        x: { grid: { display: false } },
        y: { grid: { color: "rgba(0, 0, 0, 0.05)" } },
      },
    },
  });
}

function exportCSV() {
  const startDate = document.getElementById("history-start-date").value;
  const endDate = document.getElementById("history-end-date").value;

  const data = DataService.getHistoryTableData(startDate, endDate, 100);

  const headers = [
    "Timestamp",
    "Sensor",
    "Temperature",
    "Humidity",
    "PM2.5",
    "Pressure",
  ];
  const rows = data.map((row) => [
    row.displayTime,
    row.sensor,
    row.temperature,
    row.humidity,
    row.pm25,
    row.pressure,
  ]);

  const csv = [headers.join(","), ...rows.map((row) => row.join(","))].join(
    "\n"
  );

  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `weather_data_${startDate}_${endDate}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);

  showToast("CSV exported successfully", "success");
}

// ===== UTILITY FUNCTIONS =====
function formatTemperature(value, includeUnit = true) {
  if (state.preferences.tempUnit === "fahrenheit") {
    const fahrenheit = (value * 9) / 5 + 32;
    return includeUnit ? `${fahrenheit.toFixed(1)}°F` : fahrenheit.toFixed(1);
  }
  return includeUnit ? `${value.toFixed(1)}°C` : value.toFixed(1);
}

function formatPressure(value) {
  switch (state.preferences.pressureUnit) {
    case "inhg":
      if (value > 100) {
        // Convert from hPa to inHg
        return `${(value * 0.02953).toFixed(2)} inHg`;
      }
      return `${value} inHg`;
    case "mbar":
      if (value < 100) {
        // Convert from inHg to mbar
        return `${(value * 33.8639).toFixed(1)} mbar`;
      }
      return `${value.toFixed(1)} mbar`;
    default:
      if (value < 100) {
        // Convert from inHg to hPa
        return `${(value * 33.8639).toFixed(1)} hPa`;
      }
      return `${value.toFixed(1)} hPa`;
  }
}

function updateDateTime() {
  const now = new Date();

  elements.currentDate.textContent = now.toLocaleDateString("en-US", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  });

  elements.currentTime.textContent = now.toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function showLoading(show) {
  elements.loadingOverlay.classList.toggle("hidden", !show);
}

function showToast(message, type = "info") {
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;

  const icons = {
    success: "fa-check-circle",
    error: "fa-exclamation-circle",
    warning: "fa-exclamation-triangle",
    info: "fa-info-circle",
  };

  toast.innerHTML = `
        <i class="fas ${icons[type]}"></i>
        <span class="toast-message">${message}</span>
        <button class="toast-close"><i class="fas fa-times"></i></button>
    `;

  elements.toastContainer.appendChild(toast);

  // Close button
  toast.querySelector(".toast-close").addEventListener("click", () => {
    toast.remove();
  });

  // Auto-remove after 4 seconds
  setTimeout(() => {
    toast.style.animation = "slideIn 0.3s ease reverse";
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// Make functions available globally for inline event handlers
window.refreshData = refreshData;
