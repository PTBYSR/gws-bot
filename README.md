# Selfbot Logger Deploy

A comprehensive Discord Selfbot Logger and WhatsApp Monitor. This project silently monitors specified Discord servers (using a user account/selfbot) for new member joins, logs them locally and to a database, and can send alerts via Discord DMs and WhatsApp messages. 

It consists of two main components:
1. **Python Discord Logger** (`main.py`): Monitors Discord using `discord.py-self`. Features missed join recovery via MongoDB and forwards alerts to the WhatsApp monitor.
2. **Node.js WhatsApp Monitor** (`whatsapp/monitor.js`): A WhatsApp client using Baileys that provides a REST API to send WhatsApp messages and logs WhatsApp activity to MongoDB.

## Features
- **Passive Logging**: Silently logs when users join specified servers.
- **Missed Join Recovery**: If the bot goes offline, it will scan for users who joined while it was down and log them (requires MongoDB).
- **Multi-channel Alerts**: Receive notifications via Discord DM and WhatsApp.
- **WhatsApp API**: Internal REST API to easily send WhatsApp messages.

## Prerequisites
- [Python 3.8+](https://www.python.org/downloads/)
- [Node.js 18+](https://nodejs.org/)
- [MongoDB Atlas](https://www.mongodb.com/atlas) (Optional, but highly recommended for missed join recovery and persistent WhatsApp sessions)

## Setup Instructions

### 1. Python Discord Setup
1. Open a terminal in the root directory.
2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` in the root directory:
   ```bash
   cp .env.example .env
   ```
4. Fill in the `.env` file:
   - `DISCORD_TOKEN`: Your Discord account token (Get it by inspecting Discord network requests for the `authorization` header).
   - `LOG_TARGET_USER_ID`: (Optional) Your user ID to receive DM alerts.
   - `TARGET_SERVERS`: (Optional) Comma-separated list of server IDs to monitor. Leave blank for all.
   - `MONGO_URI`: (Optional) Your MongoDB connection string.
   - `ALERT_WHATSAPP_NUMBER`: (Optional) Phone number to send WhatsApp alerts to (e.g., 2348012345678).

### 2. Node.js WhatsApp Setup
1. Navigate to the `whatsapp` directory:
   ```bash
   cd whatsapp
   ```
2. Install Node.js dependencies:
   ```bash
   npm install
   ```
3. The monitor uses the `.env` file from the parent directory for database configuration. It also accepts `BOT_PHONE_NUMBER`, `DB_NAME`, and `MONITOR_COLLECTION` if you wish to override defaults.

## How to Run

### Method 1: Using the start script (Recommended for Linux/macOS)
You can use the provided `start.sh` script to run both processes together.
```bash
bash start.sh
```

### Method 2: Running manually
You will need to open two separate terminal windows.

**Terminal 1: WhatsApp Monitor**
```bash
cd whatsapp
node monitor.js
```
*Note: On first run, it will provide a pairing code in the terminal. Go to your WhatsApp app -> Linked Devices -> Link a Device -> Link with phone number instead, and enter the code.*

**Terminal 2: Discord Logger**
```bash
# In the root directory
python main.py
```

## Logs and Data
- **Local Logs**: Simple text logs are saved in `logs/joins.log`.
- **Database**: 
  - `selfbot_logger.joins`: Stores detailed Discord join information.
  - `sneakerheads.monitored_messages`: Stores WhatsApp message logs.
  - WhatsApp session data is also saved in the database to keep you logged in across restarts.

## Disclaimer
**Automated user accounts (selfbots) are against Discord's Terms of Service.** Using this script may result in your account being banned. Use at your own risk.
