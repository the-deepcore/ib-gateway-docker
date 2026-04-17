"""
PostgreSQL database configuration.
"""
import os

PGHOST = os.getenv("POSTGRES_HOST")
PGPORT = int(os.getenv("POSTGRES_PORT")
PGDATABASE = os.getenv("POSTGRES_DATABASE")
PGUSER = os.getenv("POSTGRES_USER")
PGPASSWORD = os.getenv("POSTGRES_PASSWORD")
