import os
import json
import logging
from dotenv import load_dotenv

# Load environment variables from .env file for local development
load_dotenv()

class Config:
    @property
    def wu_api_config(self):
        # Allow for dummy config in test/dev environments
        api_key = None
        if self.wu_api_key and isinstance(self.wu_api_key, dict):
            api_key = self.wu_api_key.get("test_api_key")
        elif os.getenv("DUMMY_WU_API_KEY"):
            api_key = os.getenv("DUMMY_WU_API_KEY")
        return {
            "base_url": "https://api.weather.com/v2/pws",
            "api_key": api_key
        }

    @property
    def tsi_api_config(self):
        # Allow for dummy config in test/dev environments
        client_id = None
        client_secret = None
        if self.tsi_creds and isinstance(self.tsi_creds, dict):
            client_id = self.tsi_creds.get("key")
            client_secret = self.tsi_creds.get("secret")
        elif os.getenv("DUMMY_TSI_CLIENT_ID") and os.getenv("DUMMY_TSI_CLIENT_SECRET"):
            client_id = os.getenv("DUMMY_TSI_CLIENT_ID")
            client_secret = os.getenv("DUMMY_TSI_CLIENT_SECRET")
        return {
            "base_url": "https://api-prd.tsilink.com/api/v3/external",
            "auth_url": "https://api-prd.tsilink.com/api/v3/external/oauth/client_credential/accesstoken",
            "client_id": client_id,
            "client_secret": client_secret
        }
    """
    A centralized configuration class for the application.
    Handles loading secrets and environment variables.
    """
    # temporary
    def _parse_env_var_value(self, env_var_name):
        value = os.getenv(env_var_name)
        if value is None:
            return None
        # Check if it's in KEY=VALUE format and extract VALUE
        if '=' in value and value.startswith(env_var_name + '='):
            return value.split('=', 1)[1].strip()
        return value.strip() # Just strip if not in KEY=VALUE format

    def __init__(self):
        self._db_creds = None
        self._tsi_creds = None
        self._wu_api_key = None
        self.secret_client = None  # Delay initialization

        # PROJECT_ID can arrive in several shapes in Cloud Run / GitHub OIDC contexts.
        # Accept (in priority order): PROJECT_ID, GOOGLE_CLOUD_PROJECT, GCP_PROJECT.
        self.project_id = (
            self._parse_env_var_value("PROJECT_ID")
            or self._parse_env_var_value("GOOGLE_CLOUD_PROJECT")
            or self._parse_env_var_value("GCP_PROJECT")
        )

        # Secret ID env vars sometimes get passed through as KEY=VALUE; _parse_env_var_value handles that.
        self.db_creds_secret_id = self._parse_env_var_value("DB_CREDS_SECRET_ID")
        self.tsi_creds_secret_id = self._parse_env_var_value("TSI_CREDS_SECRET_ID")
        self.wu_api_key_secret_id = self._parse_env_var_value("WU_API_KEY_SECRET_ID")

        # Emit a concise debug summary to help diagnose 403 / CONSUMER_INVALID issues showing 'project None'.
        logging.info(
            "Config init: project_id=%s db_secret=%s tsi_secret=%s wu_secret=%s",
            self.project_id,
            self.db_creds_secret_id,
            self.tsi_creds_secret_id,
            self.wu_api_key_secret_id,
        )
        # GCS configuration (no secrets required)
        self.gcs_bucket = self._parse_env_var_value("GCS_BUCKET")
        self.gcs_prefix = os.getenv("GCS_PREFIX", "sensor_readings")

        # Optional BigQuery defaults for helper script
        self.bq_project = self._parse_env_var_value("BQ_PROJECT")
        self.bq_dataset = self._parse_env_var_value("BQ_DATASET")
        self.bq_location = os.getenv("BQ_LOCATION", "US")

        self._validate_env_vars()

        # Define paths to sensor configuration files
        self.sensor_config_paths = {
            'production': os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'environments', 'production.json'),
            'test': os.path.join(os.path.dirname(__file__), '..', '..', 'test_data', 'test_sensors.json')
        }
    @property
    def db_creds(self):
        if self._db_creds is None:
            self._db_creds = self._get_json_secret(self.db_creds_secret_id)
        # Allow for dummy creds in test/dev environments
        if not self._db_creds and os.getenv("DUMMY_DB_USER"):
            return {
                "DB_USER": os.getenv("DUMMY_DB_USER"),
                "DB_PASSWORD": os.getenv("DUMMY_DB_PASSWORD", "dummy"),
                "DB_HOST": os.getenv("DUMMY_DB_HOST", "localhost"),
                "DB_PORT": os.getenv("DUMMY_DB_PORT", "5432"),
                "DB_NAME": os.getenv("DUMMY_DB_NAME", "testdb")
            }
        return self._db_creds

    @property
    def tsi_creds(self):
        if self._tsi_creds is None:
            self._tsi_creds = self._get_json_secret(self.tsi_creds_secret_id)
        # Allow for dummy creds in test/dev environments
        if not self._tsi_creds and os.getenv("DUMMY_TSI_CLIENT_ID"):
            return {
                "key": os.getenv("DUMMY_TSI_CLIENT_ID"),
                "secret": os.getenv("DUMMY_TSI_CLIENT_SECRET", "dummy")
            }
        return self._tsi_creds

    @property
    def wu_api_key(self):
        if self._wu_api_key is None:
            self._wu_api_key = self._get_json_secret(self.wu_api_key_secret_id)
        # Allow for dummy key in test/dev environments
        if not self._wu_api_key and os.getenv("DUMMY_WU_API_KEY"):
            return {"test_api_key": os.getenv("DUMMY_WU_API_KEY")}
        return self._wu_api_key

    @property
    def database_url(self):
        creds = self.db_creds
        if not creds:
            return None
        try:
            return (
                f"postgresql://{creds['DB_USER']}:{creds['DB_PASSWORD']}"
                f"@{creds['DB_HOST']}:{creds['DB_PORT']}"
                f"/{creds['DB_NAME']}"
            )
        except Exception:
            return None

    def _validate_env_vars(self):
        """Ensure all required environment variables are set, unless dummy variables are present (for test/dev)."""
        # Map required name -> attribute actually holding it
        required_map = {
            "PROJECT_ID": "project_id",
            "DB_CREDS_SECRET_ID": "db_creds_secret_id",
            "TSI_CREDS_SECRET_ID": "tsi_creds_secret_id",
            "WU_API_KEY_SECRET_ID": "wu_api_key_secret_id",
        }
        missing_vars = [env_name for env_name, attr in required_map.items() if not getattr(self, attr)]
        # If all dummy variables are present, skip strict validation (for test/dev)
        dummy_vars = [
            os.getenv("DUMMY_DB_USER"),
            os.getenv("DUMMY_TSI_CLIENT_ID"),
            os.getenv("DUMMY_WU_API_KEY")
        ]
        if missing_vars:
            if all(dummy_vars):
                logging.warning(f"Missing required environment variables: {', '.join(missing_vars)}. Using dummy variables for test/dev.")
                return
            logging.critical(f"Missing required environment variables: {', '.join(missing_vars)}")
            # Do not exit here; allow tests to run with dummy vars
            # sys.exit(1)

    def _get_json_secret(self, secret_id):
        """Fetches and decodes a JSON secret from Google Secret Manager."""
        try:
            client = self.get_secret_client()
            if client is None:
                logging.critical("Secret Manager client could not be initialized (missing credentials?)")
                return None
            if not self.project_id:
                logging.critical("Cannot fetch secret '%s' because project_id is not set.", secret_id)
                return None
            if not secret_id:
                logging.critical("Attempted to fetch a secret but secret_id was empty or None.")
                return None
            name = f"projects/{self.project_id}/secrets/{secret_id.strip()}/versions/latest"
            response = client.access_secret_version(request={"name": name})
            payload = response.payload.data.decode("UTF-8")
            return json.loads(payload)
        except Exception as e:
            logging.critical(f"Fatal: Could not access or parse secret '{secret_id}'. Error: {e}")
            return None

    def _validate_secrets(self):
        """Validate the contents of the fetched secrets."""
        db_keys = ["DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT", "DB_NAME"]
        creds = self.db_creds
        tsi = self.tsi_creds
        if not creds or not all(key in creds for key in db_keys):
            logging.critical("Database credentials secret is missing one or more required keys.")
            return False
        if not tsi or "key" not in tsi or "secret" not in tsi:
            logging.critical("TSI credentials secret is missing 'key' or 'secret'.")
            return False
        return True

    def get_secret_client(self):
        if self.secret_client is None:
            from google.cloud import secretmanager
            try:
                self.secret_client = secretmanager.SecretManagerServiceClient()
            except Exception:
                # Optionally log or handle missing credentials
                self.secret_client = None
        return self.secret_client

    def _build_database_url(self):
        """Constructs the database connection string."""
        creds = self.db_creds
        if not creds:
            return None
        return (
            f"postgresql://{creds['DB_USER']}:{creds['DB_PASSWORD']}"
            f"@{creds['DB_HOST']}:{creds['DB_PORT']}"
            f"/{creds['DB_NAME']}"
        )

    @property
    def gcs_config(self):
        """Returns GCS upload configuration required by the uploader."""
        return {
            "bucket": self.gcs_bucket,
            "prefix": self.gcs_prefix,
        }

    @property
    def bigquery_defaults(self):
        return {
            "project": self.bq_project,
            "dataset": self.bq_dataset,
            "location": self.bq_location,
        }

# A single, global instance of the configuration
app_config = Config()
