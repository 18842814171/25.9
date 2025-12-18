import ezdxf
import sys

sys.stdout.reconfigure(encoding='utf-8')
def extract_all_text(dxf_file):
    """
    提取DXF文件中所有图层的文字内容
    """
    try:
        # 打开DXF文件
        doc = ezdxf.readfile(dxf_file)
        # 选择模型空间
        msp = doc.modelspace()
        
        # 存储获取到的文本和对应的图层
        text_data = []
        
        # 遍历模型空间中的所有文本实体
        for text in msp.query('TEXT'):
            layer_name = text.dxf.layer
            text_content = text.text
            text_data.append({
                'layer': layer_name,
                'text': text_content
            })
        
            
        # 按图层分组显示
        # 使用字符串分割
        file_name_with_ext = dxf_file.split('\\')[-1]
        # 去除扩展名
        output_name = file_name_with_ext.rsplit('.', 1)[0]
          # 输出：附图8：炮眼布置及装药结构图
        layers_text = {}
        
        for item in text_data:
            layer = item['layer']
            text = item['text']
            if layer not in layers_text:
                layers_text[layer] = []
            layers_text[layer].append(text)
        with open(f"info/{output_name}--text.txt")as f:
            for layer, texts in layers_text.items():
                f.write(f"图层 '{layer}':")
                for i, text in enumerate(texts, 1):
                    f.write(f"  {i}. {text}")
                f.write('\n')
        print("全部文字已写入txt")
    except Exception as e:
        print(f"读取DXF文件时出错: {e}")
        return []

def extract_text_from_layer(dxf_file, layer_name,text_type):
    """
    提取指定图层的文字内容
    """
    try:
        # 打开DXF文件
        doc = ezdxf.readfile(dxf_file)
        # 选择模型空间
        msp = doc.modelspace()

        # 存储获取到的文本
        texts = []
        # 遍历模型空间中的所有文本实体
        for text in msp.query(text_type):
            layer_name = text.dxf.layer
            text_content = text.dxf.text  # 使用 dxf.text 替代 text
            if text_content:  # 确保文本内容不为空
                texts.append({
                    'layer': layer_name,
                    'text': text_content
                })
        file_name_with_ext = dxf_file.split('\\')[-1]
        output_name = file_name_with_ext.rsplit('.', 1)[0]
        with open(f"info/{output_name}--{layer_name}--{text_type}.txt",'w',encoding='utf-8')as f:
            f.write(f'从图层 "{layer_to_query}" 提取的文本: ')
            for item in texts:
                f.write(f"图层: {item['layer']}, 文本: {item['text']}\n")
        print("图层文字已写入txt")

    except Exception as e:
        print(f"读取DXF文件时出错: {e}")
        return []


def extract_entity_types(dxf_file):
    doc = ezdxf.readfile(dxf_file)
    msp = doc.modelspace()

    # 存储所有实体类型
    entity_types = set()

    # 遍历所有实体并统计类型
    for entity in msp:
        entity_type = entity.dxftype()
        entity_types.add(entity_type)

    print("工程图中包含的实体类型:")
    
    for idx, entity_type in enumerate(sorted(entity_types), 1):
        print(f"{idx}. {entity_type}")
    """ # 打印所有实体类型
    file_name_with_ext = dxf_file.split('\\')[-1]
    output_name = file_name_with_ext.rsplit('.', 1)[0]
    with open(f"info/{output_name}--entity_type.txt")as f:
        f.write("工程图中包含的实体类型:")
    
        for idx, entity_type in enumerate(sorted(entity_types), 1):
            f.write(f"{idx}. {entity_type}")
    print("所有实体类型已写入txt")
"""
if __name__ == '__main__':
    dxf_file_path = r"D:\大创\25.9\图纸\dxf\附图8：炮眼布置及装药结构图.dxf"
    
    # 提取所有图层的文字
    #extract_all_text(dxf_file_path)
    
    # 如果想要提取特定图层的文字，可以取消下面的注释
    layer_to_query = '排水图'  # 请替换为你要查询的图层名
    text_type='MTEXT'
    #extract_text_from_layer(dxf_file_path, layer_to_query,text_type)
    extract_entity_types(dxf_file_path)
   