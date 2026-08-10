import logging
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

class Logger:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
            cls._instance.logger = None
        return cls._instance
    
    def init(self, log_dir="logs", log_level=logging.INFO, max_bytes=10*1024*1024, backup_count=5):
        if self._initialized:
            return
        
        self.logger = logging.getLogger("solid_info")
        self.logger.setLevel(log_level)
        self.logger.propagate = False
        
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        
        log_format = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(funcName)s:%(lineno)d - %(message)s"
        )
        
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        console_handler.setFormatter(log_format)
        self.logger.addHandler(console_handler)
        
        timestamp = datetime.now().strftime("%Y%m%d")
        file_handler = RotatingFileHandler(
            os.path.join(log_dir, f"app_{timestamp}.log"),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8"
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(log_format)
        self.logger.addHandler(file_handler)
        
        self._initialized = True
    
    def debug(self, message):
        if self.logger:
            self.logger.debug(message)
    
    def info(self, message):
        if self.logger:
            self.logger.info(message)
    
    def warning(self, message):
        if self.logger:
            self.logger.warning(message)
    
    def error(self, message, exc_info=False):
        if self.logger:
            self.logger.error(message, exc_info=exc_info)
    
    def critical(self, message, exc_info=False):
        if self.logger:
            self.logger.critical(message, exc_info=exc_info)


logger = Logger()


def init_logger(log_dir="logs", log_level=logging.INFO):
    """初始化日志记录器
    
    Args:
        log_dir: 日志文件存放目录，默认"logs"
        log_level: 日志级别，默认logging.INFO
    """
    logger.init(log_dir=log_dir, log_level=log_level)


def get_logger():
    """获取日志记录器实例"""
    return logger
