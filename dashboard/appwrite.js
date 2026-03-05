/**
 * Appwrite Configuration & Services
 * Weather Dashboard Authentication Module
 */

import {
  Client,
  Account,
  ID,
} from "https://cdn.jsdelivr.net/npm/appwrite@16.0.0/+esm";

// Appwrite Configuration - Update these values with your Appwrite project settings
const APPWRITE_CONFIG = {
  endpoint: "https://cloud.appwrite.io/v1", // Your Appwrite endpoint
  projectId: "YOUR_PROJECT_ID", // Replace with your Appwrite project ID
  // set to true to always use local mock auth
  useMockAuth: false,
};

// Decide whether to use mock auth (no Appwrite configured) or real Appwrite
const USE_MOCK_AUTH =
  !APPWRITE_CONFIG.projectId ||
  APPWRITE_CONFIG.projectId === "YOUR_PROJECT_ID" ||
  APPWRITE_CONFIG.useMockAuth;

// Initialize Appwrite Client (still safe to import even if not used)
const client = new Client()
  .setEndpoint(APPWRITE_CONFIG.endpoint)
  .setProject(APPWRITE_CONFIG.projectId);

// Initialize Account service
const account = new Account(client);

// Demo credentials (used by the "Use demo" button)
const DEMO_CREDENTIALS = {
  email: "demo@local.test",
  password: "demo1234",
  name: "Demo User",
};

/**
 * Mock Authentication Service (localStorage based) - for demo access without Appwrite
 */
const MockAuthService = {
  _storageKey: "dashboard_mock_user",
  _prefsKeyPrefix: "dashboard_mock_prefs_",

  async register(email, password, name) {
    // accept any credentials for mock
    const user = {
      $id: `mock_${Date.now()}`,
      email,
      name: name || email.split("@")[0],
      createdAt: new Date().toISOString(),
    };
    localStorage.setItem(this._storageKey, JSON.stringify(user));
    // default prefs
    const prefs = {
      tempUnit: "celsius",
      pressureUnit: "hpa",
      refreshInterval: 300,
      darkMode: false,
      outdoorSensorId: "",
      indoorSensorId: "",
    };
    localStorage.setItem(this._prefsKey(user.email), JSON.stringify(prefs));
    return { success: true, user };
  },

  async login(email, password) {
    // in mock mode any email/password is accepted
    const stored = localStorage.getItem(this._storageKey);
    let user = stored ? JSON.parse(stored) : null;
    if (!user || user.email !== email) {
      // create a new mock user for this email
      user = {
        $id: `mock_${Date.now()}`,
        email,
        name: email.split("@")[0],
        createdAt: new Date().toISOString(),
      };
      localStorage.setItem(this._storageKey, JSON.stringify(user));
      // ensure prefs
      const prefs = {
        tempUnit: "celsius",
        pressureUnit: "hpa",
        refreshInterval: 300,
        darkMode: false,
        outdoorSensorId: "",
        indoorSensorId: "",
      };
      localStorage.setItem(this._prefsKey(user.email), JSON.stringify(prefs));
    }
    return { success: true, session: { user } };
  },

  /**
   * Create or ensure a demo user exists and log them in
   */
  async demoLogin() {
    const demo = DEMO_CREDENTIALS;
    const user = {
      $id: `mock_demo`,
      email: demo.email,
      name: demo.name,
      createdAt: new Date().toISOString(),
    };
    localStorage.setItem(this._storageKey, JSON.stringify(user));
    const prefs = {
      tempUnit: "celsius",
      pressureUnit: "hpa",
      refreshInterval: 300,
      darkMode: false,
      outdoorSensorId: "WU-DURHAM-001",
      indoorSensorId: "TSI-LAB-001",
    };
    localStorage.setItem(this._prefsKey(user.email), JSON.stringify(prefs));
    return { success: true, session: { user } };
  },

  async logout() {
    localStorage.removeItem(this._storageKey);
    return { success: true };
  },

  async getCurrentUser() {
    const stored = localStorage.getItem(this._storageKey);
    if (!stored) return { success: false, error: "No user" };
    const user = JSON.parse(stored);
    return { success: true, user };
  },

  async isLoggedIn() {
    const stored = localStorage.getItem(this._storageKey);
    return !!stored;
  },

  async updatePreferences(prefs) {
    const current = localStorage.getItem(this._storageKey);
    if (!current) return { success: false, error: "Not logged in" };
    const user = JSON.parse(current);
    const key = this._prefsKey(user.email);
    const existing = JSON.parse(localStorage.getItem(key) || "{}");
    const updated = { ...existing, ...prefs };
    localStorage.setItem(key, JSON.stringify(updated));
    return { success: true, prefs: updated };
  },

  async getPreferences() {
    const current = localStorage.getItem(this._storageKey);
    if (!current) return { success: false, error: "Not logged in" };
    const user = JSON.parse(current);
    const key = this._prefsKey(user.email);
    const prefs = JSON.parse(localStorage.getItem(key) || "{}");
    return { success: true, prefs };
  },

  async requestPasswordRecovery(email) {
    // No-op for mock
    return { success: true, result: { message: "Mock recovery email sent" } };
  },

  _prefsKey(email) {
    return `${this._prefsKeyPrefix}${email}`;
  },
};

/**
 * Appwrite Authentication Service wrapper
 * Uses Appwrite if configured, otherwise falls back to MockAuthService
 */
export const AuthService = USE_MOCK_AUTH
  ? MockAuthService
  : {
      async register(email, password, name) {
        try {
          const user = await account.create(ID.unique(), email, password, name);
          // Automatically log in after registration
          await this.login(email, password);
          return { success: true, user };
        } catch (error) {
          console.error("Registration error:", error);
          return { success: false, error: error.message };
        }
      },

      async login(email, password) {
        try {
          const session = await account.createEmailPasswordSession({
            email,
            password,
          });
          return { success: true, session };
        } catch (error) {
          console.error("Login error:", error);
          return { success: false, error: error.message };
        }
      },

      async logout() {
        try {
          await account.deleteSession("current");
          return { success: true };
        } catch (error) {
          console.error("Logout error:", error);
          return { success: false, error: error.message };
        }
      },

      async getCurrentUser() {
        try {
          const user = await account.get();
          return { success: true, user };
        } catch (error) {
          console.error("Get user error:", error);
          return { success: false, error: error.message };
        }
      },

      async isLoggedIn() {
        try {
          await account.get();
          return true;
        } catch {
          return false;
        }
      },

      async updatePreferences(prefs) {
        try {
          const result = await account.updatePrefs({ prefs });
          return { success: true, prefs: result };
        } catch (error) {
          console.error("Update preferences error:", error);
          return { success: false, error: error.message };
        }
      },

      async getPreferences() {
        try {
          const prefs = await account.getPrefs();
          return { success: true, prefs };
        } catch (error) {
          console.error("Get preferences error:", error);
          return { success: false, error: error.message };
        }
      },

      async requestPasswordRecovery(email) {
        try {
          const result = await account.createRecovery({
            email,
            url: `${window.location.origin}/dashboard/reset-password.html`,
          });
          return { success: true, result };
        } catch (error) {
          console.error("Password recovery error:", error);
          return { success: false, error: error.message };
        }
      },
    };

// Export for global access
export { client, account, ID, USE_MOCK_AUTH as IS_MOCK, DEMO_CREDENTIALS };
export default AuthService;
