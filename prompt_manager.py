import os
from jinja2 import Environment, FileSystemLoader

class PromptManager:
    def __init__(self, prompt_dir="prompts"):
        self.prompt_dir = prompt_dir
        self.env = Environment(loader=FileSystemLoader(prompt_dir))
    
    def render(self, template_path, variables):
        """Render a single template file with variables."""
        template = self.env.get_template(template_path)
        return template.render(**variables)
    
    def build(self, workflow_path, variables):
        """
        Build a messages list from a workflow directory.
        
        Expects:
          - {workflow_path}/system.md  (optional)
          - {workflow_path}/user.md    (required)
        """
        messages = []
        
        # System message (optional)
        system_path = f"{workflow_path}/system.md"
        if os.path.exists(os.path.join(self.prompt_dir, system_path)):
            messages.append({
                "role": "system",
                "content": self.render(system_path, variables)
            })
        
        # User message (required)
        user_path = f"{workflow_path}/user.md"
        messages.append({
            "role": "user", 
            "content": self.render(user_path, variables)
        })
        
        return {"messages": messages}
