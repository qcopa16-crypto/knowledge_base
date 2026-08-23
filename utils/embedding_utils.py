from pymilvus.model.hybrid import BGEM3EmbeddingFunction
import threading
from config.embedding_config import embedding_config
from processor.import_processor.base import setup_logging

setup_logging()

# 模型单例对象，避免重复初始化
_bge_m3_ef = None

_model_lock = threading.Lock()


def get_bge_m3_ef():
    """
    获取BGE-M3模型单例对象，自动加载环境变量配置
    :return: 初始化完成的BGEM3EmbeddingFunction实例
    """
    global _bge_m3_ef
    if _bge_m3_ef is not None:
        return _bge_m3_ef

    with _model_lock:
        if _bge_m3_ef is not None:
            return _bge_m3_ef

        # 从环境变量加载配置
        model_name = embedding_config.bge_m3_path
        device = embedding_config.bge_device
        use_fp16 = embedding_config.bge_fp16

        # 如果模型没有被提前下载，会自动下载
        _bge_m3_ef = BGEM3EmbeddingFunction(
            model_name=model_name,
            device=device,
            use_fp16=use_fp16
        )
        return _bge_m3_ef


def generate_embeddings(texts):
    """
    为文本生成向量嵌入
    :param texts: 要生成嵌入的文本列表
    :return: 包含dense和sparse向量的字典
    """

    if not isinstance(texts, list):
        raise ValueError(f"texts 必须是列表，当前类型: {type(texts)}")

    clean_texts = []
    for t in texts:
        if isinstance(t, (list, tuple)):
            t = t[0] if t else ""
        if not isinstance(t, str):
            t = str(t)
        clean_texts.append(t)
    texts = clean_texts

    model = get_bge_m3_ef()

    with _model_lock:
        embeddings = model.encode_documents(texts)

    processed_sparse = []
    for i in range(len(texts)):
        sparse_indices = embeddings["sparse"].indices[
            embeddings["sparse"].indptr[i]:embeddings["sparse"].indptr[i + 1]].tolist()
        sparse_data = embeddings["sparse"].data[
            embeddings["sparse"].indptr[i]:embeddings["sparse"].indptr[i + 1]].tolist()
        sparse_dict = {k: v for k, v in zip(sparse_indices, sparse_data)}
        processed_sparse.append(sparse_dict)

    return {
        "dense": [emb.tolist() for emb in embeddings["dense"]],
        "sparse": processed_sparse
    }
