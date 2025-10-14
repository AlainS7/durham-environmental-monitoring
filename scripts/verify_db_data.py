#from sqlalchemy import create_engine
#import pandas as pd
#import os
#
#def verify_data():
#    """
#    Connects to the PostgreSQL database and prints the last 5 records from
#    the tsi_data and wu_data tables to verify data integrity.
#    """
#    try:
#        # Database connection parameters should be loaded from environment variables
#        db_name = os.getenv("DB_NAME", "postgres")
#        db_user = os.getenv("DB_USER", "postgres")
#        db_pass = os.getenv("DB_PASS")
#        db_host = os.getenv("DB_HOST", "127.0.0.1")
#        db_port = os.getenv("DB_PORT", "5432")
#
#        if not db_pass:
#            print("DB_PASS environment variable not set.")
#            print("Please set the database password and other connection variables in your environment.")
#            return
#
#        print(f"Connecting to database '{db_name}' at {db_host}:{db_port}...")
#        
#        conn_string = f"postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"
#        engine = create_engine(conn_string)
#
#        with engine.connect() as conn:
#            print("\n--- Verifying 'tsi_data' table ---")
#            try:
#                # Check if table exists
#                tsi_df = pd.read_sql("SELECT * FROM tsi_data ORDER BY reading_time DESC LIMIT 5", conn)
#                if not tsi_df.empty:
#                    print("Latest 5 records from tsi_data:")
#                    print(tsi_df.to_string())
#                else:
#                    print("No data found in 'tsi_data' table.")
#            except Exception as e:
#                print(f"Could not query 'tsi_data': {e}")
#
#            print("\n--- Verifying 'wu_data' table ---")
#            try:
#                wu_df = pd.read_sql("SELECT * FROM wu_data ORDER BY obsTimeUtc DESC LIMIT 5", conn)
#                if not wu_df.empty:
#                    print("Latest 5 records from wu_data:")
#                    print(wu_df.to_string())
#                else:
#                    print("No data found in 'wu_data' table.")
#            except Exception as e:
#                print(f"Could not query 'wu_data': {e}")
#
#    except Exception as e:
#        print(f"An error occurred: {e}")
#
#if __name__ == "__main__":
#    verify_data()