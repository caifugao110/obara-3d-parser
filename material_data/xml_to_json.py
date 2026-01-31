import xml.etree.ElementTree as ET
import json
import re

# 读取XML文件，处理编码问题
xml_file = 'sldmaterials.txt'
with open(xml_file, 'r', encoding='utf-8', errors='ignore') as f:
    xml_content = f.read()

# 移除XML声明中的编码指定，让解析器自动处理
xml_content = re.sub(r'<\?xml[^>]*\?>', '<?xml version="1.0"?>', xml_content)

# 移除所有命名空间前缀
xml_content = re.sub(r'\w+:', '', xml_content)

# 解析XML
tree = ET.ElementTree(ET.fromstring(xml_content))
root = tree.getroot()

# 初始化结果字典
result = {
    'version': root.attrib.get('version', ''),
    'curves': [],
    'classifications': []
}

# 处理curves节点
curves_node = root.find('curves')
if curves_node is not None:
    curve = {
        'id': curves_node.attrib.get('id', ''),
        'points': []
    }
    for point in curves_node.findall('point'):
        curve['points'].append({
            'x': float(point.attrib.get('x', '0')),
            'y': float(point.attrib.get('y', '0'))
        })
    result['curves'].append(curve)

# 处理classification节点
for classification in root.findall('classification'):
    class_data = {
        'name': classification.attrib.get('name', ''),
        'materials': []
    }
    
    # 处理material节点
    for material in classification.findall('material'):
        mat_data = {
            'name': material.attrib.get('name', ''),
            'description': material.attrib.get('description', ''),
            'propertysource': material.attrib.get('propertysource', ''),
            'appdata': material.attrib.get('appdata', ''),
            'shaders': {},
            'swatchcolor': {
                'RGB': '',
                'optical': {}
            },
            'xhatch': {
                'name': '',
                'angle': 0.0,
                'scale': 1.0
            },
            'physicalproperties': {}
        }
        
        # 处理shaders节点
        shaders_node = material.find('shaders')
        if shaders_node is not None:
            pwshader = shaders_node.find('pwshader')
            if pwshader is not None:
                mat_data['shaders']['pwshader'] = pwshader.attrib.get('name', '')
            
            pwshader2 = shaders_node.find('pwshader2')
            if pwshader2 is not None:
                mat_data['shaders']['pwshader2'] = {
                    'name': pwshader2.attrib.get('name', ''),
                    'path': pwshader2.attrib.get('path', ''),
                    'isNewShader': pwshader2.attrib.get('isNewShader', '0')
                }
            
            cgshader = shaders_node.find('cgshader')
            if cgshader is not None:
                mat_data['shaders']['cgshader'] = cgshader.attrib.get('name', '')
            
            swtexture = shaders_node.find('swtexture')
            if swtexture is not None:
                mat_data['shaders']['swtexture'] = swtexture.attrib.get('path', '')
        
        # 处理swatchcolor节点
        swatchcolor_node = material.find('swatchcolor')
        if swatchcolor_node is not None:
            mat_data['swatchcolor']['RGB'] = swatchcolor_node.attrib.get('RGB', '')
            optical_node = swatchcolor_node.find('Optical')
            if optical_node is not None:
                mat_data['swatchcolor']['optical'] = {
                    'Ambient': float(optical_node.attrib.get('Ambient', '0')),
                    'Transparency': float(optical_node.attrib.get('Transparency', '0')),
                    'Diffuse': float(optical_node.attrib.get('Diffuse', '0')),
                    'Specularity': float(optical_node.attrib.get('Specularity', '0')),
                    'Shininess': float(optical_node.attrib.get('Shininess', '0')),
                    'Emission': float(optical_node.attrib.get('Emission', '0'))
                }
        
        # 处理xhatch节点
        xhatch_node = material.find('xhatch')
        if xhatch_node is not None:
            mat_data['xhatch']['name'] = xhatch_node.attrib.get('name', '')
            mat_data['xhatch']['angle'] = float(xhatch_node.attrib.get('angle', '0'))
            mat_data['xhatch']['scale'] = float(xhatch_node.attrib.get('scale', '1'))
        
        # 处理physicalproperties节点
        physicalproperties_node = material.find('physicalproperties')
        if physicalproperties_node is not None:
            for prop in physicalproperties_node:
                prop_name = prop.tag  # 直接使用标签名
                mat_data['physicalproperties'][prop_name] = {
                    'displayname': prop.attrib.get('displayname', ''),
                    'value': float(prop.attrib.get('value', '0')),
                    'usepropertycurve': prop.attrib.get('usepropertycurve', '0')
                }
        
        class_data['materials'].append(mat_data)
    
    result['classifications'].append(class_data)

# 写入JSON文件
with open('sldmaterials.json', 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print('转换完成！结果已保存到 sldmaterials.json')
