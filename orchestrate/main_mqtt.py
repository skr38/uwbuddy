from orchestrate.location_mqtt import LocationMQTT

from .anchor_digital_twin import AnchorZoneDigitalTwin
from .bluetooth_orientation_receiver import BluetoothOrientationReceiver
import time

# Global digital twin instance
digital_twin = AnchorZoneDigitalTwin()
bluetooth_receiver = BluetoothOrientationReceiver()

def process_position(node_id, pos):
    """Process incoming position data and update the digital twin"""
    x, y, z = pos["x"], pos["y"], pos["z"]
    print(f"📍 Node {node_id}: x={x:.4f}, y={y:.4f}, z={z:.4f}")
    
    # Update the digital twin model
    digital_twin.update_entity_position(node_id, pos)
    
    # Print model summary every few updates
    if hash(node_id) % 10 == 0:  # Print summary occasionally
        summary_ = digital_twin.get_model_summary()
        print(f"🗺️  Model Summary: {summary_['total_entities']} entities, "
              f"{summary_:['entities_in_zone']} in zone")

def process_orientation(angular_velocity_data):
    """Process incoming angular velocity data from Bluetooth"""
    yaw_rate = angular_velocity_data['yaw_rate']
    print(f"🧭 Tumbller angular velocity: {yaw_rate:.3f} rad/s")
    
    # Update the digital twin model
    digital_twin.update_tumbller_orientation(angular_velocity_data)


# Configuration
BROKER = "10.19.71.5"
PORT = 1883
TOPIC = "dwm/node/+/uplink/location"
TUMBLLER_NODE_ID = "4c87"
PERSON_NODE_ID = "0cad"

if __name__ == "__main__":
    print("🗺️  Starting Anchor Zone Digital Twin...")
    
    # Configure entity IDs (you'll need to set these based on your actual tags)
    digital_twin.register_tumbller(TUMBLLER_NODE_ID)  # Replace with actual Tumbller node ID
    digital_twin.register_target_person(PERSON_NODE_ID)  # Replace with actual person's tag ID
    
    # Start MQTT for position data
    mqtt_client = LocationMQTT(BROKER, PORT, TOPIC)
    mqtt_client.set_location_callback(process_position)
    mqtt_client.start(BROKER, PORT)
    
    # Start Bluetooth for orientation data
    bluetooth_receiver.set_orientation_callback(process_orientation)
    bluetooth_receiver.start()
    
    print(f"   Anchor zone center: {digital_twin.anchor_center}")
    print(f"   Zone radius: {digital_twin.zone_radius}m")
    print("   Ready to receive UWB position and Bluetooth orientation data...")
    print("   The steering logic can now query the model for real-time state!")
    
    try:
        while True:
            time.sleep(5)
            # Periodically show model state
            summary = digital_twin.get_model_summary()
            print(f"📊 {summary}")
    except KeyboardInterrupt:
        print("Shutting down Digital Twin Model")
