#!/usr/bin/env python3
from datetime import datetime
import json
import logging
import proxmoxer
from prettytable import PrettyTable
from tenacity import retry, stop_after_attempt, wait_exponential
import yaml
import argparse
from colorama import init, Fore, Back, Style

# Initialize colorama for cross-platform color support
init(autoreset=True)

def safe_numeric(value, default=0):
    """Safely convert a value to a numeric type for division operations."""
    if value is None:
        return default
    try:
        if isinstance(value, str):
            # Try to convert string to float or int
            return float(value)
        return float(value)  # Handle other numeric types
    except (ValueError, TypeError):
        return default

# Configure logging with colors
class ColoredFormatter(logging.Formatter):
    COLORS = {
        'INFO': Fore.GREEN,
        'WARNING': Fore.YELLOW,
        'ERROR': Fore.RED,
        'CRITICAL': Fore.RED + Back.WHITE,
        'DEBUG': Fore.BLUE
    }

    def format(self, record):
        log_message = super().format(record)
        return f"{self.COLORS.get(record.levelname, '')}{log_message}{Style.RESET_ALL}"

# Configure logging
logger = logging.getLogger("proxmox_monitor")
logger.setLevel(logging.INFO)
file_handler = logging.FileHandler("proxmox_monitor.log")
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

