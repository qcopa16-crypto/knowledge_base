from pymilvus import MilvusClient, WeightedRanker, AnnSearchRequest
from config.milvus_config import milvus_config
from tool.logger import logger
import time
import threading

_milvus_client = None

_collection_load_lock = threading.Lock()


def get_milvus_client():
    """
    获取全局单例的MilvusClient对象
    :return: MilvusClient实例
    """
    global _milvus_client

    if _milvus_client is not None:
        return _milvus_client

    _milvus_client = MilvusClient(uri=milvus_config.milvus_url)

    return _milvus_client


def _ensure_collection_loaded(collection_name: str) -> bool:
    """检查集合是否加载到内存，兼容枚举/字符串两种返回格式；缺索引时自动补建"""
    client = get_milvus_client()

    def _is_loaded(state_val) -> bool:
        """统一判断是否已加载，兼容枚举对象、字符串、数字三种格式"""
        if hasattr(state_val, "name"):
            return state_val.name == "Loaded"

        if isinstance(state_val, str):
            return state_val.lower() == "loaded"

        return "loaded" in str(state_val).lower()

    def _is_missing_sparse_index_error(e: Exception) -> bool:
        """判断是否为「稀疏向量字段无索引」的报错"""
        err_msg = str(e).lower()
        return "there is no vector index on field" in err_msg and "sparse_vector" in err_msg

    # 第一层：无锁快速检查
    try:
        load_info = client.get_load_state(collection_name)
        if _is_loaded(load_info["state"]):
            return True
    except Exception as e:
        logger.warning(f"获取集合 [{collection_name}] 加载状态失败: {str(e)}")

    # 第二层：加锁后执行加载
    with _collection_load_lock:
        try:
            # 加锁后二次检查
            load_info = client.get_load_state(collection_name)
            if _is_loaded(load_info["state"]):
                return True

            logger.info(f"集合 [{collection_name}] 未加载，正在加载到内存...")
            client.load_collection(collection_name)

        except Exception as e:
            if _is_missing_sparse_index_error(e):
                logger.warning(f"集合 [{collection_name}] 缺少稀疏向量索引，正在自动补建...")
                try:
                    client.create_index(
                        collection_name=collection_name,
                        field_name="sparse_vector",
                        index_name="sparse_vector_index",
                        index_type="SPARSE_INVERTED_INDEX",
                        metric_type="IP",
                        params={
                            "inverted_index_algo": "DAAT_MAXSCORE",
                            "normalize": True,
                            "quantization": "none"
                        }
                    )
                    logger.info(f"集合 [{collection_name}] 稀疏向量索引补建完成，重试加载")
                    client.load_collection(collection_name)
                except Exception as idx_e:
                    logger.error(f"自动补建稀疏索引失败: {str(idx_e)}", exc_info=True)
                    return False
            else:
                logger.error(f"集合 [{collection_name}] 加载异常: {str(e)}", exc_info=True)
                return False

        timeout = 120
        start_time = time.time()

        while time.time() - start_time < timeout:
            current = client.get_load_state(collection_name)
            if _is_loaded(current["state"]):
                logger.info(f"集合 [{collection_name}] 加载完成")
                return True
            time.sleep(2)

        logger.error(f"集合 [{collection_name}] 加载超时({timeout}秒)")
        return False




def escape_milvus_string(value: str) -> str:
    """
    Milvus数据库过滤表达式中字符串的安全转义函数（防止解析失败）
    作用：
        转义特殊字符（反斜杠、双引号），避免Milvus解析filter时报错
    参数：
        value: 需要转义的原始字符串
    返回：
        str: 转义后的安全字符串
    """
    # 转义反斜杠（\ → \\） 双引号（" → \"） 单引号（' → \'）
    value = value.replace("\\", "\\\\").replace('"', '\\"').replace("'", "\\'")
    return value


def create_hybrid_search_requests(dense_vector, sparse_vector, dense_params=None, sparse_params=None, expr=None,
                                  limit=5):
    """
    构建Milvus混合搜索请求对象
    分别创建稠密/稀疏向量的搜索请求，用于后续混合搜索融合
    :param dense_vector: 文本生成的稠密向量
    :param sparse_vector: 文本生成的稀疏向量
    :param dense_params: 稠密向量搜索参数，默认使用余弦相似度
    :param sparse_params: 稀疏向量搜索参数，默认使用内积相似度
    :param expr: 搜索过滤表达式，用于精准筛选数据
    :param limit: 单向量搜索返回结果数量，默认5
    :return: 搜索请求列表，包含[dense_req, sparse_req]
    """
    # 稠密向量默认搜索参数：余弦相似度（COSINE），适配BGE-M3稠密向量
    if dense_params is None:
        dense_params = {"metric_type": "COSINE"}
    # 稀疏向量默认搜索参数：内积（IP），适配BGE-M3稀疏向量
    if sparse_params is None:
        sparse_params = {"metric_type": "IP"}

    # 构建稠密向量搜索请求，关联Milvus的dense_vector字段 近似最近邻（ANN）检索请求的核心类
    dense_req = AnnSearchRequest(
        data=[dense_vector],
        anns_field="dense_vector",
        param=dense_params,
        expr=expr,
        limit=limit
    )

    # 构建稀疏向量搜索请求，关联Milvus的sparse_vector字段
    sparse_req = AnnSearchRequest(
        data=[sparse_vector],
        anns_field="sparse_vector",
        param=sparse_params,
        expr=expr,
        limit=limit
    )

    return [dense_req, sparse_req]


def hybrid_search(client, collection_name, reqs, ranker_weights=(0.5, 0.5), norm_score=False, limit=5,
                  output_fields=None, search_params=None):
    """
    执行Milvus稠密+稀疏向量混合搜索
    基于WeightedRanker实现双向量搜索结果加权融合，提升检索准确性
    :param client: MilvusClient实例
    :param collection_name: 集合名称
    :param reqs: 搜索请求列表，固定为[dense_req, sparse_req]
    :param ranker_weights: 加权融合权重，默认(0.5,0.5)，依次对应稠密/稀疏向量
    :param norm_score: 是否归一化评分后再融合，避免评分量级差异导致权重失效
    :param limit: 混合搜索最终返回结果数量，默认5
    :param output_fields: 需要返回的字段列表，默认返回item_name
    :param search_params: 搜索参数，如ef/topk等，默认None
    :return: 混合搜索结果列表，搜索失败返回None
    """
    try:
        _ensure_collection_loaded(collection_name)
        # 初始化加权排名器：按权重融合稠密/稀疏向量的搜索结果
        # norm_score=True：先将两个向量评分归一化到0~1区间，再加权计算，避免一个得分特别大、另一个特别小导致权重失效。
        # 版本：V2.4
        rerank = WeightedRanker(ranker_weights[0], ranker_weights[1], norm_score=norm_score)
        # 默认返回字段：文档标识字段
        if output_fields is None:
            output_fields = ["item_name"]

        # 执行混合搜索：融合稠密+稀疏向量结果，按权重重新排序
        res = client.hybrid_search(
            collection_name=collection_name,
            reqs=reqs,
            ranker=rerank,
            limit=limit,
            output_fields=output_fields,
            search_params=search_params
        )

        logger.info(f"Milvus混合搜索完成，集合[{collection_name}]共检索到{len(res[0])}条结果")
        return res
    except Exception as e:
        logger.error(f"Milvus混合搜索执行失败，集合[{collection_name}]：{str(e)}", exc_info=True)
        return None
