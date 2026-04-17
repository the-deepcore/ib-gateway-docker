"""
IBKR api access configuration.
"""
import os

HOST = os.getenv("IBKR_HOST", "127.0.0.1")
PORT = int(os.getenv("IBKR_PORT", "4002"))