console_handler = logging.StreamHandler()
console_handler.setFormatter(ColoredFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(console_handler)

# Function to load credentials from YAML
def load_credentials(yaml_file):
    try:
        with open(yaml_file, 'r') as file:
            data = yaml.safe_load(file)
        return data.get('servers', {})
    except FileNotFoundError:
        logger.error(f"Error: {yaml_file} not found.")
        return {}
    except yaml.YAMLError as e:
        logger.error(f"Error parsing YAML: {e}")
        return {}

# Function to convert disk size to GB
def parse_disk_size(size_str):
    size_str = str(size_str).strip()  # Ensure string type
    if size_str.endswith('G'):
        return float(size_str.replace('G', ''))
    elif size_str.endswith('M'):
        return float(size_str.replace('M', '')) / 1024
    elif size_str.endswith('K'):
        return float(size_str.replace('K', '')) / (1024 ** 3)
    elif size_str.endswith('T'):
        return float(size_str.replace('T', '')) * 1024
    else:
        try:
            return float(size_str) / (1024 ** 3)  # Assume bytes
        except ValueError:
            return 0

# Function to display the list of VMs on a server
def display_vm_list(server, nodes):
    logger.info(f"Displaying VMs on server {server}")
    print(f"\n{Fore.CYAN}{Style.BRIGHT}--- VMs on server {server} ---{Style.RESET_ALL}")
    for node_name, node_data in nodes.items():
        if 'vm_details' in node_data and node_data['vm_details']:
            table = PrettyTable()
            table.field_names = ["VM Name", "Status", "CPU", "RAM (GB)", "Disk (GB)"]
            
            for vm in node_data['vm_details']:
                status_color = Fore.GREEN if vm['status'] == 'running' else Fore.RED
                row = [
                    vm['vm_name'],
                    f"{status_color}{vm['status']}{Style.RESET_ALL}",
                    vm['cpu_assigned'],
                    f"{vm['mem_assigned']:.2f}",
                    f"{vm['disk_assigned']:.2f}"
                ]
                table.add_row(row)
            
            print(f"\n{Fore.YELLOW}{Style.BRIGHT}Node: {node_name}{Style.RESET_ALL}")
            print(table)
        else:
            print(f"\n{Fore.YELLOW}{Style.BRIGHT}Node: {node_name}{Style.RESET_ALL} - {Fore.RED}No VMs found{Style.RESET_ALL}")

# Function to get server statistics with retry mechanism
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30))
def get_server_stats(server, username, password):
    try:
        logger.info(f"Connecting to {server}...")
        proxmox = proxmoxer.ProxmoxAPI(server, user=username, password=password, verify_ssl=False, timeout=15)
        nodes = proxmox.nodes.get()
        node_data = {}
        
        # Create a server_hostname → node_name mapping
        server_hostname = server.split('.')[0]  # Extract hostname from FQDN
        logger.debug(f"Using hostname: {server_hostname} for server {server}")
        
        # Only process nodes that belong to this server
        for node in nodes:
            node_name = node['node']
            
            if node_name == server_hostname:
                logger.debug(f"Processing node {node_name}")
                node_stats = proxmox.nodes(node_name).status.get()
                vms = proxmox.nodes(node_name).qemu.get()
                
                # CPU and memory calculation
                total_cpu_max = safe_numeric(node_stats.get('cpuinfo', {}).get('cpus', 0))
                memory_total = safe_numeric(node_stats.get('memory', {}).get('total', 0))
                total_mem_max = memory_total / (1024**3)
                
                # Get all storage pools for this node
                storages = proxmox.nodes(node_name).storage.get()
                total_disk_max = 0
                for storage in storages:
                    # Skip storage types that don't represent local disk space
                    if storage.get('type') in ('dir', 'lvm', 'lvmthin', 'zfspool'):
                        # Get storage status to find total/used space
                        try:
                            storage_status = proxmox.nodes(node_name).storage(storage['storage']).status.get()
                            storage_total = safe_numeric(storage_status.get('total', 0))
                            total_disk_max += storage_total / (1024**3)
                        except Exception as e:
                            # Some storage types might not support status reporting
                            logger.warning(f"Could not get storage status for {storage['storage']}: {e}")
                # Rest of the VM processing
                total_cpu_used = 0
                total_mem_used = 0
                total_disk_used = 0
                vm_details = []
                
                for vm in vms:
                    vm_id = vm['vmid']
                    vm_name = vm['name']
                    status = vm['status']
                    
                    vm_config = proxmox.nodes(node_name).qemu(vm_id).config.get()
                    vm_cpu = safe_numeric(vm_config.get('cores', 1))
                    vm_memory = safe_numeric(vm_config.get('memory', 0))
                    vm_mem = vm_memory / 1024
                    vm_disk = 0
                    # Search for all disk types with any index number
                    disk_prefixes = ['scsi', 'virtio', 'ide', 'sata']
                    for key in vm_config:
                        # Check if the key starts with any disk prefixes
                        # and the rest is a number (e.g.: scsi0, scsi1, virtio0, etc.)
                        is_disk = False
                        for prefix in disk_prefixes:
                            if key.startswith(prefix) and key[len(prefix):].isdigit():
                                is_disk = True
                                break
                        
                        if is_disk and vm_config[key]:
                            disk_str = vm_config[key]
                            size_part = [part for part in disk_str.split(',') if 'size=' in part]
                            if size_part:
                                size_str = size_part[0].split('=')[1]
                                # Accumulate size instead of replacing it
                                vm_disk += parse_disk_size(size_str)
                    vm_details.append({
                        'server': server,
                        'node': node_name,
                        'vm_name': vm_name,
                        'status': status,
                        'cpu_assigned': vm_cpu,
                        'mem_assigned': vm_mem,
                        'disk_assigned': vm_disk
                    })
                    
                    if status == 'running':
                        total_cpu_used += vm_cpu
                        total_mem_used += vm_mem
                        total_disk_used += vm_disk
                
                node_data[node_name] = {
                    'vms_running': sum(1 for vm in vms if vm['status'] == 'running'),
                    'vms_stopped': sum(1 for vm in vms if vm['status'] != 'running'),
                    'cpu_used': total_cpu_used,
                    'cpu_free': total_cpu_max - total_cpu_used,
                    'cpu_max': total_cpu_max,
                    'mem_used': total_mem_used,
                    'mem_free': total_mem_max - total_mem_used,
                    'mem_max': total_mem_max,
                    'disk_used': total_disk_used,
                    'disk_free': total_disk_max - total_disk_used,
                    'disk_max': total_disk_max,
                    'vm_details': vm_details
                }
        
        return node_data
    except Exception as e:
        logger.error(f"Error connecting to {server}: {str(e)}")
        # Add more detailed logging in debug mode
        logger.debug(f"Detailed error information:", exc_info=True)
        raise

# Function to predict growth
def predict_growth(server_data):
    logger.info("Calculating growth prediction")
    total_vms_running = 0
    total_cpu_used = 0
    total_cpu_free = 0
    total_mem_used = 0
    total_mem_free = 0
    total_disk_used = 0
    total_disk_free = 0
    
    for nodes in server_data.values():
        for stats in nodes.values():
            total_vms_running += stats['vms_running']
            total_cpu_used += stats['cpu_used']
            total_cpu_free += stats['cpu_free']
            total_mem_used += stats['mem_used']
            total_mem_free += stats['mem_free']
            total_disk_used += stats['disk_used']
            total_disk_free += stats['disk_free']
    
    if total_vms_running == 0:
        logger.warning("No running VMs found, cannot predict growth")
        return 0
    
    # Calculate averages
    avg_cpu_per_vm = total_cpu_used / total_vms_running if total_vms_running > 0 else 0
    avg_mem_per_vm = total_mem_used / total_vms_running if total_vms_running > 0 else 0
    avg_disk_per_vm = total_disk_used / total_vms_running if total_vms_running > 0 else 0
    
    # Calculate potential growth (handle division by zero)
    cpu_based_growth = total_cpu_free / avg_cpu_per_vm if avg_cpu_per_vm > 0 else float('inf')
    mem_based_growth = total_mem_free / avg_mem_per_vm if avg_mem_per_vm > 0 else float('inf')
    disk_based_growth = total_disk_free / avg_disk_per_vm if avg_disk_per_vm > 0 else float('inf')
    
    # Return the minimum growth potential as an integer (minimum resources constraint)
    prediction = max(0, int(min(cpu_based_growth, mem_based_growth, disk_based_growth)))
    logger.info(f"Predicted potential additional VMs: {prediction}")
    return prediction

