#!/usr/bin/env python3
from datetime import datetime, timedelta
import json
import logging
import proxmoxer
from prettytable import PrettyTable
from tenacity import retry, stop_after_attempt, wait_exponential
import yaml
import argparse
from colorama import init, Fore, Back, Style
import time

# Initialize colorama for cross-platform color support
init(autoreset=True)

def safe_numeric(value, default=0):
    """Safely convert a value to a numeric type for division operations."""
    if value is None:
        return default
    try:
        if isinstance(value, str):
            return float(value)
        return float(value)
    except (ValueError, TypeError):
        return default

def format_uptime(seconds):
    """Convert seconds to human readable uptime format"""
    if seconds is None or seconds == 0:
        return "N/A"
    
    try:
        seconds = int(seconds)
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        minutes = (seconds % 3600) // 60
        
        if days > 0:
            return f"{days}d {hours}h {minutes}m"
        elif hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m"
    except:
        return "N/A"

def format_bytes(bytes_value):
    """Convert bytes to human readable format"""
    if bytes_value is None:
        return "N/A"
    
    try:
        bytes_value = float(bytes_value)
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_value < 1024.0:
                return f"{bytes_value:.2f} {unit}"
            bytes_value /= 1024.0
        return f"{bytes_value:.2f} PB"
    except:
        return "N/A"

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
logger = logging.getLogger("proxmox_vm_details")
logger.setLevel(logging.INFO)
file_handler = logging.FileHandler("proxmox_vm_details.log")
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

console_handler = logging.StreamHandler()
console_handler.setFormatter(ColoredFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(console_handler)

def load_credentials(yaml_file):
    """Load credentials from YAML file"""
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

def parse_disk_size(size_str):
    """Convert disk size to GB"""
    if not size_str:
        return 0
    
    size_str = str(size_str).strip()
    if size_str.endswith('G'):
        return float(size_str.replace('G', ''))
    elif size_str.endswith('M'):
        return float(size_str.replace('M', '')) / 1024
    elif size_str.endswith('K'):
        return float(size_str.replace('K', '')) / (1024 ** 2)
    elif size_str.endswith('T'):
        return float(size_str.replace('T', '')) * 1024
    else:
        try:
            return float(size_str) / (1024 ** 3)  # Assume bytes
        except ValueError:
            return 0

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30))
def get_detailed_vm_info(server, username, password, status_filter=None, name_filter=None):
    """Get detailed information about all VMs"""
    try:
        logger.info(f"Connecting to {server}...")
        proxmox = proxmoxer.ProxmoxAPI(server, user=username, password=password, verify_ssl=False, timeout=15)
        nodes = proxmox.nodes.get()
        
        server_hostname = server.split('.')[0]
        all_vms = []
        
        for node in nodes:
            node_name = node['node']
            
            if node_name == server_hostname:
                logger.debug(f"Processing node {node_name}")
                
                # Get node information
                node_stats = proxmox.nodes(node_name).status.get()
                vms = proxmox.nodes(node_name).qemu.get()
                
                for vm in vms:
                    vm_id = vm['vmid']
                    vm_name = vm['name']
                    status = vm['status']
                    
                    # Apply filters
                    if status_filter and status != status_filter:
                        continue
                    if name_filter and name_filter.lower() not in vm_name.lower():
                        continue
                    
                    # Get VM configuration
                    vm_config = proxmox.nodes(node_name).qemu(vm_id).config.get()
                    
                    # Get VM current status and statistics
                    vm_current = None
                    if status == 'running':
                        try:
                            vm_current = proxmox.nodes(node_name).qemu(vm_id).status.current.get()
                        except Exception as e:
                            logger.debug(f"Could not get current status for VM {vm_name}: {e}")
                    
                    # Basic VM information
                    vm_info = {
                        'server': server,
                        'node': node_name,
                        'vmid': vm_id,
                        'name': vm_name,
                        'status': status,
                        'cores': safe_numeric(vm_config.get('cores', 1)),
                        'sockets': safe_numeric(vm_config.get('sockets', 1)),
                        'memory_mb': safe_numeric(vm_config.get('memory', 0)),
                        'memory_gb': safe_numeric(vm_config.get('memory', 0)) / 1024,
                        'boot_order': vm_config.get('boot', 'N/A'),
                        'os_type': vm_config.get('ostype', 'N/A'),
                        'machine': vm_config.get('machine', 'N/A'),
                        'bios': vm_config.get('bios', 'N/A'),
                        'agent': vm_config.get('agent', 'N/A'),
                        'template': vm_config.get('template', 0) == 1
                    }
                    
                    # CPU information
                    if status == 'running' and vm_current:
                        vm_info['cpu_usage_percent'] = safe_numeric(vm_current.get('cpu', 0)) * 100
                        vm_info['uptime_seconds'] = safe_numeric(vm_current.get('uptime', 0))
                        vm_info['uptime_formatted'] = format_uptime(vm_current.get('uptime', 0))
                        vm_info['memory_used_bytes'] = safe_numeric(vm_current.get('mem', 0))
                        vm_info['memory_used_gb'] = safe_numeric(vm_current.get('mem', 0)) / (1024**3)
                        vm_info['memory_max_bytes'] = safe_numeric(vm_current.get('maxmem', 0))
                        vm_info['memory_max_gb'] = safe_numeric(vm_current.get('maxmem', 0)) / (1024**3)
                    else:
                        vm_info['cpu_usage_percent'] = 0
                        vm_info['uptime_seconds'] = 0
                        vm_info['uptime_formatted'] = "Stopped"
                        vm_info['memory_used_bytes'] = 0
                        vm_info['memory_used_gb'] = 0
                        vm_info['memory_max_bytes'] = 0
                        vm_info['memory_max_gb'] = 0
                    
                    # Disk information
                    disks = []
                    total_disk_size = 0
                    disk_prefixes = ['scsi', 'virtio', 'ide', 'sata']
                    
                    for key in vm_config:
                        is_disk = False
                        for prefix in disk_prefixes:
                            if key.startswith(prefix) and key[len(prefix):].isdigit():
                                is_disk = True
                                break
                        
                        if is_disk and vm_config[key]:
                            disk_str = vm_config[key]
                            parts = disk_str.split(',')
                            
                            # Extract storage and size
                            storage = parts[0].split(':')[1] if ':' in parts[0] else parts[0]
                            size_gb = 0
                            
                            size_part = [part for part in parts if 'size=' in part]
                            if size_part:
                                size_str = size_part[0].split('=')[1]
                                size_gb = parse_disk_size(size_str)
                            
                            disks.append({
                                'interface': key,
                                'storage': storage,
                                'size_gb': size_gb,
                                'raw_config': disk_str
                            })
                            total_disk_size += size_gb
                    
                    vm_info['disks'] = disks
                    vm_info['total_disk_gb'] = total_disk_size
                    
                    # Network information
                    networks = []
                    for key in vm_config:
                        if key.startswith('net') and key[3:].isdigit():
                            net_config = vm_config[key]
                            net_parts = net_config.split(',')
                            
                            network_info = {
                                'interface': key,
                                'raw_config': net_config
                            }
                            
                            # Parse network configuration
                            for part in net_parts:
                                if '=' in part:
                                    k, v = part.split('=', 1)
                                    network_info[k] = v
                                else:
                                    network_info['model'] = part
                            
                            networks.append(network_info)
                    
                    vm_info['networks'] = networks
                    
                    # Additional configuration
                    vm_info['description'] = vm_config.get('description', '')
                    vm_info['tags'] = vm_config.get('tags', '')
                    
                    all_vms.append(vm_info)
        
        return all_vms
        
    except Exception as e:
        logger.error(f"Error connecting to {server}: {str(e)}")
        logger.debug(f"Detailed error information:", exc_info=True)
        raise

