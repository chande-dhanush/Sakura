import os
import json
import time
from sakura_assistant.core.identity_manager import get_identity_manager, get_event_bus

def test_event_bus_sync():
    print(" Starting EventBus Sync Test...")
    
    im = get_identity_manager()
    bus = get_event_bus()
    
    # 1. Subscribe to changes
    received_events = []
    def on_identity_change(data):
        print(f" [Listener] Received identity update: {data['name']}")
        received_events.append(data)
    
    bus.subscribe("identity:changed", on_identity_change)
    
    # 2. Update via manager
    print(" Updating identity to 'Test User'...")
    im.update_and_save({"name": "Test User", "location": "Test Lab"})
    
    # 3. Verify event received
    if received_events and received_events[-1]["name"] == "Test User":
        print(" EventBus propagated update correctly!")
    else:
        print(" EventBus failed to propagate update.")
    
    # 4. Verify loop-back (Manual file edit + refresh)
    print(" Manually editing file to 'Hacker'...")
    path = im._get_settings_path()
    with open(path, 'r') as f:
        data = json.load(f)
    data["user_name"] = "Hacker"
    with open(path, 'w') as f:
        json.dump(data, f)
        
    print(" Calling refresh()...")
    im.refresh()
    
    if received_events and received_events[-1]["name"] == "Hacker":
         print(" Manual refresh propagated update correctly!")
    else:
         print(f" Manual refresh failed. Last event: {received_events[-1]['name']}")

if __name__ == "__main__":
    test_event_bus_sync()
