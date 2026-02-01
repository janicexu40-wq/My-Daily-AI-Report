#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
阿里云盘自动上传工具
使用 aligo 库（阿里云盘官方Python SDK）
"""

import os
import sys
from pathlib import Path
from datetime import datetime

try:
    from aligo import Aligo
except ImportError:
    print("⚠️  正在安装 aligo 库...")
    os.system("pip install aligo --break-system-packages")
    from aligo import Aligo


def upload_to_aliyunpan(
    refresh_token: str,
    local_file_path: str,
    remote_folder: str = "/晨间情报"
) -> bool:
    """
    上传文件到阿里云盘
    
    Args:
        refresh_token: 阿里云盘 refresh_token
        local_file_path: 本地文件路径
        remote_folder: 云盘目标文件夹（默认 /晨间情报）
    
    Returns:
        bool: 上传成功返回 True，失败返回 False
    """
    try:
        print(f"☁️  开始上传到阿里云盘...")
        print(f"  本地文件: {local_file_path}")
        print(f"  目标文件夹: {remote_folder}")
        
        # 检查本地文件是否存在
        if not os.path.exists(local_file_path):
            print(f"❌ 本地文件不存在: {local_file_path}")
            return False
        
        file_size_mb = os.path.getsize(local_file_path) / (1024 * 1024)
        print(f"  文件大小: {file_size_mb:.2f} MB")
        
        # 初始化阿里云盘客户端
        print(f"  正在连接阿里云盘...")
        ali = Aligo(refresh_token=refresh_token)
        
        # 获取用户信息（验证 token 有效性）
        user = ali.get_user()
        if user:
            print(f"  ✓ 已登录: {user.nick_name}")
        else:
            print(f"❌ Token 无效或已过期")
            return False
        
        # 获取或创建目标文件夹
        print(f"  正在检查目标文件夹...")
        folder = ali.get_folder_by_path(remote_folder)
        
        if not folder:
            print(f"  文件夹不存在，正在创建: {remote_folder}")
            folder = ali.create_folder(remote_folder)
            if folder:
                print(f"  ✓ 文件夹创建成功")
            else:
                print(f"❌ 文件夹创建失败")
                return False
        else:
            print(f"  ✓ 文件夹已存在")
        
        # 上传文件
        print(f"  开始上传...")
        file_name = Path(local_file_path).name
        
        result = ali.upload_file(
            file_path=local_file_path,
            parent_file_id=folder.file_id,
            name=file_name,
            check_name_mode='overwrite'  # 同名文件覆盖
        )
        
        if result:
            print(f"✅ 上传成功!")
            print(f"  文件名: {file_name}")
            print(f"  文件ID: {result.file_id}")
            print(f"  云盘路径: {remote_folder}/{file_name}")
            return True
        else:
            print(f"❌ 上传失败")
            return False
            
    except Exception as e:
        print(f"❌ 上传出错: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主函数"""
    print("=" * 60)
    print("📤 阿里云盘自动上传工具")
    print(f"⏰ 运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print()
    
    # 从环境变量获取配置
    refresh_token = os.getenv('ALIYUN_REFRESH_TOKEN')
    
    # 支持从环境变量或参数获取文件路径
    audio_file = os.getenv('AUDIO_FILE')
    if not audio_file:
        # 如果没有环境变量，尝试找最新的音频文件
        date_str = datetime.now().strftime('%Y%m%d')
        audio_file = f'output/briefing_{date_str}.mp3'
    
    # 验证必需参数
    if not refresh_token:
        print("❌ 错误: 未配置 ALIYUN_REFRESH_TOKEN 环境变量")
        print("请在 GitHub Secrets 中添加此密钥")
        sys.exit(1)
    
    if not audio_file:
        print("❌ 错误: 未指定音频文件路径")
        sys.exit(1)
    
    print(f"配置信息:")
    print(f"  Token: {refresh_token[:20]}... (已隐藏)")
    print(f"  文件: {audio_file}")
    print()
    
    # 执行上传
    success = upload_to_aliyunpan(
        refresh_token=refresh_token,
        local_file_path=audio_file,
        remote_folder="/晨间情报"
    )
    
    print()
    print("=" * 60)
    if success:
        print("✅ 任务完成")
    else:
        print("❌ 任务失败")
    print("=" * 60)
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
