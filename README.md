# Telegram Job Scraper Bot

This project is a sophisticated Telegram bot that automates the process of scraping job postings from a specified Telegram group, parsing them using AI, and storing them in a structured database. It also offers features like syncing to Google Sheets, a web dashboard for monitoring, and interactive commands for managing the bot.

## Features

- **Telegram Group Monitoring**: Continuously monitors a specified Telegram group for new messages containing job postings.
- **AI-Powered Parsing**: Uses Large Language Models (LLMs) via OpenRouter to parse job details from messages, with a regex fallback mechanism.
- **Structured Database**: Stores raw messages and processed job data in a local SQLite database.
- **Google Sheets Sync**: Automatically syncs processed job data to a Google Sheet, separating jobs with and without email contacts.
- **Web Dashboard**: A Flask-based web interface to monitor the bot's status, view logs, and see the queue of unprocessed messages.
- **Interactive Bot Commands**:
    - `/start` & `/stop`: Start and stop the job processing.
    - `/status`: Get the current status of the bot.
    - `/process`: Manually trigger the processing of unprocessed messages.
    - `/stats`: View statistics about processed jobs.
    - `/export`: Export processed jobs to CSV files.
    - `/sync_sheets`: Manually sync the database with Google Sheets.
- **RESTful API**: The web dashboard is powered by a RESTful API that allows for programmatic interaction with the bot.
- **Deployment Ready**: Configured for deployment on Render with a `render.yaml` file.

## How It Works

The application consists of three main components:

1.  **Telegram Monitor (`monitor.py`)**: A `telethon` client that runs in the background, listening for new messages in the target Telegram group. When a new message arrives, it's saved to the `raw_messages` table in the database.
2.  **Telegram Bot (`main.py`)**: The main `python-telegram-bot` application that provides commands to interact with the system. It runs a scheduler (`APScheduler`) that periodically fetches unprocessed messages from the database, sends them to the `LLMProcessor` for parsing, and stores the structured data in the `processed_jobs` table.
3.  **Web Server (`web_server.py`)**: A `Flask` application that provides a web-based dashboard for monitoring and managing the bot. It uses a simple API to communicate with the database and send commands to the bot.

## Tech Stack

- **Python**: The core programming language.
- **Telethon**: For monitoring the Telegram group.
- **Python-Telegram-Bot**: For creating the interactive Telegram bot.
- **OpenRouter**: For AI-powered parsing of job postings.
- **SQLite**: As the local database for storing data.
- **Google Sheets API**: For syncing job data.
- **Flask**: For the web dashboard.
- **Gunicorn**: As the WSGI server for the Flask app.
- **Honcho**: To run multiple processes locally.
- **Render**: For deployment.

## Setup and Installation

1.  **Clone the repository**:
    ```bash
    git clone <repository-url>
    cd telegram-automate
    ```

2.  **Create a virtual environment and activate it**:
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
    ```

3.  **Install the dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

## Configuration

1.  **Copy the example environment file**:
    ```bash
    cp .env.example .env
    ```

2.  **Fill in the `.env` file with your credentials**:
    - `TELEGRAM_API_ID` & `TELEGRAM_API_HASH`: Your Telegram API credentials from my.telegram.org.
    - `TELEGRAM_PHONE`: Your phone number associated with your Telegram account.
    - `TELEGRAM_BOT_TOKEN`: The token for your Telegram bot from BotFather.
    - `TELEGRAM_GROUP_USERNAME`: The username or ID of the Telegram group to monitor.
    - `AUTHORIZED_USER_IDS`: A comma-separated list of user IDs who are authorized to use the bot's commands.
    - `ADMIN_USER_ID`: The user ID of the admin who will receive notifications and can control the bot via the web dashboard.
    - `OPENROUTER_API_KEY`: Your API key from OpenRouter.
    - `GOOGLE_CREDENTIALS_JSON`: The JSON content of your Google Cloud service account credentials.
    - `SPREADSHEET_ID`: The ID of the Google Sheet to sync data to.

## Usage

1.  **Run the application locally**:
    Honcho is used to run the multiple processes defined in the `Procfile`.
    ```bash
    honcho start
    ```
    This will start the web server, the bot, and the monitor.

2.  **Interact with the bot**:
    - Open Telegram and start a chat with your bot.
    - Use the `/start` command to begin monitoring and processing jobs.
    - Use the other commands to interact with the bot.

3.  **Access the web dashboard**:
    - Open your browser and go to `http://localhost:5000` (or the port specified in your `Procfile`).

## Deployment to Render

This project is configured for deployment on Render using the `render.yaml` file.

1.  **Create a new Blueprint instance on Render**.
2.  **Connect your GitHub repository**.
3.  **Render will automatically detect the `render.yaml` file and configure the services**.
4.  **Add your environment variables as secrets in the Render dashboard**.
    - Go to the "Environment" tab of your service.
    - Add each secret from your `.env` file as a secret file or environment variable. For `GOOGLE_CREDENTIALS_JSON`, it's recommended to add it as a secret file.
5.  **Deploy the application**.

The `render.yaml` file configures three services:
- `job-dashboard`: The web server.
- `telegram-job-bot`: The main bot application.
- `telegram-job-monitor`: The Telegram group monitor.

**Note**: The current `render.yaml` starts both `main.py` and `monitor.py` which can cause conflicts. It is recommended to refactor `main.py` to handle the monitoring process as a background task and remove the `telegram-job-monitor` service.

## Project Structure

```
.
├── .env.example
├── .gitignore
├── Procfile
├── README.md
├── bot.log
├── config.py
├── data/
├── database.py
├── llm_processor.py
├── main.py
├── monitor.log
├── monitor.py
├── render.yaml
├── requirements.txt
├── sheets_sync.py
├── templates
│   └── index.html
└── web_server.py
```
