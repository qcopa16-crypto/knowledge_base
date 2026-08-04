import torch

# 打印PyTorch版本
print("PyTorch版本:", torch.__version__)
# 验证CUDA是否可用，输出True即为GPU版本安装成功
print("CUDA可用:", torch.cuda.is_available())
# 打印显卡名称，确认识别到你的GTX 1080
print("显卡名称:", torch.cuda.get_device_name(0))