class ToolCall:
    def __init__(self, name_func, desc_func):
        self.name = name_func
        self.desc_function = desc_func
        self.props = []
        self.required = []

    def insert_prop(self, name, type, desc):
        self.props.append({
            'name': name,
            'type': type,
            'description':desc
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
                    'properties':{prop['name']:{'type':prop['type'], 'description':prop['description']} for prop in self.props},
                    'required': self.required,
                    'additionalProperties': False
                 }            
            }
        }
        return response