# Function to create dashboard and graphs
def create_dashboard(server_data, growth_prediction):
    logger.info("Creating dashboard")
    table = PrettyTable()
    table.field_names = ["Server", "Node", "VMs Running", "VMs Stopped", "CPU Used", "CPU Free", 
                         "Mem Used (GB)", "Mem Free (GB)", "Disk Used (GB)", "Disk Free (GB)"]
    
    total_running = 0
    total_stopped = 0
    for server, nodes in server_data.items():
        for node, stats in nodes.items():
            # Color free resources indicators based on thresholds
            cpu_free_color = Fore.GREEN if stats['cpu_free'] > stats['cpu_max'] * 0.3 else (Fore.YELLOW if stats['cpu_free'] > stats['cpu_max'] * 0.1 else Fore.RED)
            mem_free_color = Fore.GREEN if stats['mem_free'] > stats['mem_max'] * 0.3 else (Fore.YELLOW if stats['mem_free'] > stats['mem_max'] * 0.1 else Fore.RED)
            disk_free_color = Fore.GREEN if stats['disk_free'] > stats['disk_max'] * 0.3 else (Fore.YELLOW if stats['disk_free'] > stats['disk_max'] * 0.1 else Fore.RED)
            
            # Color for VMs stopped - green if 0, red if > 0
            stopped_color = Fore.GREEN if stats['vms_stopped'] == 0 else Fore.RED
            table.add_row([
                server, 
                node, 
                stats['vms_running'],  # No color for VMs running
                f"{stopped_color}{stats['vms_stopped']}{Style.RESET_ALL}",  # Green if 0, red if > 0
                f"{int(stats['cpu_used'])}/{int(stats['cpu_max'])}", 
                f"{cpu_free_color}{int(stats['cpu_free'])}{Style.RESET_ALL}", 
                f"{stats['mem_used']:.2f}/{stats['mem_max']:.2f}", 
                f"{mem_free_color}{stats['mem_free']:.2f}{Style.RESET_ALL}", 
                f"{stats['disk_used']:.2f}/{stats['disk_max']:.2f}", 
                f"{disk_free_color}{stats['disk_free']:.2f}{Style.RESET_ALL}"
            ])
            total_running += stats['vms_running']
            total_stopped += stats['vms_stopped']    
    print(f"\n{Fore.CYAN}{Style.BRIGHT}Proxmox Cluster Dashboard - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{Style.RESET_ALL}")
    print(table)
    # Determine color for total VMs stopped
    total_stopped_color = Fore.GREEN if total_stopped == 0 else Fore.RED
    
    print(f"\n{Fore.CYAN}{Style.BRIGHT}Proxmox Cluster Dashboard - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{Style.RESET_ALL}")
    print(table)
    print(f"\n{Fore.BLUE}Total VMs Running: {total_running}, Total VMs Stopped: {total_stopped_color}{total_stopped}{Style.RESET_ALL}")
    
    # Display growth prediction with color
    prediction_color = Fore.GREEN if growth_prediction > 10 else (Fore.YELLOW if growth_prediction > 3 else Fore.RED)
    print(f"{Fore.BLUE}Predicted additional VMs the cluster can support: {prediction_color}{growth_prediction}{Style.RESET_ALL}")
    
    # Display resource utilization averages
    total_cpu_max = sum(stats['cpu_max'] for nodes in server_data.values() for stats in nodes.values())
    total_cpu_used = sum(stats['cpu_used'] for nodes in server_data.values() for stats in nodes.values())
    total_mem_max = sum(stats['mem_max'] for nodes in server_data.values() for stats in nodes.values())
    total_mem_used = sum(stats['mem_used'] for nodes in server_data.values() for stats in nodes.values())
    total_disk_max = sum(stats['disk_max'] for nodes in server_data.values() for stats in nodes.values())
    total_disk_used = sum(stats['disk_used'] for nodes in server_data.values() for stats in nodes.values())
    
    cpu_percent = (total_cpu_used / total_cpu_max * 100) if total_cpu_max > 0 else 0
    mem_percent = (total_mem_used / total_mem_max * 100) if total_mem_max > 0 else 0
    disk_percent = (total_disk_used / total_disk_max * 100) if total_disk_max > 0 else 0
    
    cpu_color = Fore.GREEN if cpu_percent < 70 else (Fore.YELLOW if cpu_percent < 90 else Fore.RED)
    mem_color = Fore.GREEN if mem_percent < 70 else (Fore.YELLOW if mem_percent < 90 else Fore.RED)
    disk_color = Fore.GREEN if disk_percent < 70 else (Fore.YELLOW if disk_percent < 90 else Fore.RED)
    
    print(f"\n{Style.BRIGHT}Resource Utilization:{Style.RESET_ALL}")
    print(f"CPU: {cpu_color}{cpu_percent:.1f}%{Style.RESET_ALL}")
    print(f"Memory: {mem_color}{mem_percent:.1f}%{Style.RESET_ALL}")
    print(f"Disk: {disk_color}{disk_percent:.1f}%{Style.RESET_ALL}")

