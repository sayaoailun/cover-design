#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置文件验证工具
检查 config.json 是否有效
"""

import json
from pathlib import Path

def verify_config(config_path):
    """验证 config.json 文件"""
    
    print("=" * 60)
    print(f"验证配置文件: {config_path}")
    print("=" * 60)
    
    # 检查文件是否存在
    if not Path(config_path).exists():
        print("❌ 错误：文件不存在！")
        return False
    
    # 尝试读取和解析 JSON
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        print("✅ JSON 格式正确！")
    except json.JSONDecodeError as e:
        print(f"❌ JSON 解析错误：")
        print(f"   位置：第 {e.lineno} 行，第 {e.colno} 列")
        print(f"   错误：{e.msg}")
        
        # 显示出错行
        with open(config_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            if e.lineno <= len(lines):
                error_line = lines[e.lineno - 1]
                print(f"\n   出错行内容：")
                print(f"   {error_line.rstrip()}")
                print(f"   {' ' * (e.colno - 1)}^")
        
        return False
    except Exception as e:
        print(f"❌ 读取文件错误：{str(e)}")
        return False
    
    # 验证必须的 key
    print("\n检查必要的配置项...")
    required_keys = {
        "canvas": ["width", "height"],
        "paths": ["excel_file", "cover_dir", "output_dir"],
        "shadow": ["enabled", "blur", "opacity"],
        "text": ["title", "subtitle"],
    }
    
    all_valid = True
    for section, keys in required_keys.items():
        if section not in config:
            print(f"⚠️  缺失部分：{section}")
            all_valid = False
        else:
            for key in keys:
                if key not in config[section]:
                    print(f"⚠️  缺失项：{section}.{key}")
                    all_valid = False
            
    if all_valid:
        print("✅ 所有必要项都存在")
    
    # 显示阴影配置
    print("\n阴影配置详情：")
    if "shadow" in config:
        shadow = config["shadow"]
        for key, value in shadow.items():
            print(f"  {key}: {value}")
    
    print("\n✅ 配置文件验证完成！")
    return True


if __name__ == "__main__":
    # 检查当前目录下的 config.json
    config_path = Path(__file__).parent / "config.json"
    verify_config(config_path)
