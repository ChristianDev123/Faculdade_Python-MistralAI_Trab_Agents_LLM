class Message:
    def __init__(self, role, content, tool_call_id=None):
        self.role = role
        self.tool_call_id = tool_call_id
        self.content = content
        
    def to_dict(self)->dict:
        response =  {
            'role':self.role,
            'content':self.content
        }
        if(self.tool_call_id): response['tool_call_id'] = self.tool_call_id
        return response