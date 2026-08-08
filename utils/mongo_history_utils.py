import os
from datetime import datetime
from typing import List, Dict, Any, Optional
from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient, ASCENDING
import logging

load_dotenv()


class HistoryMongoTool:
    """
    MongoDB 历史对话记录读写工具类 (基于原生 PyMongo 实现)
    核心功能：封装MongoDB的连接、集合初始化、索引创建，为上层提供统一的数据库操作入口
    扩展功能：
    """

    def __init__(self):
        """
        类初始化方法：完成MongoDB的连接、数据库/集合获取、索引创建
        初始化失败会抛出异常并记录错误日志，确保程序感知连接问题
        """
        try:
            # 从环境变量读取MongoDB连接地址（敏感配置，不硬编码）
            self.mongo_url = os.getenv("MONGO_URL")
            # 从环境变量读取要使用的数据库名称
            self.db_name = os.getenv("MONGO_DB_NAME")

            # 创建MongoDB客户端实例，建立与数据库的连接
            self.client = MongoClient(self.mongo_url)

            # 获取指定名称的数据库对象
            self.db = self.client[self.db_name]

            # 获取对话记录的集合（相当于关系型数据库的表），集合名：chat_message
            self.chat_message = self.db["chat_message"]

            # 为chat_message集合创建复合索引，提升查询性能
            self.chat_message.create_index([("session_id", 1), ("ts", -1)])

            logging.info(f"Successfully connected to MongoDB: {self.db_name}")

        except Exception as e:
            # 捕获所有初始化异常，记录详细错误日志
            logging.error(f"Failed to connect to MongoDB: {e}")
            # 重新抛出异常，让调用方感知初始化失败，避免使用未初始化的实例
            raise


_history_mongo_tool = HistoryMongoTool()


def get_history_mongo_tool() -> HistoryMongoTool:
    """
    获取HistoryMongoTool的单例实例（懒加载模式）
    核心逻辑：全局实例为空时创建，不为空时直接返回，保证整个程序只有一个数据库连接实例
    :return: HistoryMongoTool的单例实例
    """

    global _history_mongo_tool

    if _history_mongo_tool is None:
        _history_mongo_tool = HistoryMongoTool()

    return _history_mongo_tool


def clear_history(session_id: str) -> int:
    """
    清空指定会话的所有历史对话记录
    :param session_id: 会话唯一标识，用于筛选要删除的记录
    :return: 实际删除的文档数量，删除失败返回0
    """

    mongo_tool = get_history_mongo_tool()
    try:
        result = mongo_tool.chat_message.delete_many({"session_id": session_id})

        logging.info(f"Deleted {result.deleted_count} messages for session {session_id}")

        return result.deleted_count

    except Exception as e:
        logging.error(f"Error clearing history for session {session_id}: {e}")
        # 异常时返回0，标识删除失败
        return 0


def save_chat_message(
        session_id: str,
        role: str,
        text: str,
        rewritten_query: str = "",
        item_names: List[str] = None,
        image_urls: List[str] = None,
        message_id: str = None
) -> str:
    """
    写入/更新单条会话记录到MongoDB
    支持两种模式：无message_id时新增记录，有message_id时更新已有记录
    :param session_id: 会话唯一标识，关联对话所属的会话
    :param role: 消息角色，固定值：user（用户）/assistant（助手）
    :param text: 对话核心内容，用户的提问或助手的回答
    :param rewritten_query: 重写后的查询语句（可选，用于检索增强等场景，默认空字符串）
    :param item_names: 关联的商品名称列表（可选，支持多商品，默认None）
    :param image_urls: 关联的图片URL列表（可选，默认None）
    :param message_id: 记录主键ID（可选，有值则更新，无值则新增）
    :return: 插入/更新的记录唯一标识（新增返回ObjectId字符串，更新返回传入的message_id）
    """

    ts = datetime.now().timestamp()

    document = {
        "session_id": session_id,  # 会话ID，关联维度
        "role": role,  # 消息角色
        "text": text,  # 消息内容
        "rewritten_query": rewritten_query or "",  # 问题优化后的改写，空值处理为空字符串
        "item_names": item_names,  # 关联商品名称列表
        "image_urls": image_urls,  # 关联图片URL列表
        "ts": ts  # 时间戳，排序和时间筛选维度
    }

    mongo_tool = get_history_mongo_tool()

    if message_id:
        result = mongo_tool.chat_message.update_one(
            {"_id": ObjectId(message_id)},
            {"$set": document}
        )
        return message_id
    else:
        result = mongo_tool.chat_message.insert_one(document)
        return str(result.inserted_id)


def update_message_item_names(ids: List[str], item_names: List[str]) -> int:
    """
    批量更新历史会话记录的关联商品名称
    :param ids: 要更新的记录主键ID列表（字符串类型）
    :param item_names: 要设置的新商品名称列表
    :return: 实际更新的文档数量，更新失败返回0
    """

    mongo_tool = get_history_mongo_tool()

    try:
        object_ids = [ObjectId(i) for i in ids]

        result = mongo_tool.chat_message.update_many(
            {
                "_id": {"$in": object_ids}
            },
            {"$set": {"item_names": item_names}}
        )

        logging.info(f"Updated {result.modified_count} records to item_names: {item_names}")

        return result.modified_count

    except Exception as e:
        logging.error(f"Error updating history item_names: {e}")
        # 异常时返回0，标识更新失败
        return 0


def get_recent_messages(session_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    查询指定会话的最近N条对话记录，返回原始字典格式
    结果按时间正序排列，可直接喂给LLM作为上下文
    :param session_id: 会话唯一标识，用于筛选指定会话的记录
    :param limit: 条数限制，默认返回最近10条
    :return: 对话记录列表（字典格式），查询失败返回空列表
    """

    mongo_tool = get_history_mongo_tool()
    try:
        query = {"session_id": session_id}

        cursor = mongo_tool.chat_message.find(query).sort("ts", ASCENDING).limit(limit)

        messages = list(cursor)

        return messages

    except Exception as e:
        logging.error(f"Error getting recent messages: {e}")
        # 异常时返回空列表，避免上层处理None报错
        return []


# if __name__ == "__main__":
#     # 简单测试代码：验证数据库的写入和查询功能是否正常
#     # 测试会话ID，用于标识测试的对话记录
#     sid = "000015_hybrid"
#     # 1. 写入用户消息
#     save_chat_message(sid, "user", "你好 (Hybrid)")
#     # 2. 写入助手回复
#     save_chat_message(sid, "assistant", "你好！我是基于原生 Mongo + LangChain 对象的助手。")
#     # 3. 写入带关联商品的用户消息
#     save_chat_message(sid, "user", "这个万用表怎么换电池？", item_names=["混合万用表"])
#
#     # 4. 查询指定会话的最近5条记录，验证查询功能
#     print("--- 查询 LangChain 对象记录 ---")
#     messages = get_recent_messages(sid, limit=5)
#     # 打印查询到的记录数量
#     print(f"查询到的记录数: {len(messages)}")
#     # 遍历打印每条记录的详细内容
#     for m in messages:
#         print(f" {m}  ")

if __name__ == "__main__":
    # 测试会话，用于确认商品名称是否能正确的提取
    sid = "test_session_002"
    # 1. 写入用户消息
    save_chat_message(sid, "user", "你好，有烫金机吗？")
    # 2. 写入助手回复
    save_chat_message(sid, "assistant", "你好！请问你想询问哪个型号？")
    # 3. 写入带关联商品的用户消息
    save_chat_message(sid, "user", "brother的HAK180烫金机")
    save_chat_message(sid, "assistant", "有的")
