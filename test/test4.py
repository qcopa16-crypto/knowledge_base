from config.lm_config import lm_config



base_url = lm_config.base_url
api_key = lm_config.api_key
vl_model = lm_config.vl_model
llm_model = lm_config.llm_model
item_model = lm_config.item_model
llm_temperature = lm_config.llm_temperature

print(base_url)
print(api_key)
print(vl_model)
print(llm_model)
print(item_model)
print(llm_temperature)