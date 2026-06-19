from flask import Flask
from threading import Thread
import os
import time
import requests

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive and running!"

def run():
    # Render assigns a port dynamically via the PORT environment variable.
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def ping_self():
    while True:
        time.sleep(600)  # Wait for 10 minutes (600 seconds)
        try:
            # Render automatically provides RENDER_EXTERNAL_URL
            url = os.environ.get('RENDER_EXTERNAL_URL')
            if url:
                requests.get(url)
                print(f"Auto-pinged {url} to stay awake!")
            else:
                # If RENDER_EXTERNAL_URL is not available, try localhost
                port = int(os.environ.get("PORT", 8080))
                requests.get(f"http://127.0.0.1:{port}/")
                print("Auto-pinged localhost to stay awake!")
        except Exception as e:
            print(f"Auto-ping failed: {e}")

def keep_alive():
    # Start the web server
    t = Thread(target=run)
    t.daemon = True
    t.start()
    
    # Start the auto-pinging thread
    ping_thread = Thread(target=ping_self)
    ping_thread.daemon = True
    ping_thread.start()
