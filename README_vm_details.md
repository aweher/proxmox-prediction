# Proxmox VM Details Monitor

Este script proporciona información detallada sobre todas las máquinas virtuales (VMs) que se ejecutan en tus servidores Proxmox.

## Características

- **Información detallada de VMs**: Muestra configuración completa, uso de recursos y estado de cada VM
- **Filtros avanzados**: Filtra por estado (running/stopped) y nombre de VM
- **Múltiples formatos de salida**: Resumen tabular, vista detallada y estadísticas
- **Exportación JSON**: Exporta todos los datos a archivo JSON para análisis posterior
- **Información en tiempo real**: Para VMs en ejecución, muestra CPU%, memoria usada y uptime
- **Configuración de red y disco**: Detalles completos de interfaces de red y discos

## Requisitos

- Python 3.6+
- Librerías: `proxmoxer`, `prettytable`, `tenacity`, `pyyaml`, `colorama`
- Archivo de credenciales YAML (mismo formato que proxmox_monitor.py)

## Instalación

```bash
pip install proxmoxer prettytable tenacity pyyaml colorama
```

## Uso

### Uso básico
```bash
python3 proxmox_vm_details.py
```

### Opciones disponibles

```bash
# Mostrar ayuda
python3 proxmox_vm_details.py -h

# Usar archivo de credenciales personalizado
python3 proxmox_vm_details.py -c mi_config.yaml

# Filtrar solo VMs en ejecución
python3 proxmox_vm_details.py -s running

# Filtrar solo VMs detenidas
python3 proxmox_vm_details.py -s stopped

# Buscar VMs por nombre (búsqueda parcial, insensible a mayúsculas)
python3 proxmox_vm_details.py -n "web"

# Mostrar información detallada de cada VM
python3 proxmox_vm_details.py -d

# Mostrar TODOS los detalles (incluyendo configuraciones raw)
python3 proxmox_vm_details.py -a

# Mostrar solo resumen tabular
python3 proxmox_vm_details.py --summary-only

# Mostrar estadísticas generales
python3 proxmox_vm_details.py --stats

# Exportar datos a JSON
python3 proxmox_vm_details.py -e

# Exportar con nombre personalizado
python3 proxmox_vm_details.py -e -o mis_vms.json

# Modo verbose (debug)
python3 proxmox_vm_details.py -v
```

### Ejemplos de uso combinado

```bash
# VMs en ejecución con detalles y exportación
python3 proxmox_vm_details.py -s running -d -e

# Buscar VMs con "prod" en el nombre y mostrar estadísticas
python3 proxmox_vm_details.py -n "prod" --stats

# Solo resumen de VMs detenidas
python3 proxmox_vm_details.py -s stopped --summary-only
```

## Información mostrada

### Resumen tabular
- Servidor y nodo
- ID y nombre de VM
- Estado (running/stopped)
- CPU (cores/sockets)
- RAM asignada
- Espacio en disco total
- Uptime (para VMs en ejecución)
- Porcentaje de CPU en uso
- Tipo de SO

### Vista detallada
- **Información básica**: Estado, tipo de SO, BIOS, agente, descripción, tags
- **CPU y memoria**: Cores, sockets, memoria asignada y uso actual
- **Discos**: Interfaces, almacenamiento, tamaños
- **Red**: Interfaces de red, modelos, bridges, direcciones MAC
- **Configuración**: Orden de arranque, tipo de máquina

### Estadísticas
- Total de VMs, ejecutándose y detenidas
- Templates
- Uso total de recursos (CPU, memoria, disco)
- Uso promedio de CPU
- Distribución por tipo de SO

## Archivo de credenciales

Usa el mismo formato YAML que `proxmox_monitor.py`:

```yaml
servers:
  proxmox1.ejemplo.com:
    username: usuario@pam
    password: contraseña
  proxmox2.ejemplo.com:
    username: usuario@pam
    password: contraseña
```

## Salida JSON

Cuando usas `-e`, el script exporta todos los datos a un archivo JSON que incluye:
- Timestamp de la exportación
- Número total de VMs
- Array completo con todos los detalles de cada VM

## Diferencias con proxmox_monitor.py

| Característica | proxmox_monitor.py | proxmox_vm_details.py |
|---|---|---|
| Enfoque | Resumen del cluster y predicción | Detalles individuales de VMs |
| Información de VMs | Básica | Completa y detallada |
| Filtros | No | Por estado y nombre |
| Configuración de red | No | Sí, completa |
| Configuración de disco | Básica | Detallada por interfaz |
| Uptime | No | Sí |
| Uso actual de recursos | No | Sí (para VMs en ejecución) |
| Templates | No detecta | Detecta y marca |
| Estadísticas por SO | No | Sí |

## Logging

El script genera logs en `proxmox_vm_details.log` con información de conexiones, errores y operaciones realizadas.

## Colores en la salida

- **Verde**: Estados positivos (running, recursos disponibles)
- **Rojo**: Estados problemáticos (stopped, recursos críticos)
- **Amarillo**: Advertencias y encabezados
- **Azul**: Información general
- **Cian**: Títulos y banners 