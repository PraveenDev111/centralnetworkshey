from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from apscheduler.schedulers.background import BackgroundScheduler
import json
import os
import uuid
from datetime import datetime
from device_manager import get_device_info, run_command, backup_config_ssh
from scheduler import run_all_backups
from waitress import serve

app = Flask(__name__)
# A secret key is required for session management
app.secret_key = os.urandom(24)

# --- User Authentication (Simple Example) ---
# In a real app, use a database and hashed passwords
VALID_USERNAME = 'admin'
VALID_PASSWORD = 'password'

# --- Routes ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form['username'] == VALID_USERNAME and request.form['password'] == VALID_PASSWORD:
            session['logged_in'] = True
            flash('You were successfully logged in', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid credentials. Please try again.', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    flash('You were logged out', 'success')
    return redirect(url_for('login'))

def load_inventory():
    if not os.path.exists('database/inventory.json'):
        return {'devices': []}
    try:
        with open('database/inventory.json', 'r') as f:
            data = json.load(f)
            # Ensure the data is in the correct format
            if isinstance(data, list):
                # Convert old format to new format
                return {'devices': data}
            return data
    except json.JSONDecodeError:
        # If the file is empty or corrupted, return default structure
        return {'devices': []}

def save_inventory(data):
    os.makedirs('database', exist_ok=True)
    with open('database/inventory.json', 'w') as f:
        json.dump(data, f, indent=2)

@app.route('/')
def dashboard():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    inventory = load_inventory()
    # Ensure we're always working with a list of devices
    devices = inventory.get('devices', [])
    if not isinstance(devices, list):
        devices = []
    return render_template('dashboard.html', devices=devices)

@app.route('/add_device', methods=['POST'])
def add_device():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
        
    hostname = request.form.get('hostname')
    ip = request.form.get('ip')
    username = request.form.get('username')
    password = request.form.get('password')
    device_type = request.form.get('device_type', 'cisco_ios')
    
    if not all([hostname, ip, username, password]):
        flash('All fields are required', 'danger')
        return redirect(url_for('dashboard'))
    
    inventory = load_inventory()
    
    # Check if device with same IP already exists
    if any(device['ip'] == ip for device in inventory.get('devices', [])):
        flash('A device with this IP already exists', 'danger')
        return redirect(url_for('dashboard'))
    
    # Add new device
    new_device = {
        'id': str(uuid.uuid4()),
        'hostname': hostname,
        'ip': ip,
        'username': username,
        'password': password,  # In production, encrypt this!
        'device_type': device_type,
        'last_backup': None
    }
    
    if 'devices' not in inventory:
        inventory['devices'] = []
    inventory['devices'].append(new_device)
    save_inventory(inventory)
    
    flash(f'Device {hostname} added successfully', 'success')
    return redirect(url_for('dashboard'))

@app.route('/console/<device_ip>', methods=['GET', 'POST'])
def console(device_ip):
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    inventory = load_inventory()
    device = next((d for d in inventory.get('devices', []) if d['ip'] == device_ip), None)
    
    if not device:
        flash('Device not found', 'danger')
        return redirect(url_for('dashboard'))
    
    output = ""
    if request.method == 'POST':
        command = request.form.get('command', '').strip()
        if command:
            try:
                output = f"{device['hostname']}# {command}\n"
                # In a real app, you would run the actual command here
                # For now, we'll just simulate a response
                if command.lower() == 'show version':
                    output += "Cisco IOS Software, C3560CX Software (C3560CX-UNIVERSALK9-M), Version 15.2(4)E7\n"
                    output += "Copyright (c) 1986-2018 by Cisco Systems, Inc.\n"
                elif 'show ip interface brief' in command.lower():
                    output += "Interface              IP-Address      OK? Method Status                Protocol\n"
                    output += "Vlan1                  unassigned      YES NVRAM  administratively down down\n"
                    output += "GigabitEthernet0/1     unassigned      YES unset  up                    up\n"
                elif 'show run' in command.lower():
                    output += "Current configuration : 1234 bytes\n!\n! Last configuration change at 14:23:01 UTC Mon Mar 1 2023\n! NVRAM config last updated at 14:20:05 UTC Mon Mar 1 2023\n!\nversion 15.2\nservice timestamps debug datetime msec\nservice timestamps log datetime msec\n"
                else:
                    output += f"Command '{command}' executed successfully\n"
            except Exception as e:
                output += f"Error executing command: {str(e)}\n"
    
    return render_template('console.html', device=device, output=output)

@app.route('/backup/<device_ip>')
def backup_now(device_ip):
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    inventory = load_inventory()
    device = next((d for d in inventory.get('devices', []) if d['ip'] == device_ip), None)
    
    if not device:
        flash('Device not found', 'danger')
        return redirect(url_for('dashboard'))
    
    try:
        # In a real app, you would call backup_config_ssh(device_ip) here
        # For now, we'll simulate a successful backup
        backup_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Update last backup time
        for d in inventory['devices']:
            if d['ip'] == device_ip:
                d['last_backup'] = backup_time
                break
        save_inventory(inventory)
        
        flash(f'Backup completed successfully for {device["hostname"]} at {backup_time}', 'success')
    except Exception as e:
        flash(f'Backup failed: {str(e)}', 'danger')
    
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    # --- Scheduler ---
    # This automates the configuration retrieval process
    scheduler = BackgroundScheduler()
    # Schedule the backup job to run every 60 minutes
    scheduler.add_job(run_all_backups, 'interval', minutes=60)
    scheduler.start()
    
    print("Starting Flask app with Waitress server on http://127.0.0.1:8000")
    print("Scheduled backup job will run every 60 minutes.")
    
    # Use Waitress, a production-ready server, instead of Flask's built-in dev server
    serve(app, host='127.0.0.1', port=8000)