# Network Management System

A centralized network management system for monitoring and managing network devices.

## Features

- Device inventory management
- Web-based console access to devices
- Configuration backup functionality
- User authentication
- Responsive web interface

## Prerequisites

- Python 3.7+
- pip (Python package manager)

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/PraveenDev111/centralnetworkshey.git
   cd centralnetworkshey
   ```

2. Create and activate a virtual environment (recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install the required packages:
   ```bash
   pip install -r requirements.txt
   ```

## Configuration

1. Copy `.env.example` to `.env` and update the configuration:
   ```bash
   cp .env.example .env
   ```

2. Update the environment variables in `.env` as needed.

## Usage

1. Start the application:
   ```bash
   python app.py
   ```

2. Access the web interface at `http://localhost:8000`

3. Default login credentials:
   - Username: admin
   - Password: password

## Project Structure

```
Central_Management_System/
├── app.py                  # Main application
├── device_manager.py       # Device management logic
├── scheduler.py            # Background tasks
├── requirements.txt        # Python dependencies
├── .gitignore             # Git ignore file
├── README.md              # This file
├── database/              # Database files (not versioned)
└── templates/             # HTML templates
    ├── dashboard.html
    ├── login.html
    └── console.html
```

## License

This project is licensed under the MIT License.
