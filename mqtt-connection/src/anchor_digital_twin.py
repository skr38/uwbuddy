import math
import time

class AnchorZoneDigitalTwin:
    """
    Digital twin model of the anchor zone containing all tracked entities.
    Maintains real-time state but does NOT contain control logic.
    """
    
    def __init__(self, anchor_center=(0, 0, 0), zone_radius=5.0):
        self.anchor_center = {'x': anchor_center[0], 'y': anchor_center[1], 'z': anchor_center[2]}
        self.zone_radius = zone_radius
        
        # Entity tracking
        self.entities = {}  # node_id -> entity data
        self.tumbller_id = None
        self.target_person_id = None
        
        # Tumbller specific state
        self.tumbller_orientation = {
            'yaw': 0.0,  # Current heading in radians
            'angular_velocity': 0.0,  # Current yaw rate in rad/s
            'last_update': time.time()
        }
        
        # State history for analysis
        self.position_history = {}  # node_id -> list of recent positions
        self.max_history_length = 50
        
        # Thread safety
        self._lock = threading.Lock()
    
    def register_tumbller(self, node_id):
        """Register which node ID corresponds to the Tumbller"""
        with self._lock:
            self.tumbller_id = node_id
            print(f"🤖 Registered Tumbller with node ID: {node_id}")
    
    def register_target_person(self, node_id):
        """Register which node ID corresponds to the person being followed"""
        with self._lock:
            self.target_person_id = node_id
            print(f"👤 Registered target person with node ID: {node_id}")
    
    def update_entity_position(self, node_id, position):
        """Update position of an entity (tag) in the anchor zone"""
        with self._lock:
            current_time = time.time()
            
            # Update entity data
            if node_id not in self.entities:
                self.entities[node_id] = {
                    'type': 'unknown',
                    'first_seen': current_time
                }
            
            self.entities[node_id].update({
                'position': position.copy(),
                'last_update': current_time,
                'in_zone': self._is_in_anchor_zone(position)
            })
            
            # Determine entity type
            if node_id == self.tumbller_id:
                self.entities[node_id]['type'] = 'tumbller'
            elif node_id == self.target_person_id:
                self.entities[node_id]['type'] = 'target_person'
            
            # Update position history
            if node_id not in self.position_history:
                self.position_history[node_id] = []
            
            self.position_history[node_id].append({
                'position': position.copy(),
                'timestamp': current_time
            })
            
            # Limit history length
            if len(self.position_history[node_id]) > self.max_history_length:
                self.position_history[node_id].pop(0)
    
    def update_tumbller_orientation(self, angular_velocity_data):
        """Update Tumbller's orientation based on angular velocity from Bluetooth"""
        with self._lock:
            current_time = time.time()
            dt = current_time - self.tumbller_orientation['last_update']
            
            # Integrate angular velocity to get current heading
            yaw_rate = angular_velocity_data['yaw_rate']
            self.tumbller_orientation['yaw'] += yaw_rate * dt
            
            # Normalize yaw to [-π, π]
            self.tumbller_orientation['yaw'] = math.atan2(
                math.sin(self.tumbller_orientation['yaw']),
                math.cos(self.tumbller_orientation['yaw'])
            )
            
            self.tumbller_orientation['angular_velocity'] = yaw_rate
            self.tumbller_orientation['last_update'] = current_time
    
    def _is_in_anchor_zone(self, position):
        """Check if a position is within the anchor zone"""
        dx = position['x'] - self.anchor_center['x']
        dy = position['y'] - self.anchor_center['y']
        dz = position['z'] - self.anchor_center['z']
        distance = math.sqrt(dx*dx + dy*dy + dz*dz)
        return distance <= self.zone_radius
    
    def get_entity_state(self, node_id):
        """Get current state of a specific entity"""
        with self._lock:
            return self.entities.get(node_id, None)
    
    def get_tumbller_state(self):
        """Get complete state of the Tumbller (position + orientation)"""
        with self._lock:
            if self.tumbller_id and self.tumbller_id in self.entities:
                tumbller_data = self.entities[self.tumbller_id].copy()
                tumbller_data['orientation'] = self.tumbller_orientation.copy()
                return tumbller_data
            return None
    
    def get_target_person_state(self):
        """Get current state of the target person"""
        with self._lock:
            if self.target_person_id and self.target_person_id in self.entities:
                return self.entities[self.target_person_id].copy()
            return None
    
    def get_all_entities(self):
        """Get state of all tracked entities"""
        with self._lock:
            return {
                'entities': self.entities.copy(),
                'tumbller_orientation': self.tumbller_orientation.copy(),
                'anchor_center': self.anchor_center.copy(),
                'zone_radius': self.zone_radius,
                'timestamp': time.time()
            }
    
    def get_entity_trajectory(self, node_id, time_window=10.0):
        """Get recent trajectory of an entity within time window (seconds)"""
        with self._lock:
            if node_id not in self.position_history:
                return []
            
            current_time = time.time()
            trajectory = [
                entry for entry in self.position_history[node_id]
                if current_time - entry['timestamp'] <= time_window
            ]
            return trajectory
    
    def calculate_distance_between_entities(self, node_id1, node_id2):
        """Calculate 3D distance between two entities"""
        with self._lock:
            entity1 = self.entities.get(node_id1)
            entity2 = self.entities.get(node_id2)
            
            if not entity1 or not entity2:
                return None
            
            pos1 = entity1['position']
            pos2 = entity2['position']
            
            dx = pos1['x'] - pos2['x']
            dy = pos1['y'] - pos2['y']
            dz = pos1['z'] - pos2['z']
            
            return math.sqrt(dx*dx + dy*dy + dz*dz)
    
    def get_model_summary(self):
        """Get a summary of the current model state for monitoring"""
        with self._lock:
            summary = {
                'total_entities': len(self.entities),
                'entities_in_zone': sum(1 for e in self.entities.values() if e.get('in_zone', False)),
                'tumbller_registered': self.tumbller_id is not None,
                'target_registered': self.target_person_id is not None,
                'model_timestamp': time.time()
            }
            
            if self.tumbller_id and self.target_person_id:
                distance = self.calculate_distance_between_entities(self.tumbller_id, self.target_person_id)
                summary['tumbller_to_target_distance'] = distance
            
            return summary
