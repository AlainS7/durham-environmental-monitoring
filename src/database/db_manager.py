"""
Database integration for Hot Durham project
"""
import pandas as pd
import json
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
import logging

log = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
class HotDurhamDB:
    """Database manager for PostgreSQL on Google Cloud SQL"""

    def __init__(self):
        """Initializes the database connection and schema."""
        self.engine = self._create_db_engine()
        self._init_database()

    def _create_db_engine(self) -> Engine:
        """Creates and returns a SQLAlchemy engine using the database_url from app_config (Google Secret Manager)."""
        from src.config.app_config import app_config
        db_url = app_config.database_url
        if not db_url:
            log.critical("Database URL is not available (secrets missing or malformed). Database features will be disabled.")
            raise RuntimeError("Database URL not available")
        return create_engine(db_url)

    def _init_database(self):
        """
        Initializes all required database tables if they don't already exist.
        This includes the main sensor data schema and logging tables.
        """
        with self.engine.connect() as connection:
            with connection.begin():
                # Main application schema
                connection.execute(text("""
                    CREATE TABLE IF NOT EXISTS sensors_master (
                        sensor_pk SERIAL PRIMARY KEY,
                        native_sensor_id VARCHAR(255) NOT NULL,
                        sensor_type VARCHAR(50) NOT NULL,
                        friendly_name VARCHAR(255),
                        CONSTRAINT uq_native_sensor_id_type UNIQUE (native_sensor_id, sensor_type)
                    );
                """))
                connection.execute(text("""
                    CREATE TABLE IF NOT EXISTS deployments (
                        deployment_pk SERIAL PRIMARY KEY,
                        sensor_fk INTEGER NOT NULL REFERENCES sensors_master(sensor_pk) ON DELETE CASCADE,
                        location VARCHAR(255) NOT NULL,
                        latitude DOUBLE PRECISION,
                        longitude DOUBLE PRECISION,
                        status VARCHAR(50) NOT NULL,
                        start_date DATE NOT NULL,
                        end_date DATE
                    );
                """))
                connection.execute(text("""
                    CREATE UNIQUE INDEX IF NOT EXISTS uq_one_active_deployment_per_sensor
                    ON deployments (sensor_fk, (COALESCE(end_date, '9999-12-31')));
                """))
                connection.execute(text("""
                    CREATE TABLE IF NOT EXISTS sensor_readings (
                        "timestamp" TIMESTAMPTZ NOT NULL,
                        deployment_fk INTEGER NOT NULL REFERENCES deployments(deployment_pk) ON DELETE CASCADE,
                        metric_name VARCHAR(100) NOT NULL,
                        value DOUBLE PRECISION,
                        PRIMARY KEY ("timestamp", deployment_fk, metric_name)
                    );
                """))
                connection.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_sensor_readings_deployment_timestamp 
                    ON sensor_readings(deployment_fk, "timestamp" DESC);
                """))

                # Logging and metadata tables
                connection.execute(text("""
                    CREATE TABLE IF NOT EXISTS collection_log (
                        log_id SERIAL PRIMARY KEY,
                        collection_date TIMESTAMPTZ DEFAULT NOW(),
                        source VARCHAR(50),
                        records_collected INTEGER,
                        errors_count INTEGER,
                        duration_seconds REAL
                    );
                """))
                connection.execute(text("""
                    CREATE TABLE IF NOT EXISTS collection_metadata (
                        metadata_id SERIAL PRIMARY KEY,
                        collection_time TIMESTAMPTZ DEFAULT NOW(),
                        collection_type VARCHAR(100),
                        metadata_json JSONB
                    );
                """))
    
    # --- NEW RECOMMENDED ---
    def insert_sensor_readings(self, df: pd.DataFrame):
        """
        Efficiently upserts a DataFrame of sensor data into the normalized sensor_readings table.
        Duplicate rows (same timestamp, deployment_fk, metric_name) are skipped (do nothing on conflict).
        The DataFrame is expected to have the following columns:
        - timestamp
        - deployment_fk
        - metric_name
        - value
        """
        if df.empty:
            log.info("No sensor readings to insert (DataFrame is empty).")
            return
        if not all(col in df.columns for col in ['timestamp', 'deployment_fk', 'metric_name', 'value']):
            raise ValueError("DataFrame must contain 'timestamp', 'deployment_fk', 'metric_name', and 'value' columns.")

        from sqlalchemy.dialects.postgresql import insert
        table_name = 'sensor_readings'
        from sqlalchemy import Table, MetaData
        meta = MetaData()
        table = Table(table_name, meta, autoload_with=self.engine)

        # Ensure all keys are str for SQLAlchemy insert
        log.debug("Converting DataFrame to list of dicts for upsert...")
        rows = df.to_dict(orient='records')
        total_rows = len(rows)
        log.info(f"Prepared {total_rows} rows for upsert into sensor_readings table.")
        if not rows:
            log.info("No rows to upsert after DataFrame conversion.")
            return
        chunk_size = 10000
        log.info(f"Using chunk size of {chunk_size} for batch upserts.")
        num_chunks = (total_rows + chunk_size - 1) // chunk_size
        inserted_total = 0
        with self.engine.begin() as conn:
            for i in range(num_chunks):
                chunk = rows[i*chunk_size:(i+1)*chunk_size]
                log.info(f"Upserting chunk {i+1}/{num_chunks} ({len(chunk)} rows)...")
                stmt = insert(table).values(chunk)
                stmt = stmt.on_conflict_do_nothing(index_elements=['timestamp', 'deployment_fk', 'metric_name'])
                result = conn.execute(stmt)
                inserted = getattr(result, 'rowcount', 0)
                inserted_total += inserted if isinstance(inserted, int) else 0
                log.info(f"Chunk {i+1}/{num_chunks} upserted. Rowcount reported: {inserted}")
        log.info(f"Batch upsert complete. Attempted to insert {total_rows} records into sensor_readings (duplicates skipped). Total inserted (rowcount sum): {inserted_total}")

    # --- LEGACY METHODS (To be deprecated) ---
    def insert_tsi_data(self, df: pd.DataFrame):
        """DEPRECATED: Insert TSI data into the old 'tsi_data' table."""
        log.warning("Using deprecated method 'insert_tsi_data'. Please migrate to 'insert_sensor_readings'.")
        # df.to_sql('tsi_data', self.engine, if_exists='append', index=False)
    
    def insert_wu_data(self, df: pd.DataFrame):
        """DEPRECATED: Insert WU data into the old 'wu_data' table."""
        log.warning("Using deprecated method 'insert_wu_data'. Please migrate to 'insert_sensor_readings'.")
        # df.to_sql('wu_data', self.engine, if_exists='append', index=False)
    
    def get_latest_readings(self, hours: int = 24) -> pd.DataFrame:
        """Gets the latest data from the sensor_readings table for all deployments."""
        query = text("""
            SELECT s.friendly_name, d.location, r.timestamp, r.metric_name, r.value
            FROM sensor_readings r
            JOIN deployments d ON r.deployment_fk = d.deployment_pk
            JOIN sensors_master s ON d.sensor_fk = s.sensor_pk
            WHERE r."timestamp" >= NOW() - INTERVAL :hours || ' hours'
            ORDER BY r."timestamp" DESC
        """)
        return pd.read_sql_query(query, self.engine, params={"hours": hours})
    
    def log_collection(self, source: str, records: int, errors: int, duration: float):
        """Logs a data collection event to the collection_log table."""
        query = text("""
            INSERT INTO collection_log 
            (source, records_collected, errors_count, duration_seconds)
            VALUES (:source, :records, :errors, :duration)
        """)
        with self.engine.connect() as connection:
            with connection.begin():
                connection.execute(query, {
                    "source": source, 
                    "records": records, 
                    "errors": errors, 
                    "duration": duration
                })
    
    def get_collection_stats(self, days: int = 7) -> pd.DataFrame:
        """Retrieves collection statistics for a given number of days."""
        query = text("""
            SELECT 
                DATE(collection_date) as collection_day,
                source,
                SUM(records_collected) as total_records,
                SUM(errors_count) as total_errors,
                AVG(duration_seconds) as avg_duration
            FROM collection_log 
            WHERE collection_date >= NOW() - INTERVAL :days || ' days'
            GROUP BY collection_day, source
            ORDER BY collection_day DESC, source
        """)
        return pd.read_sql_query(query, self.engine, params={"days": days})
    
    def store_collection_metadata(self, collection_type: str, metadata: dict):
        """Stores arbitrary collection metadata as a JSON object."""
        query = text("""
            INSERT INTO collection_metadata (collection_type, metadata_json)
            VALUES (:collection_type, :metadata_json)
        """)
        with self.engine.connect() as connection:
            with connection.begin():
                connection.execute(query, {
                    "collection_type": collection_type,
                    "metadata_json": json.dumps(metadata)
                })