def display_vm_summary(vms):
    """Display a summary table of all VMs"""
    if not vms:
        print(f"{Fore.RED}No VMs found matching the criteria.{Style.RESET_ALL}")
        return
    
    print(f"\n{Fore.CYAN}{Style.BRIGHT}VM Summary - {len(vms)} VMs found{Style.RESET_ALL}")
    
    table = PrettyTable()
    table.field_names = ["Server", "Node", "VMID", "Name", "Status", "CPU", "RAM (GB)", 
                         "Disk (GB)", "Uptime", "CPU %", "OS Type"]
    
    for vm in sorted(vms, key=lambda x: (x['server'], x['node'], x['vmid'])):
        status_color = Fore.GREEN if vm['status'] == 'running' else Fore.RED
        cpu_color = Fore.RED if vm['cpu_usage_percent'] > 80 else (Fore.YELLOW if vm['cpu_usage_percent'] > 60 else Fore.GREEN)
        
        table.add_row([
            vm['server'].split('.')[0],
            vm['node'],
            vm['vmid'],
            vm['name'][:20] + '...' if len(vm['name']) > 20 else vm['name'],
            f"{status_color}{vm['status']}{Style.RESET_ALL}",
            f"{vm['cores']}C/{vm['sockets']}S",
            f"{vm['memory_gb']:.1f}",
            f"{vm['total_disk_gb']:.1f}",
            vm['uptime_formatted'],
            f"{cpu_color}{vm['cpu_usage_percent']:.1f}%{Style.RESET_ALL}" if vm['status'] == 'running' else "N/A",
            vm['os_type'][:10] if vm['os_type'] != 'N/A' else 'N/A'
        ])
    
    print(table)

