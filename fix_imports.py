import os

def replace_in_file(filepath, replacements):
    with open(filepath, 'r') as f:
        content = f.read()
    
    new_content = content
    for old, new in replacements.items():
        new_content = new_content.replace(old, new)
        
    if new_content != content:
        with open(filepath, 'w') as f:
            f.write(new_content)
        print(f"Updated {filepath}")

# API routes
routes_dir = "agent_system/api/routes"
for file in os.listdir(routes_dir):
    if file.endswith('.py'):
        replace_in_file(os.path.join(routes_dir, file), {
            "from ...core": "from agent_system.core"
        })

# Core files
core_dir = "agent_system/core"
for file in os.listdir(core_dir):
    if file.endswith('.py'):
        replace_in_file(os.path.join(core_dir, file), {
            "from .": "from agent_system.core."
        })
        
# Connectors
connectors_dir = "agent_system/core/connectors"
for file in os.listdir(connectors_dir):
    if file.endswith('.py'):
        replace_in_file(os.path.join(connectors_dir, file), {
            "from .": "from agent_system.core.connectors."
        })

# Auth
auth_dir = "agent_system/core/auth"
for file in os.listdir(auth_dir):
    if file.endswith('.py'):
        replace_in_file(os.path.join(auth_dir, file), {
            "from .": "from agent_system.core.auth."
        })
