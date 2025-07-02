import json
from device_manager import backup_config_ssh

def run_all_backups():
    """Job to back up all devices in the inventory."""
    print("--- Starting scheduled backup job ---")
    try:
        with open('database/inventory.json', 'r') as f:
            inventory = json.load(f)
        
        for device in inventory:
            print(f"Backing up {device['hostname']} ({device['ip']})...")
            result = backup_config_ssh(device['ip'])
            print(result)

    except Exception as e:
        print(f"An error occurred during scheduled backup: {str(e)}")
    print("--- Scheduled backup job finished ---")