def display_detailed_vm_info(vms, show_all_details=False):
    """Display detailed information for each VM"""
    if not vms:
        print(f"{Fore.RED}No VMs found matching the criteria.{Style.RESET_ALL}")
        return
    
    for vm in sorted(vms, key=lambda x: (x['server'], x['node'], x['vmid'])):
        print(f"\n{Fore.CYAN}{Style.BRIGHT}{'='*80}")
        print(f"VM: {vm['name']} (ID: {vm['vmid']}) on {vm['server']}")
        print(f"{'='*80}{Style.RESET_ALL}")
        
        # Basic information
        status_color = Fore.GREEN if vm['status'] == 'running' else Fore.RED
        template_text = " [TEMPLATE]" if vm['template'] else ""
        
        print(f"{Fore.YELLOW}Basic Information:{Style.RESET_ALL}")
        print(f"  Server: {vm['server']}")
        print(f"  Node: {vm['node']}")
        print(f"  Status: {status_color}{vm['status']}{Style.RESET_ALL}{template_text}")
        print(f"  OS Type: {vm['os_type']}")
        print(f"  Machine: {vm['machine']}")
        print(f"  BIOS: {vm['bios']}")
        print(f"  Agent: {vm['agent']}")
        if vm['description']:
            print(f"  Description: {vm['description']}")
        if vm['tags']:
            print(f"  Tags: {vm['tags']}")
        
        # CPU and Memory
        print(f"\n{Fore.YELLOW}CPU & Memory:{Style.RESET_ALL}")
        print(f"  CPU Cores: {vm['cores']}")
        print(f"  CPU Sockets: {vm['sockets']}")
        print(f"  Memory: {vm['memory_gb']:.2f} GB ({vm['memory_mb']} MB)")
        
        if vm['status'] == 'running':
            cpu_color = Fore.RED if vm['cpu_usage_percent'] > 80 else (Fore.YELLOW if vm['cpu_usage_percent'] > 60 else Fore.GREEN)
            print(f"  CPU Usage: {cpu_color}{vm['cpu_usage_percent']:.2f}%{Style.RESET_ALL}")
            print(f"  Memory Used: {vm['memory_used_gb']:.2f} GB / {vm['memory_max_gb']:.2f} GB")
            print(f"  Uptime: {vm['uptime_formatted']}")
        
        # Disk information
        if vm['disks']:
            print(f"\n{Fore.YELLOW}Disk Information:{Style.RESET_ALL}")
            for disk in vm['disks']:
                print(f"  {disk['interface']}: {disk['size_gb']:.2f} GB on {disk['storage']}")
                if show_all_details:
                    print(f"    Raw config: {disk['raw_config']}")
            print(f"  Total Disk Space: {vm['total_disk_gb']:.2f} GB")
        
        # Network information
        if vm['networks']:
            print(f"\n{Fore.YELLOW}Network Information:{Style.RESET_ALL}")
            for net in vm['networks']:
                model = net.get('model', 'Unknown')
                bridge = net.get('bridge', 'N/A')
                mac = net.get('macaddr', 'N/A')
                print(f"  {net['interface']}: {model} on {bridge}")
                if mac != 'N/A':
                    print(f"    MAC: {mac}")
                if show_all_details:
                    print(f"    Raw config: {net['raw_config']}")
        
        print(f"  Boot Order: {vm['boot_order']}")

def display_statistics(vms):
    """Display general statistics about the VMs"""
    if not vms:
        return
    
    print(f"\n{Fore.CYAN}{Style.BRIGHT}VM Statistics{Style.RESET_ALL}")
    
    # Status statistics
    running_vms = [vm for vm in vms if vm['status'] == 'running']
    stopped_vms = [vm for vm in vms if vm['status'] != 'running']
    template_vms = [vm for vm in vms if vm['template']]
    
    print(f"Total VMs: {len(vms)}")
    print(f"Running VMs: {Fore.GREEN}{len(running_vms)}{Style.RESET_ALL}")
    print(f"Stopped VMs: {Fore.RED}{len(stopped_vms)}{Style.RESET_ALL}")
    print(f"Templates: {len(template_vms)}")
    
    if running_vms:
        # Resource statistics for running VMs
        total_cpu_cores = sum(vm['cores'] for vm in running_vms)
        total_memory = sum(vm['memory_gb'] for vm in running_vms)
        total_disk = sum(vm['total_disk_gb'] for vm in vms)  # Include all VMs for disk
        avg_cpu_usage = sum(vm['cpu_usage_percent'] for vm in running_vms) / len(running_vms)
        
        print(f"\n{Fore.YELLOW}Resource Usage (Running VMs):{Style.RESET_ALL}")
        print(f"Total CPU Cores: {total_cpu_cores}")
        print(f"Total Memory: {total_memory:.2f} GB")
        print(f"Average CPU Usage: {avg_cpu_usage:.2f}%")
        print(f"Total Disk Space (All VMs): {total_disk:.2f} GB")
    
    # OS Type statistics
    os_types = {}
    for vm in vms:
        if not vm['template']:  # Exclude templates
            os_type = vm['os_type'] if vm['os_type'] != 'N/A' else 'Unknown'
            os_types[os_type] = os_types.get(os_type, 0) + 1
    
    if os_types:
        print(f"\n{Fore.YELLOW}OS Distribution:{Style.RESET_ALL}")
        for os_type, count in sorted(os_types.items(), key=lambda x: x[1], reverse=True):
            print(f"  {os_type}: {count}")

