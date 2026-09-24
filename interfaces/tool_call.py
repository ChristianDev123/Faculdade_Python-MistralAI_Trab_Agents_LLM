class ToolCall:
    def __init__(self, name_func, desc_func):
        self.name = name_func
        self.desc_function = desc_func
        self.props = []
        self.required = []

    def insert_prop(self, name:str, definition:dict):
        self.props.append({
            'name': name,
            'definition':definition,
        })
        self.required.append(name)

    def to_dict(self):
        response = {
            'type':'function',
            'function':{
                'name':self.name,
                'description':self.desc_function,
                'parameters':{ 
                    'type':'object',
                    'properties':{prop['name']:prop['definition'] for prop in self.props},
                    'required': self.required,
                    'additionalProperties': False
                 }            
            }
        }
        return response