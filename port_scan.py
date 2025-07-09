import socket
import concurrent.futures
from datetime import datetime

def scan_port(ip, port):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            result = s.connect_ex((ip, port))
            if result == 0:
                return port, "Open"
            return port, "Closed"
    except Exception as e:
        return port, f"Error: {str(e)}"

def main():
    target = "192.168.8.1"
    common_ports = [
        21,    # FTP
        22,    # SSH
        23,    # Telnet
        80,    # HTTP
        161,   # SNMP
        443,   # HTTPS
        8080,  # HTTP Alt
        830,   # NETCONF
        3389,  # RDP
        2222   # SSH Alt
    ]
    
    print(f"Scanning {target} for open ports...")
    print("-" * 40)
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_port = {executor.submit(scan_port, target, port): port for port in common_ports}
        for future in concurrent.futures.as_completed(future_to_port):
            port = future_to_port[future]
            try:
                port_status = future.result()
                print(f"Port {port_status[0]}: {port_status[1]}")
            except Exception as e:
                print(f"Error scanning port {port}: {e}")

if __name__ == "__main__":
    main()
