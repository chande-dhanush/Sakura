import os
import sys
import asyncio
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

load_dotenv()

async def verify_lifecycle():
    print("🚀 Initializing SmartAssistant for lifecycle test...")
    from backend.sakura_assistant.core.llm import SmartAssistant
    from backend.sakura_assistant.core.graph.world_graph import get_world_graph, EntityType, EntityLifecycle
    
    assistant = SmartAssistant()
    graph = assistant.world_graph
    
    # 1. Simulate change
    test_node_name = "ShutdownTestRef"
    from backend.sakura_assistant.core.graph.world_graph import EntitySource
    node = graph.get_or_create_entity(
        type=EntityType.TOPIC, 
        name=test_node_name,
        source=EntitySource.USER_STATED
    )
    node.attributes["status"] = "verified"
    print(f"✅ Created test entity: {node.id} with lifecycle={node.lifecycle.value}")
    
    # 2. Simulate shutdown
    print("🛑 Shutting down...")
    if hasattr(assistant, 'world_graph'):
        assistant.world_graph.save()
        print("💾 World Graph saved via Assistant")
    
    # 3. Verify persistence
    graph_path = os.path.join("backend", "data", "world_graph.json")
    if os.path.exists(graph_path):
        with open(graph_path, "r", encoding="utf-8") as f:
            content = f.read()
            if test_node_name in content:
                print("✨ Persistence Verified")
            else:
                print("❌ Persistence Failed - Node not found in file")
    else:
        print(f"❌ Persistence Failed - {graph_path} not found")

if __name__ == "__main__":
    asyncio.run(verify_lifecycle())
