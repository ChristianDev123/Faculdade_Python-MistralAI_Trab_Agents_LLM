def createJsonFormat(name: str, props: list[dict]):
    properties = {}
    required = []
    
    for prop in props:
        prop_name = prop['name']
        required.append(prop_name)
        
        # Copia todas as configurações da propriedade, exceto o 'name'
        prop_def = {k: v for k, v in prop.items() if k != 'name'}
        properties[prop_name] = prop_def
        
    return {
        "type": "json_schema",
        "json_schema": {
            "name": name,
            "strict": True,
            "schema": {
                "type": "object",    
                "properties": properties,
                "additionalProperties": False,
                "required": required
            }
        }
    }