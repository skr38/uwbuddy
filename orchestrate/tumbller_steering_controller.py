import math
import time
import threading

class TumbllerSteeringController:
    """
    Intelligente Steuerungslogik für den Tumbller mit Richtungsberechnung
    """
    
    def __init__(self, digital_twin, message_queue):
        self.dt = digital_twin
        self.message_queue = message_queue  # Direkte Referenz zur Message Queue
        self.running = False
        self.thread = None
        
        # Steuerungsparameter
        self.min_distance = 0.8
        self.max_distance = 2.0
        self.angle_threshold = 0.3
        self.command_interval = 2.0
        self.last_command_time = 0
        
        print(f"Steering Controller initialisiert mit:")
        print(f"  Digital Twin: {id(self.dt)}")
        print(f"  Message Queue: {id(self.message_queue)}")
        
    def calculate_steering_command(self):
        """Berechnet optimalen Steuerungsbefehl"""
        current_time = time.time()
        
        # Rate-Limiting
        if current_time - self.last_command_time < self.command_interval:
            return None, "rate_limited"
        
        # Hole Positionen
        tumbller_state = self.dt.get_entity_state("4c87")
        person_state = self.dt.get_entity_state("0cad")
        
        if not (tumbller_state and person_state and 
                'position' in tumbller_state and 'position' in person_state):
            return None, "missing_positions"
        
        tumbller_pos = tumbller_state['position']
        target_pos = person_state['position']
        
        # Distanz und Winkel berechnen
        dx = target_pos['x'] - tumbller_pos['x']
        dy = target_pos['y'] - tumbller_pos['y']
        distance = math.sqrt(dx*dx + dy*dy)
        target_angle = math.atan2(dy, dx)
        
        # Aktuelle Orientierung
        tumbller_full_state = self.dt.get_tumbller_state()
        if tumbller_full_state and 'orientation' in tumbller_full_state:
            current_yaw = tumbller_full_state['orientation']['yaw']
        else:
            current_yaw = 0.0
        
        # Winkeldifferenz
        angle_diff = self._normalize_angle(target_angle - current_yaw)
        
        # Entscheidung
        command, reason = self._decide_action(distance, angle_diff)
        
        if command:
            self.last_command_time = current_time
            
        return command, reason
    
    def _normalize_angle(self, angle):
        return math.atan2(math.sin(angle), math.cos(angle))
    
    def _decide_action(self, distance, angle_diff):
        if distance < self.min_distance:
            return "s", f"zu_nah_{distance:.1f}m"
        
        if distance > self.max_distance:
            if abs(angle_diff) > self.angle_threshold:
                if angle_diff > 0:
                    return "l", f"links_drehen_{math.degrees(angle_diff):.0f}grad"
                else:
                    return "i", f"rechts_drehen_{math.degrees(abs(angle_diff)):.0f}grad"
            else:
                return "f", f"folgen_{distance:.1f}m"
        
        return "s", f"perfekte_distanz_{distance:.1f}m"
    
    def start(self, interval=1.0):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run, args=(interval,), daemon=True)
        self.thread.start()
        print("Tumbller Steering Controller gestartet")
    
    def _send_ble_command(self, command, reason):
        """Sendet BLE-Befehl über die Message Queue"""
        try:
            self.message_queue.put(("robot_command", "ble", {
                "command": command,
                "reason": reason
            }))
            return True
        except Exception as e:
            print(f"Fehler beim Senden des Steering-Befehls: {e}")
            return False
    
    def _run(self, interval):
        while self.running:
            try:
                command, reason = self.calculate_steering_command()
                
                if command and reason not in ["rate_limited", "missing_positions"]:
                    # Debug Info
                    tumbller_state = self.dt.get_entity_state("4c87")
                    person_state = self.dt.get_entity_state("0cad")
                    
                    if tumbller_state and person_state:
                        tpos = tumbller_state['position']
                        ppos = person_state['position']
                        dx = ppos['x'] - tpos['x']
                        dy = ppos['y'] - tpos['y']
                        distance = math.sqrt(dx*dx + dy*dy)
                        target_angle = math.atan2(dy, dx)
                        
                        print(f"Smart Steering: Distanz {distance:.2f}m, "
                              f"Zielrichtung {math.degrees(target_angle):.0f}°")
                    
                    # Action Namen
                    action_names = {
                        'f': 'VORWÄRTS',
                        's': 'STOPPEN',
                        'l': 'LINKS DREHEN',
                        'i': 'RECHTS DREHEN'
                    }
                    action_name = action_names.get(command, f'UNKNOWN({command})')
                    print(f"Steering Entscheidung: {action_name} ({reason})")
                    
                    # Befehl über Message Queue senden
                    success = self._send_ble_command(command, reason)
                    if not success:
                        print("Warnung: Konnte Steering-Befehl nicht senden")
                
            except Exception as e:
                print(f"Fehler im Steering Controller: {e}")
            
            time.sleep(interval)
    
    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()
        print("Tumbller Steering Controller gestoppt")
