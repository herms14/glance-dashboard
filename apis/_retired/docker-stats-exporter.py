#!/usr/bin/env python3
"""
Docker Stats Prometheus Exporter
Exposes container metrics with proper container names.
Includes uptime and start time metrics.
"""

import os
import time
from datetime import datetime, timezone
import docker
from prometheus_client import start_http_server, Gauge, Info
from prometheus_client.core import GaugeMetricFamily, REGISTRY

REFRESH_INTERVAL = int(os.getenv("REFRESH_INTERVAL", "15"))
EXPORTER_PORT = int(os.getenv("EXPORTER_PORT", "9417"))

# Docker client
client = docker.from_env()

# Metrics
container_cpu_percent = Gauge(
    'docker_container_cpu_percent',
    'CPU usage percentage',
    ['name', 'id', 'image']
)

container_memory_usage = Gauge(
    'docker_container_memory_usage_bytes',
    'Memory usage in bytes',
    ['name', 'id', 'image']
)

container_memory_limit = Gauge(
    'docker_container_memory_limit_bytes',
    'Memory limit in bytes',
    ['name', 'id', 'image']
)

container_memory_percent = Gauge(
    'docker_container_memory_percent',
    'Memory usage percentage',
    ['name', 'id', 'image']
)

container_network_rx = Gauge(
    'docker_container_network_rx_bytes',
    'Network received bytes',
    ['name', 'id', 'image']
)

container_network_tx = Gauge(
    'docker_container_network_tx_bytes',
    'Network transmitted bytes',
    ['name', 'id', 'image']
)

container_status = Gauge(
    'docker_container_running',
    'Container running status (1=running, 0=stopped)',
    ['name', 'id', 'image', 'status']
)

host_total_memory = Gauge(
    'docker_host_memory_total_bytes',
    'Total host memory in bytes',
    ['host']
)

host_containers_total = Gauge(
    'docker_host_containers_total',
    'Total number of containers',
    ['host']
)

host_containers_running = Gauge(
    'docker_host_containers_running',
    'Number of running containers',
    ['host']
)

host_uptime_seconds = Gauge(
    'docker_host_uptime_seconds',
    'Host VM uptime in seconds',
    ['host']
)

container_uptime_seconds = Gauge(
    'docker_container_uptime_seconds',
    'Container uptime in seconds',
    ['name', 'id', 'image']
)

container_started_at = Gauge(
    'docker_container_started_at',
    'Container start time as Unix timestamp',
    ['name', 'id', 'image']
)


def calculate_cpu_percent(stats):
    """Calculate CPU usage percentage from Docker stats."""
    cpu_delta = stats['cpu_stats']['cpu_usage']['total_usage'] - \
                stats['precpu_stats']['cpu_usage']['total_usage']
    system_delta = stats['cpu_stats']['system_cpu_usage'] - \
                   stats['precpu_stats']['system_cpu_usage']

    if system_delta > 0 and cpu_delta > 0:
        cpu_count = stats['cpu_stats'].get('online_cpus', 1)
        return (cpu_delta / system_delta) * cpu_count * 100.0
    return 0.0


def get_network_stats(stats):
    """Extract network stats from Docker stats."""
    rx_bytes = 0
    tx_bytes = 0

    networks = stats.get('networks', {})
    for iface, data in networks.items():
        rx_bytes += data.get('rx_bytes', 0)
        tx_bytes += data.get('tx_bytes', 0)

    return rx_bytes, tx_bytes


def collect_metrics():
    """Collect metrics from all containers."""
    hostname = os.uname().nodename

    try:
        # Host info
        info = client.info()
        host_total_memory.labels(host=hostname).set(info.get('MemTotal', 0))
        host_containers_total.labels(host=hostname).set(info.get('Containers', 0))
        host_containers_running.labels(host=hostname).set(info.get('ContainersRunning', 0))

        # Host uptime from /proc/uptime
        try:
            with open('/proc/uptime', 'r') as f:
                uptime_seconds = float(f.read().split()[0])
                host_uptime_seconds.labels(host=hostname).set(uptime_seconds)
        except Exception as e:
            print(f"Error reading host uptime: {e}")

        # Container stats
        containers = client.containers.list(all=True)

        for container in containers:
            name = container.name
            cid = container.short_id
            image = container.image.tags[0] if container.image.tags else container.image.short_id
            status = container.status

            # Status metric
            is_running = 1 if status == 'running' else 0
            container_status.labels(name=name, id=cid, image=image, status=status).set(is_running)

            # Uptime metrics (only for running containers)
            if status == 'running':
                try:
                    started_at_str = container.attrs['State'].get('StartedAt', '')
                    if started_at_str:
                        # Parse ISO 8601 timestamp (e.g., "2024-12-21T08:00:00.123456789Z")
                        # Handle nanoseconds by truncating to microseconds
                        if '.' in started_at_str:
                            base, frac = started_at_str.rsplit('.', 1)
                            # Remove 'Z' and truncate to 6 digits for microseconds
                            frac = frac.rstrip('Z')[:6]
                            started_at_str = f"{base}.{frac}+00:00"
                        else:
                            started_at_str = started_at_str.replace('Z', '+00:00')

                        start_time = datetime.fromisoformat(started_at_str)
                        now = datetime.now(timezone.utc)
                        uptime = (now - start_time).total_seconds()

                        container_uptime_seconds.labels(name=name, id=cid, image=image).set(uptime)
                        container_started_at.labels(name=name, id=cid, image=image).set(start_time.timestamp())
                except Exception as e:
                    print(f"Error getting uptime for {name}: {e}")

            if status == 'running':
                try:
                    stats = container.stats(stream=False)

                    # CPU
                    cpu_pct = calculate_cpu_percent(stats)
                    container_cpu_percent.labels(name=name, id=cid, image=image).set(cpu_pct)

                    # Memory
                    mem_usage = stats['memory_stats'].get('usage', 0)
                    mem_limit = stats['memory_stats'].get('limit', 0)
                    mem_pct = (mem_usage / mem_limit * 100) if mem_limit > 0 else 0

                    container_memory_usage.labels(name=name, id=cid, image=image).set(mem_usage)
                    container_memory_limit.labels(name=name, id=cid, image=image).set(mem_limit)
                    container_memory_percent.labels(name=name, id=cid, image=image).set(mem_pct)

                    # Network
                    rx, tx = get_network_stats(stats)
                    container_network_rx.labels(name=name, id=cid, image=image).set(rx)
                    container_network_tx.labels(name=name, id=cid, image=image).set(tx)

                except Exception as e:
                    print(f"Error collecting stats for {name}: {e}")

    except Exception as e:
        print(f"Error collecting metrics: {e}")


def main():
    """Main function."""
    print(f"Starting Docker Stats Exporter on port {EXPORTER_PORT}")
    print(f"Refresh interval: {REFRESH_INTERVAL}s")

    # Start Prometheus HTTP server
    start_http_server(EXPORTER_PORT)

    while True:
        collect_metrics()
        time.sleep(REFRESH_INTERVAL)


if __name__ == '__main__':
    main()
