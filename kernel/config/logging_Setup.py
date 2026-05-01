from av.logging import INFO
import sys
from loguru import logger

def setup_logging():
    """
    对logger进行设置
    """
    logger.remove()
    # 标准输出
    logger.add(
        sys.stdout,
        colorize=True,
        format=
        "<green>{time:HH:mm:ss}</green> | " 
        "<level>{level: <8}</level> | "
        "<cyan>{module}</cyan>:<cyan>{function}</cyan> - {message}",
        level="WARNING"
    )

    # 日志文件
    logger.add(
    "logs/server.log",
    rotation="12:00",      # 每天中午 12 点定时切分文件
    retention="1 week",    # 保留一周
    serialize=False,      
    encoding="utf-8",      # 加上编码，防止中文乱码
    enqueue=True
)
