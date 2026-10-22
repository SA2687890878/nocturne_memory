"""
写入小说记忆到指定数据库
用法: python write_novel_memory.py <db_path> <novel_name> <memory_type> <content_file>
"""
import sqlite3
import uuid
import sys
import json
from datetime import datetime
from pathlib import Path

def get_or_create_node(cursor, namespace, domain, path):
    """获取或创建节点"""
    # 检查路径是否已存在
    cursor.execute(
        "SELECT node_uuid FROM paths WHERE namespace=? AND domain=? AND path=?",
        (namespace, domain, path)
    )
    result = cursor.fetchone()
    if result:
        return result[0]

    # 创建新节点
    node_uuid = str(uuid.uuid4())
    now = datetime.now().isoformat()
    cursor.execute(
        "INSERT INTO nodes (uuid, created_at, last_accessed_at) VALUES (?, ?, ?)",
        (node_uuid, now, now)
    )

    # 创建路径
    cursor.execute(
        "INSERT INTO paths (namespace, domain, path, node_uuid, created_at) VALUES (?, ?, ?, ?, ?)",
        (namespace, domain, path, node_uuid, now)
    )

    return node_uuid

def create_memory_with_edge(cursor, namespace, domain, parent_path, child_path, content, priority=2, disclosure=""):
    """创建记忆并建立父子关系"""
    now = datetime.now().isoformat()

    # 获取或创建父节点
    parent_uuid = get_or_create_node(cursor, namespace, domain, parent_path)

    # 获取或创建子节点
    child_uuid = get_or_create_node(cursor, namespace, domain, child_path)

    # 创建记忆
    memory_id = cursor.execute("SELECT MAX(id) FROM memories").fetchone()[0] or 0
    memory_id += 1
    cursor.execute(
        "INSERT INTO memories (id, node_uuid, content, deprecated, created_at) VALUES (?, ?, ?, 0, ?)",
        (memory_id, child_uuid, content, now)
    )

    # 创建边（父子关系）
    cursor.execute(
        "INSERT INTO edges (parent_uuid, child_uuid, priority, disclosure, created_at) VALUES (?, ?, ?, ?, ?)",
        (parent_uuid, child_uuid, priority, disclosure, now)
    )

    # 更新搜索索引
    cursor.execute(
        """INSERT OR REPLACE INTO search_documents
           (namespace, domain, path, node_uuid, memory_id, uri, content, disclosure, search_terms, priority, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (namespace, domain, child_path, child_uuid, memory_id, f"{domain}://{child_path}", content, disclosure, child_path.split('/')[-1], priority, now)
    )

    return memory_id

def write_novel_memory(db_path, novel_config):
    """写入小说记忆"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    namespace = "default"
    domain = novel_config["domain"]

    # 写入根节点
    create_memory_with_edge(
        cursor, namespace, domain,
        f"{domain}_root",
        f"{domain}_root",
        novel_config["root_content"],
        priority=2,
        disclosure=novel_config["root_disclosure"]
    )

    # 写入角色记忆
    if "characters" in novel_config:
        create_memory_with_edge(
            cursor, namespace, domain,
            f"{domain}_root",
            f"{domain}_root/characters",
            novel_config["characters"],
            priority=0,
            disclosure=f"当需要了解{novel_config['name']}角色时"
        )

    # 写入情节记忆
    if "plot" in novel_config:
        create_memory_with_edge(
            cursor, namespace, domain,
            f"{domain}_root",
            f"{domain}_root/plot_structure",
            novel_config["plot"],
            priority=2,
            disclosure=f"当需要了解{novel_config['name']}情节结构时"
        )

    # 写入关系记忆
    if "relationships" in novel_config:
        create_memory_with_edge(
            cursor, namespace, domain,
            f"{domain}_root",
            f"{domain}_root/relationships",
            novel_config["relationships"],
            priority=1,
            disclosure=f"当需要了解{novel_config['name']}人物关系时"
        )

    # 写入文风记忆
    if "techniques" in novel_config:
        create_memory_with_edge(
            cursor, namespace, domain,
            f"{domain}_root",
            f"{domain}_root/techniques",
            novel_config["techniques"],
            priority=3,
            disclosure=f"当模仿{novel_config['name']}文风/学习对话节奏/写感官场景/续写时"
        )

    conn.commit()
    conn.close()
    print(f"✓ 已写入 {db_path}")

if __name__ == "__main__":
    # 测试用
    print("请通过团队成员调用此脚本")
