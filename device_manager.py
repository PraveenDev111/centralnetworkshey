import paramiko
import json
import os
from datetime import datetime

# Define the path to the backups directory
BACKUP_DIR = "backups"

def get_device_info(device_ip):
    """Retrieves device details from the inventory."""
    with open('database/inventory.json', 'r') as f:
        inventory = json.load(f)
    for device in inventory:
        if device['ip'] == device_ip:
            return device
    return None

def run_command(device_ip, command):
    """Connects to a device via SSH and runs a single command."""
    device = get_device_info(device_ip)
    if not device:
        return "Device not found in inventory."

    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=device['ip'],
            username=device['username'],
            password=device['password'],
            timeout=5
        )
        stdin, stdout, stderr = client.exec_command(command)
        output = stdout.read().decode('utf-8')
        client.close()
        return output
    except Exception as e:
        return f"An error occurred: {str(e)}"

def backup_config_ssh(device_ip):
    """Backs up the running configuration of a device."""
    device = get_device_info(device_ip)
    if not device:
        return f"Error: Device {device_ip} not found."

    # Define the 'show run' command based on device type
    commands = {
        "cisco_ios": "show running-config",
        "arista_eos": "show running-config"
        # Add other device types here
    }
    command = commands.get(device['device_type'])
    if not command:
        return f"Error: Backup command not defined for device type {device['device_type']}."

    config_output = run_command(device_ip, command)

    if "An error occurred" in config_output:
        return f"Failed to backup {device['hostname']}: {config_output}"
    
    # Create the backups directory if it doesn't exist
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)

    # Create a unique filename
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{device['hostname']}_{timestamp}.cfg"
    filepath = os.path.join(BACKUP_DIR, filename)

    # Save the configuration
    with open(filepath, 'w') as f:
        f.write(config_output)

    return f"Successfully backed up {device['hostname']} to {filename}"