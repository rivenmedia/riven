import os
import uuid
import platform
import httpx
import asyncio
from pathlib import Path
from fastapi import FastAPI
import logging
from datetime import datetime, timezone
import threading
import time

from program.utils import data_dir_path

class Telemetry:
    """Telemetry class to report application events to a server."""
    def __init__(self, app: FastAPI, reporting_url: str, app_version: str, 
                 heartbeat_interval_minutes=60):
        self.app = app
        self.reporting_url = reporting_url
        self.app_version = app_version
        self.heartbeat_interval = heartbeat_interval_minutes * 60  # Convert to seconds
        self.deployment_id_filename = os.environ.get("DEPLOYMENT_ID_FILENAME", "deployment_id")
        self.deployment_id_file = data_dir_path / self.deployment_id_filename
        self.deployment_id = self._get_deployment_id()

        # Add startup event to report deployment
        @app.on_event("startup")
        async def startup_report():
            await self.report_startup()
            # Start heartbeat in background
            self._start_heartbeat_thread()
        
        # Add shutdown event
        @app.on_event("shutdown")
        async def shutdown_report():
            await self.report_shutdown()
    
    def _get_deployment_id(self):
        """Generate or retrieve a unique deployment ID"""
        id_file = Path(self.deployment_id_file)
        
        if id_file.exists():
            return id_file.read_text().strip()
        
        # Generate new ID
        new_id = str(uuid.uuid4())
        
        try:
            # Try to persist it
            os.makedirs(id_file.parent, exist_ok=True)
            id_file.write_text(new_id)
        except:
            # If we can't write, just use in-memory ID
            pass
            
        return new_id
    
    async def report_startup(self):
        """Report application startup"""
        system_info = {
            "os": platform.system(),
            "python_version": platform.python_version(),
            "deployment_id": self.deployment_id,
            "app_version": self.app_version,
            "docker": self._is_docker_environment(),
            "timestamp": self._get_utc_now(),
            "event_type": "startup"
        }
        
        await self._send_report(system_info)
    
    async def report_heartbeat(self):
        """Report application heartbeat"""
        heartbeat_info = {
            "deployment_id": self.deployment_id,
            "app_version": self.app_version,
            "timestamp": self._get_utc_now(),
            "event_type": "heartbeat"
        }
        
        await self._send_report(heartbeat_info)
    
    async def report_shutdown(self):
        """Report application shutdown"""
        shutdown_info = {
            "deployment_id": self.deployment_id,
            "app_version": self.app_version,
            "timestamp": self._get_utc_now(),
            "event_type": "shutdown"
        }
        
        await self._send_report(shutdown_info)
    
    def _is_docker_environment(self):
        """Check if running in Docker"""
        return os.path.exists('/.dockerenv') or os.path.isfile('/proc/self/cgroup') and any('docker' in line for line in open('/proc/self/cgroup'))
    
    def _get_utc_now(self):
        """Get current UTC time as ISO string"""
        return datetime.now(timezone.utc).isoformat()
    
    async def _send_report(self, data):
        """Send report to server"""
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                await client.post(self.reporting_url, json=data)
        except Exception as e:
            # Don't let telemetry errors impact application
            logging.warning(f"Telemetry error: {e}")
    
    def _heartbeat_worker(self):
        """Worker function for heartbeat thread"""
        while True:
            try:
                # Create an event loop for the thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                # Send heartbeat
                loop.run_until_complete(self.report_heartbeat())
                
                # Close the loop
                loop.close()
            except Exception as e:
                logging.warning(f"Heartbeat error: {e}")
            
            # Sleep until next heartbeat
            time.sleep(self.heartbeat_interval)
    
    def _start_heartbeat_thread(self):
        """Start a background thread for heartbeats"""
        thread = threading.Thread(target=self._heartbeat_worker, daemon=True)
        thread.start()