def export_vm_data(vms, filename="vm_details.json"):
    """Export VM data to JSON file"""
    data = {
        "timestamp": datetime.now().isoformat(),
        "total_vms": len(vms),
        "vms": vms
    }
    
    with open(filename, 'w') as f:
        json.dump(data, f, indent=2, default=str)
    
    logger.info(f"VM data exported to {filename}")
    print(f"{Fore.GREEN}VM data exported to {filename}{Style.RESET_ALL}")

def main():
    parser = argparse.ArgumentParser(description="Proxmox VM Details and Monitoring Tool")
    parser.add_argument("-c", "--config", default="proxmox_credentials.yaml", 
                        help="Path to credentials YAML file (default: proxmox_credentials.yaml)")
    parser.add_argument("-s", "--status", choices=['running', 'stopped'], 
                        help="Filter VMs by status")
    parser.add_argument("-n", "--name", 
                        help="Filter VMs by name (case insensitive partial match)")
    parser.add_argument("-d", "--detailed", action="store_true", 
                        help="Show detailed information for each VM")
    parser.add_argument("-a", "--all-details", action="store_true", 
                        help="Show all configuration details (includes raw configs)")
    parser.add_argument("-e", "--export", action="store_true", 
                        help="Export results to JSON file")
    parser.add_argument("-o", "--output", default="vm_details.json",
                        help="Export filename (default: vm_details.json)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Enable verbose output (debug mode)")
    parser.add_argument("--summary-only", action="store_true",
                        help="Show only summary table, no detailed info")
    parser.add_argument("--stats", action="store_true",
                        help="Show VM statistics")
    
    args = parser.parse_args()
    
    # Set logging level based on verbose flag
    if args.verbose:
        logger.setLevel(logging.DEBUG)
        console_handler.setLevel(logging.DEBUG)
        logger.debug("Debug mode enabled")
    
    yaml_file = args.config
    logger.info(f"Starting Proxmox VM details application using {yaml_file}")
    
    # Display banner
    print(f"\n{Fore.CYAN}{Style.BRIGHT}{'=' * 70}")
    print(f"PROXMOX VM DETAILS AND MONITORING TOOL")
    print(f"{'=' * 70}{Style.RESET_ALL}\n")
    
    servers = load_credentials(yaml_file)
    
    if not servers:
        logger.error("No valid credentials loaded from the YAML file.")
        print(f"{Fore.RED}Error: No valid credentials loaded from {yaml_file}{Style.RESET_ALL}")
        return
    
    all_vms = []
    
    for server, creds in servers.items():
        logger.info(f"Processing server {server}...")
        print(f"{Fore.BLUE}Processing server {server}...{Style.RESET_ALL}")
        
        try:
            vms = get_detailed_vm_info(server, creds['username'], creds['password'], 
                                     args.status, args.name)
            all_vms.extend(vms)
            print(f"{Fore.GREEN}Found {len(vms)} VMs on {server}{Style.RESET_ALL}")
            
        except Exception as e:
            logger.error(f"Failed to process server {server}: {e}")
            print(f"{Fore.RED}Error: Failed to process server {server}: {e}{Style.RESET_ALL}")
    
    if not all_vms:
        logger.error("No VMs found matching the criteria.")
        print(f"{Fore.RED}No VMs found matching the criteria.{Style.RESET_ALL}")
        return
    
    # Display results based on arguments
    if not args.summary_only:
        display_vm_summary(all_vms)
    
    if args.stats:
        display_statistics(all_vms)
    
    if args.detailed or args.all_details:
        display_detailed_vm_info(all_vms, args.all_details)
    elif args.summary_only:
        display_vm_summary(all_vms)
    
    # Export data if requested
    if args.export:
        export_vm_data(all_vms, args.output)
    
    logger.info("VM details monitoring complete")
    print(f"\n{Fore.GREEN}VM details monitoring complete!{Style.RESET_ALL}")

if __name__ == "__main__":
    main() 