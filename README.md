# MailDev Watcher

A Python service that monitors incoming emails from a MailDev instance and performs configurable actions on them.

## Overview

MailDev Watcher is a cron-based service designed to:
- Poll a MailDev email instance for new incoming emails
- Parse and extract information from emails
- Perform configurable workflows such as:
  - Parsing email content
  - Extracting structured data
  - Saving email data to MySQL database
  - Sending notifications

## Features

- 🔄 Cron-based polling of MailDev instance
- 📧 Email parsing and content extraction
- 💾 MySQL database integration for storing email data
- 🔔 Configurable notification system
- ⚙️ Flexible, extensible action framework

## Prerequisites

- Python 3.8 or higher
- MySQL server
- MailDev instance running

## Installation

1. Clone the repository:
```bash
git clone https://github.com/daileit/maildev-watcher.git
cd maildev-watcher
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Configure your settings:
```bash
cp .env.example .env
# Edit .env with your configuration
```

## Configuration

Configuration is typically managed through environment variables in a `.env` file:

```env
# MailDev Configuration
MAILDEV_HOST=localhost
MAILDEV_PORT=1025
MAILDEV_API_PORT=1080

# MySQL Configuration
MYSQL_HOST=localhost
MYSQL_USER=root
MYSQL_PASSWORD=password
MYSQL_DATABASE=maildev_watcher

# Cron Schedule (crontab format)
CRON_SCHEDULE=*/5 * * * *  # Every 5 minutes

# Notification Settings
NOTIFICATION_ENABLED=true
NOTIFICATION_TYPE=email  # or webhook, slack, etc.
NOTIFICATION_ENDPOINT=https://webhook.example.com
```

## Usage

Start the service:
```bash
python app.py
```

The service will:
1. Start a cron scheduler with the configured schedule
2. Poll MailDev instance for new emails
3. Process each email according to configured actions
4. Save results to MySQL and send notifications as configured

## Project Structure

```
maildev-watcher/
├── README.md
├── .gitignore
├── requirements.txt
├── .env.example
├── main.py
├── src/
│   ├── __init__.py
│   ├── config.py
│   ├── maildev_client.py
│   ├── email_processor.py
│   ├── database.py
│   └── notifications.py
└── tests/
    ├── __init__.py
    └── test_*.py
```

## API Reference

### Main Components

#### MailDevClient
Handles communication with MailDev instance.

#### EmailProcessor
Parses and extracts information from emails.

#### DatabaseManager
Manages MySQL connections and email storage.

#### NotificationService
Sends notifications based on processed emails.

## Development

Install development dependencies:
```bash
pip install -r requirements-dev.txt
```

Run tests:
```bash
pytest
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Commit your changes (`git commit -m 'Add some feature'`)
4. Push to the branch (`git push origin feature/your-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For issues, questions, or feature requests, please open an issue on the GitHub repository.

## Changelog

### [Unreleased]
- Initial project setup

