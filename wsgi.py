"""
WSGI Production Entry Point for Code Quality Analyzer.
Suitable for Gunicorn, uWSGI, Docker, and Cloud Platforms.
"""

import os
from app import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    host = os.environ.get("HOST", "0.0.0.0")
    app.run(host=host, port=port)
