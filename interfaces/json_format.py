def createJsonFormat(name:str, props:list[dict]):
    json_format = {
        "type": "json_schema",
        "json_schema": {
            "name": name,
            "strict": True,
            "schema": {
                "type": "object",    
                "properties":{},
                "additionalProperties": False
            }
        }
    }
    prop_names = []
    for prop in props:
        prop_name = prop['name']
        prop_names.append(prop_name)
        prop_names_restricts = list(filter(lambda x: x != 'name', prop.keys()))
        json_format['json_schema']['schema']['properties'][prop_name] = {
            prop_name_restrict:prop[prop_name_restrict] 
            for prop_name_restrict in prop_names_restricts
        }
    json_format['json_schema']['schema']['required'] = prop_names
    return json_format