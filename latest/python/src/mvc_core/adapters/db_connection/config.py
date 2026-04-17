"""
PostgreSQL database configuration.
"""
import os

PGHOST = os.getenv("PGHOST", "deepcorepostresqlserver.postgres.database.azure.com")
PGPORT = int(os.getenv("PGPORT", "5432"))
PGDATABASE = os.getenv("PGDATABASE", "the_deep_co_9754_test_03022026")
PGUSER = os.getenv("PGUSER", "tradingdb_admin")
PGPASSWORD = os.getenv("PGPASSWORD", "Alpes1234!")


PGHOST = os.getenv("PGHOST", "127.0.0.1")
PGPORT = int(os.getenv("PGPORT", "5432"))
PGDATABASE = os.getenv("PGDATABASE", "thedeepcore_dev")
PGUSER = os.getenv("PGUSER", "postgres")
PGPASSWORD = os.getenv("PGPASSWORD", "postgres")