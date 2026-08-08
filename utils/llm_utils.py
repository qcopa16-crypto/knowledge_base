from langchain_openai import ChatOpenAI

from config.lm_config import lm_config

_llm_client_cache = {}


def get_llm_client(model: str | None = None, json_model: bool = False):
    m = model or lm_config.llm_model

    key = (m, json_model)

    if key in _llm_client_cache:
        return _llm_client_cache[key]

    llm_kwargs = {
        "model": m,
        "api_key": lm_config.api_key,
        "base_url": lm_config.base_url,
        "temperature": lm_config.llm_temperature
    }

    # JSON 模式下追加响应格式约束
    if json_model:
        llm_kwargs["model_kwargs"] = {
            "response_format": {"type": "json_object"}
        }

    client = ChatOpenAI(**llm_kwargs)

    _llm_client_cache[key] = client

    return client


if __name__ == "__main__":
    client = get_llm_client()
    res = client.invoke("你好")

    print(res)
