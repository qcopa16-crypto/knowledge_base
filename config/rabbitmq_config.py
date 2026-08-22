"""RabbitMQ / Celery 配置（dataclass + dotenv，与现有 config 风格一致）"""
from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()


@dataclass
class RabbitMQConfig:
    host: str
    port: int
    user: str
    password: str
    vhost: str

    @property
    def broker_url(self) -> str:
        """返回 amqp:// 连接串（供 Celery broker 使用）"""
        return os.getenv(
            "CELERY_BROKER_URL",
            f"amqp://{self.user}:{self.password}@{self.host}:{self.port}/{self.vhost}",
        )


rabbitmq_config = RabbitMQConfig(
    host=os.getenv("RABBITMQ_HOST", "localhost"),
    port=int(os.getenv("RABBITMQ_PORT", "5672")),
    user=os.getenv("RABBITMQ_USER", "guest"),
    password=os.getenv("RABBITMQ_PASSWORD", "guest"),
    vhost=os.getenv("RABBITMQ_VHOST", "/"),
)


@dataclass
class CeleryConfig:
    broker_url: str
    result_backend: str
    result_queue: str


celery_config = CeleryConfig(
    broker_url=os.getenv(
        "CELERY_BROKER_URL",
        rabbitmq_config.broker_url,
    ),
    result_backend=os.getenv("CELERY_RESULT_BACKEND", ""),
    result_queue=os.getenv("CELERY_RESULT_QUEUE", "kb_rag_result"),
)