def export_to_json(server_data, growth_prediction, filename="proxmox_stats.json"):
    """Export collected data to JSON file"""
    data = {
        "timestamp": datetime.now().isoformat(),
        "growth_prediction": growth_prediction,
        "server_data": server_data
    }
    
    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)
    logger.info(f"Data exported to {filename}")
    print(f"{Fore.GREEN}Data exported to {filename}{Style.RESET_ALL}")

# Main function
def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Proxmox Cluster Monitoring and Prediction Tool")
    parser.add_argument("-c", "--config", default="proxmox_credentials.yaml", 
                        help="Path to credentials YAML file (default: proxmox_credentials.yaml)")
    parser.add_argument("-e", "--export", action="store_true", 
                        help="Export results to JSON file")
    parser.add_argument("-o", "--output", default="proxmox_stats.json",
                        help="Export filename (default: proxmox_stats.json)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Enable verbose output (debug mode)")
    parser.add_argument("-l", "--list-vms", action="store_true", 
                        help="Display detailed VM list for each server")
    args = parser.parse_args()
    
    # Set logging level based on verbose flag
    if args.verbose:
        logger.setLevel(logging.DEBUG)
        console_handler.setLevel(logging.DEBUG)
        logger.debug("Debug mode enabled")
    
    yaml_file = args.config
    logger.info(f"Starting Proxmox monitoring application using {yaml_file}")
    
    # Display banner
    print(f"\n{Fore.CYAN}{Style.BRIGHT}{'=' * 60}")
    print(f"PROXMOX CLUSTER MONITORING AND PREDICTION TOOL")
    print(f"{'=' * 60}{Style.RESET_ALL}\n")
    
    servers = load_credentials(yaml_file)
    
    if not servers:
        logger.error("No valid credentials loaded from the YAML file.")
        print(f"{Fore.RED}Error: No valid credentials loaded from {yaml_file}{Style.RESET_ALL}")
        return
    server_data = {}
    for server, creds in servers.items():
        logger.info(f"Processing server {server}...")
        print(f"{Fore.BLUE}Processing server {server}...{Style.RESET_ALL}")
        try:
            nodes = get_server_stats(server, creds['username'], creds['password'])
            if nodes:
                server_data[server] = nodes
                # Display VM list for this server if requested
                if args.list_vms:
                    display_vm_list(server, nodes)
            else:
                logger.warning(f"No data collected from server {server}")
                print(f"{Fore.YELLOW}Warning: No data collected from server {server}{Style.RESET_ALL}")
        except Exception as e:
            logger.error(f"Failed to process server {server}: {e}")
            print(f"{Fore.RED}Error: Failed to process server {server}: {e}{Style.RESET_ALL}")
    
    if not server_data:
        logger.error("No data collected from any server.")
        print(f"{Fore.RED}Error: No data collected from any server.{Style.RESET_ALL}")
        return
    
    growth_prediction = predict_growth(server_data)
    create_dashboard(server_data, growth_prediction)
    
    # Export data if requested
    if args.export:
        export_to_json(server_data, growth_prediction, args.output)
    
    logger.info("Monitoring complete")
    print(f"\n{Fore.GREEN}Monitoring complete!{Style.RESET_ALL}")

if __name__ == "__main__":
    main()
