import threading
import time

class BluetoothOrientationReceiver:
    """Handles Bluetooth communication to receive Tumbller angular velocity"""
    def __init__(self):
        self._orientation_callback = None
        self.is_running = False
        
    def set_orientation_callback(self, callback):
        """Register callback to receive angular velocity data"""
        self._orientation_callback = callback
    
    def start(self):
        """Start Bluetooth listener (placeholder implementation)"""
        self.is_running = True
        # In real implementation, this would handle Bluetooth connection
        print("🔵 Bluetooth orientation receiver started")
        
        # Simulate receiving angular velocity data
        threading.Thread(target=self._simulate_angular_velocity, daemon=True).start()
    
    def _simulate_angular_velocity(self):
        """Placeholder for actual Bluetooth data reception"""
        import random
        while self.is_running:
            # Simulate angular velocity data (rad/s around z-axis)
            angular_velocity = {
                'yaw_rate': random.uniform(-0.5, 0.5),  # rad/s
                'timestamp': time.time()
            }
            if self._orientation_callback:
                self._orientation_callback(angular_velocity)
            time.sleep(0.1)  # 10Hz update rate
