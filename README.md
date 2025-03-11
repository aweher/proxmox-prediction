# Proxmox Cluster Monitoring and Prediction Tool

A comprehensive utility for monitoring Proxmox VE clusters, displaying resource utilization, and predicting VM growth capacity.

Proudly made by [Ariel S. Weher](https://ayuda.la) for the Proxmox VE community.

## Features

- **Real-time Monitoring**: Track CPU, memory, and disk usage across all Proxmox nodes
- **VM Status Tracking**: Display running and stopped VMs across the cluster
- **Resource Utilization**: Color-coded display of resource usage with warning thresholds
- **Growth Prediction**: Calculate potential additional VM capacity based on current resource allocation
- **VM Details**: Option to list all VMs with their resource allocations
- **JSON Export**: Export monitoring data for external analysis or historical tracking
- **Cross-platform**: Works on any system with Python 3.x

## Installation

### Prerequisites

- Python 3.6 or higher
- Proxmox VE cluster with API access

### Setup

1. Clone the repository or download the script files
   ```bash
   git clone https://github.com/yourusername/proxmox-monitor.git
   cd proxmox-monitor
   ```

2. Install the required dependencies
   ```bash
   pip install -r requirements.txt
   ```

3. Create a credentials file (see below for format)

## Configuration

Create a YAML file named `proxmox_credentials.yaml` with your Proxmox server details:

```yaml
servers:
  proxmox1.example.com:
    username: root@pam
    password: your_password
  proxmox2.example.com:
    username: root@pam
    password: your_password
```

## Usage

Basic usage:
```bash
python3 proxmox_monitor.py
```

### Command-line Options

```bash
usage: proxmox_monitor.py [-h] [-c CONFIG] [-e] [-o OUTPUT] [-v] [-l]

Proxmox Cluster Monitoring and Prediction Tool

options:
  -h, --help            show this help message and exit
  -c CONFIG, --config CONFIG
                        Path to credentials YAML file (default: proxmox_credentials.yaml)
  -e, --export          Export results to JSON file
  -o OUTPUT, --output OUTPUT
                        Export filename (default: proxmox_stats.json)
  -v, --verbose         Enable verbose output (debug mode)
  -l, --list-vms        Display detailed VM list for each server
```

### Examples

Display basic monitoring information:
```bash
python proxmox_monitor.py
```

Show detailed VM lists for all servers:
```bash
python proxmox_monitor.py --list-vms
```

Export data to a JSON file:
```bash
python proxmox_monitor.py --export
```

Specify a custom credentials file and export location:
```bash
python proxmox_monitor.py --config my_credentials.yaml --export --output cluster_stats.json
```

Enable verbose logging:
```bash
python proxmox_monitor.py --verbose
```

## Output Example

The dashboard displays:
- Server and node information
- Running and stopped VMs
- CPU, memory, and disk utilization
- Color-coded resource availability (green, yellow, red)
- Total VM counts
- Cluster-wide resource utilization percentages
- Prediction of additional VMs that can be supported

## Dependencies

- proxmoxer: For Proxmox API interactions
- pyyaml: For config file parsing
- prettytable: For formatted output
- colorama: For cross-platform colored terminal output
- tenacity: For retry logic

## Logging

The application logs to both console and a log file (`proxmox_monitor.log`). Use the `--verbose` flag for detailed debugging information.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
