import math
import time
import threading

# Import provided modules
from anchor_digital_twin import AnchorZoneDigitalTwin
from elegoo_controller import ElegooTumbllerController
from astar_node import AStarNode, astar

# --- Steering Controller ---
class TumbllerSteeringController:
    def __init__(self, digital_twin: AnchorZoneDigitalTwin, ble_controller: ElegooTumbllerController,
                 grid_resolution=0.5):
        self.dt = digital_twin
        self.ble = ble_controller
        self.grid_res = grid_resolution
        self.running = False
        self.thread = None

    def _position_to_grid(self, pos):
        # Convert continuous position to discrete grid cell
        return (round(pos['x']/self.grid_res), round(pos['y']/self.grid_res))

    def _grid_to_position(self, cell):
        return {'x': cell[0]*self.grid_res, 'y': cell[1]*self.grid_res}

    def _successors(self, cell):
        # 4-connected grid
        moves = [(1,0),( -1,0),(0,1),(0,-1)]
        for dx, dy in moves:
            nbr = (cell[0]+dx, cell[1]+dy)
            cost = math.hypot(dx*self.grid_res, dy*self.grid_res)
            yield nbr, cost

    def _heuristic(self, cell, goal_cell):
        return math.hypot((cell[0]-goal_cell[0])*self.grid_res, (cell[1]-goal_cell[1])*self.grid_res)

    def plan_path(self):
        # Get current positions
        tumb_state = self.dt.get_tumbller_state()
        target_state = self.dt.get_target_person_state()
        if not tumb_state or not target_state:
            return []
        start = self._position_to_grid(tumb_state['position'])
        goal = self._position_to_grid(target_state['position'])
        path = astar(
            start,
            lambda c: c == goal,
            lambda c: self._successors(c),
            lambda c: self._heuristic(c, goal)
        )
        return path or []

    def _follow_path(self, path):
        # Send movement commands for each path segment
        for cell in path[1:]:
            pos = self._grid_to_position(cell)
            self._go_to(pos)
            time.sleep(0.1)

    def _go_to(self, target_pos):
        # Compute bearing to target
        tumb_state = self.dt.get_tumbller_state()
        if not tumb_state:
            return
        cur_pos = tumb_state['position']
        yaw = tumb_state['orientation']['yaw']
        dx = target_pos['x'] - cur_pos['x']
        dy = target_pos['y'] - cur_pos['y']
        desired_angle = math.atan2(dy, dx)
        # Compute turn angle
        angle_diff = math.atan2(math.sin(desired_angle - yaw), math.cos(desired_angle - yaw))
        # Choose left or right
        if abs(angle_diff) > 0.1:
            if angle_diff > 0:
                self.ble.schedule_coroutine(self.ble.left())
            else:
                self.ble.schedule_coroutine(self.ble.right())
            time.sleep(0.2)
        # Move forward
        self.ble.schedule_coroutine(self.ble.forward())

    def start(self, interval=0.5):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run, args=(interval,), daemon=True)
        self.thread.start()

    def _run(self, interval):
        while self.running:
            path = self.plan_path()
            if path:
                self._follow_path(path)
            time.sleep(interval)

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()

# --- Example Usage ---
if __name__ == "__main__":
    # Initialize components
    dt = AnchorZoneDigitalTwin(anchor_center=(0,0,0), zone_radius=10.0)
    bt_ctrl = ElegooTumbllerController()
    
    # Connect BLE
    import asyncio
    asyncio.run(bt_ctrl.connect())
    
    # Register entities manually or via incoming MQTT/BLE updates
    dt.register_tumbller("tumbller_01")
    dt.register_target_person("person_01")
    
    # Start steering
    steer_ctrl = TumbllerSteeringController(dt, bt_ctrl)
    steer_ctrl.start(interval=1.0)
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        steer_ctrl.stop()
        asyncio.run(bt_ctrl.disconnect())
