web: gunicorn --bind 0.0.0.0:$PORT --workers 2 --timeout 120 web_server:app
scraper: python scraper_worker.py --loop
telegram: python telegram_worker.py
processor: python processor_worker.py
mcp: python mcp_server.py streamable-http
