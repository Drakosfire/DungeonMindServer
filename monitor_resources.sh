#!/bin/bash

# Simple resource monitoring script for DungeonMind development
# Run this to monitor system resources and detect potential memory leaks

echo "=== DungeonMind Resource Monitor ==="
echo "Press Ctrl+C to stop monitoring"
echo ""

while true; do
    echo "$(date '+%Y-%m-%d %H:%M:%S')"
    echo "----------------------------------------"
    
    # System load
    echo "Load Average: $(uptime | awk -F'load average:' '{print $2}')"
    
    # Memory usage
    echo "Memory Usage:"
    free -h | grep -E "Mem|Swap"
    
    # Disk usage
    echo "Disk Usage:"
    df -h . | tail -1
    
    # Top processes by memory
    echo "Top 5 Memory-Using Processes:"
    ps aux --sort=-%mem | head -6 | tail -5 | awk '{printf "%-10s %-8s %-8s %s\n", $1, $2, $3"%", $11}'
    
    # Check for runaway ripgrep processes
    RIPC=$(pgrep -c ripgrep 2>/dev/null || echo "0")
    if [ "$RIPC" -gt 5 ]; then
        echo "⚠️  WARNING: $RIPC ripgrep processes detected!"
        echo "   Consider restarting Cursor IDE"
    fi
    
    # Check for high CPU usage
    CPU_USAGE=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | cut -d'%' -f1)
    if (( $(echo "$CPU_USAGE > 80" | bc -l) )); then
        echo "⚠️  WARNING: High CPU usage: ${CPU_USAGE}%"
    fi
    
    echo ""
    echo "Press Ctrl+C to stop monitoring"
    echo ""
    
    sleep 30  # Check every 30 seconds
done 