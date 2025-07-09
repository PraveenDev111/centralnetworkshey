from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from apscheduler.schedulers.background import BackgroundScheduler
import json
import os
import uuid
import subprocess
import platform
from datetime import datetime
from functools import wraps
from device_manager import get_device_info, run_command, backup_config_ssh
from scheduler import run_all_backups
from port_scan import scan_port
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
    """Load the device inventory from JSON file."""
    if not os.path.exists('database/inventory.json'):
        os.makedirs('database', exist_ok=True)
        with open('database/inventory.json', 'w') as f:
            json.dump({'devices': []}, f)
        return {'devices': []}
    
    try:
        with open('database/inventory.json', 'r') as f:
            data = json.load(f)
            # Ensure the data is in the correct format
            if isinstance(data, list):
                # Convert old format to new format
                data = {'devices': data}
                save_inventory(data)  # Save in new format
            return data
    except (json.JSONDecodeError, FileNotFoundError):
        # If file is empty or corrupted, return default structure
        return {'devices': []}

def save_inventory(data):
    """Save the device inventory to JSON file."""
    os.makedirs('database', exist_ok=True)
    with open('database/inventory.json', 'w') as f:
        json.dump(data, f, indent=2)

@app.route('/')
def dashboard():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    # Load devices for dashboard
    inventory = load_inventory()
    devices = inventory.get('devices', [])
    if not isinstance(devices, list):
        devices = []
    
    # Prepare test network data
    test_targets = [
        {'name': 'GNS3 Local Server', 'host': 'localhost', 'ports': [80, 3080, 5000]},
        {'name': 'Google DNS', 'host': '8.8.8.8', 'ports': [53]},
        {'name': 'Cloudflare DNS', 'host': '1.1.1.1', 'ports': [53]},
    ]
    
    # Add devices to test targets
    for device in devices:
        test_targets.append({
            'name': f"{device['hostname']} ({device['ip']})",
            'host': device['ip'],
            'ports': [22, 23, 80, 443],
            'device': device
        })
    
    # Initialize results without running tests initially
    results = []
    for target in test_targets:
        results.append({
            'name': target['name'],
            'host': target['host'],
            'ping': None,  # Will be None until tested
            'ports': {port: None for port in target['ports']},  # Initialize ports as None
            'device': target.get('device')
        })
    
    return render_template('dashboard.html', 
                         devices=devices, 
                         test_results=results,
                         active_page='dashboard')

@app.route('/refresh_status', methods=['POST'])
def refresh_status():
    if not session.get('logged_in'):
        return jsonify({'error': 'Not authorized'}), 401
    
    # Get all test targets
    inventory = load_inventory()
    devices = inventory.get('devices', [])
    test_targets = [
        {'name': 'GNS3 Local Server', 'host': 'localhost', 'ports': [80, 3080, 5000]},
        {'name': 'Google DNS', 'host': '8.8.8.8', 'ports': [53]},
        {'name': 'Cloudflare DNS', 'host': '1.1.1.1', 'ports': [53]},
    ]
    
    # Add devices to test targets
    for device in devices:
        test_targets.append({
            'name': f"{device['hostname']} ({device['ip']})",
            'host': device['ip'],
            'ports': [22, 23, 80, 443],
            'device': device
        })
    
    # Run tests
    results = []
    for target in test_targets:
        ping_result = ping_host(target['host'])
        port_results = {}
        for port in target['ports']:
            port_status = scan_port(target['host'], port)
            port_results[port] = "Open" if port_status[1] == "Open" else "Closed"
        
        results.append({
            'name': target['name'],
            'host': target['host'],
            'ping': ping_result,
            'ports': port_results,
            'device': target.get('device')
        })
    
    return jsonify(results)

@app.route('/add_device', methods=['POST'])
def add_device():
    if not session.get('logged_in'):
        flash('Not authorized', 'danger')
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
    
    try:
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
        
    except Exception as e:
        flash(f'Failed to add device: {str(e)}', 'danger')
        return redirect(url_for('dashboard'))

@app.route('/device/<device_id>/delete', methods=['POST'])
def delete_device(device_id):
    if not session.get('logged_in'):
        flash('Not authorized', 'danger')
        return redirect(url_for('login'))
        
    try:
        inventory = load_inventory()
        devices = inventory.get('devices', [])
        initial_count = len(devices)
        
        # Convert device_id to string for comparison
        device_id = str(device_id)
        
        # Remove the device with the matching ID
        inventory['devices'] = [d for d in devices if str(d.get('id')) != device_id]
        
        if len(inventory['devices']) < initial_count:
            save_inventory(inventory)
            flash('Device deleted successfully', 'success')
        else:
            flash('Device not found', 'danger')
            
    except Exception as e:
        flash(f'Failed to delete device: {str(e)}', 'danger')
    
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
    
    # Get all devices for the sidebar
    devices = inventory.get('devices', [])
    
    # Add status to each device
    for dev in devices:
        dev['status'] = 'online' if ping_host(dev['ip']) else 'offline'
    
    return render_template('console.html', 
                         device=device, 
                         output=output,
                         devices=devices)

@app.route('/testnetwork')
def test_network():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    # Common network devices and their common ports
    test_targets = [
        {'name': 'GNS3 Local Server', 'host': 'localhost', 'ports': [80, 3080, 5000]},
        {'name': 'Google DNS', 'host': '8.8.8.8', 'ports': [53]},
        {'name': 'Cloudflare DNS', 'host': '1.1.1.1', 'ports': [53]},
    ]
    
    # Add devices from inventory
    try:
        inventory = load_inventory()
        for device in inventory.get('devices', []):
            test_targets.append({
                'name': f"{device['hostname']} ({device['ip']})",
                'host': device['ip'],
                'ports': [22, 23, 80, 443],  # Common management ports
                'device': device
            })
    except Exception as e:
        flash(f'Error loading inventory: {str(e)}', 'danger')
    
    results = []
    for target in test_targets:
        ping_result = ping_host(target['host'])
        port_results = {}
        for port in target['ports']:
            port_status = scan_port(target['host'], port)
            port_results[port] = "Open" if port_status[1] == "Open" else "Closed"
        
        results.append({
            'name': target['name'],
            'host': target['host'],
            'ping': ping_result,
            'ports': port_results,
            'device': target.get('device')
        })
    
    return render_template('test_network.html', results=results)

@app.route('/api/port/<host>/<int:port>')
def api_port_check(host, port):
    return jsonify({'status': 'success', 'open': check_port(host, port)})

def login_required(f):
    """Decorator to ensure user is logged in."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            if request.is_json:
                return jsonify({'error': 'Unauthorized'}), 401
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def ping_host(ip):
    """Ping a host and return True if reachable."""
    param = '-n' if platform.system().lower() == 'windows' else '-c'
    command = ['ping', param, '2', '-w', '1', ip]
    try:
        output = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=2)
        return output.returncode == 0
    except subprocess.TimeoutExpired:
        return False

@app.route('/api/ping/<ip>')
@login_required
def api_ping(ip):
    """API endpoint to ping a device."""
    try:
        is_alive = ping_host(ip)
        return jsonify({
            'status': 'success',
            'ip': ip,
            'alive': is_alive,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

'''@app.route('/device/<device_id>', methods=['DELETE'])
@login_required
def delete_device(device_id):
    if not session.get('logged_in'):
        return jsonify({'status': 'error', 'message': 'Not authorized'}), 401
        
    try:
        inventory = load_inventory()
        devices = inventory.get('devices', [])
        initial_count = len(devices)
        
        # Convert device_id to string for comparison
        device_id = str(device_id)
        
        # Remove the device with the matching ID
        inventory['devices'] = [d for d in devices if str(d.get('id')) != device_id]
        
        if len(inventory['devices']) < initial_count:
            save_inventory(inventory)
            return jsonify({
                'status': 'success',
                'message': 'Device deleted successfully'
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Device not found'
            }), 404
            
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Failed to delete device: {str(e)}'
        }), 500'''

@app.route('/backup/all', methods=['POST'])
@login_required
def backup_all_devices():
    """Backup all devices in the inventory."""
    try:
        inventory = load_inventory()
        results = []
        
        for device in inventory['devices']:
            try:
                result = backup_config_ssh(
                    device['ip'],
                    device['username'],
                    device['password'],
                    device.get('device_type', 'cisco_ios')
                )
                device['last_backup'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                results.append({
                    'device': device['hostname'],
                    'ip': device['ip'],
                    'status': 'success',
                    'message': 'Backup completed successfully'
                })
            except Exception as e:
                results.append({
                    'device': device.get('hostname', 'Unknown'),
                    'ip': device['ip'],
                    'status': 'error',
                    'message': str(e)
                })
        
        save_inventory(inventory)
        return jsonify({
            'status': 'success',
            'results': results
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Backup failed: {str(e)}'
        }), 500

@app.route('/backup/<device_ip>')
@login_required
def backup_now(device_ip):
    """Backup a single device."""
    inventory = load_inventory()
    device = next((d for d in inventory['devices'] if d['ip'] == device_ip), None)
    
    if not device:
        if request.is_json:
            return jsonify({'error': 'Device not found'}), 404
        flash('Device not found', 'danger')
        return redirect(url_for('dashboard'))
    
    try:
        result = backup_config_ssh(
            device['ip'],
            device['username'],
            device['password'],
            device.get('device_type', 'cisco_ios')
        )
        
        # Update last backup time
        for d in inventory['devices']:
            if d['ip'] == device_ip:
                d['last_backup'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                break
        save_inventory(inventory)
        
        if request.is_json:
            return jsonify({
                'status': 'success',
                'message': f'Backup completed: {result}'
            })
        flash(f'Backup completed: {result}', 'success')
    except Exception as e:
        if request.is_json:
            return jsonify({
                'status': 'error',
                'message': f'Backup failed: {str(e)}'
            }), 500
        flash(f'Backup failed: {str(e)}', 'danger')
    
    if request.is_json:
        return jsonify({'status': 'success'})
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