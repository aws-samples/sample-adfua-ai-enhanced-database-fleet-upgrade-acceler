import logging
from logging.handlers import RotatingFileHandler
import os
from datetime import datetime

class CustomLogger:
    def __init__(
        self,
        log_directory='logs',
        log_level=logging.INFO,
        max_bytes=10485760,  # 10MB
        backup_count=5,
        log_format='%(asctime)s [%(levelname)s] %(filename)s - %(message)s',
        # log_format='%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d - %(message)s'
        instance_name=None
    ):
        # Create logs directory if it doesn't exist
        if not os.path.exists(log_directory):
            os.makedirs(log_directory)

        # Create log filename
        # self.log_filename = os.path.join(
        #     log_directory,
        #     f'application_{datetime.now().strftime("%Y%m%d")}.log'
        # )
        if instance_name is None:
            instance_name=datetime.now().strftime("%Y%m%d%H%M%S")

        self.log_filename = os.path.join(
            log_directory,
            f'{instance_name}.log'
        )

        # Create logger
        self.logger = logging.getLogger(instance_name)
        self.logger.setLevel(log_level)

        # Create formatter
        formatter = logging.Formatter(log_format)

        # Create rotating file handler
        file_handler = RotatingFileHandler(
            self.log_filename,
            maxBytes=max_bytes,
            backupCount=backup_count
        )
        
        if self.logger.handlers:
            for handler in self.logger.handlers[:]:
                self.logger.removeHandler(handler)

        file_handler.setFormatter(formatter)

        # Create console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)

        # Add handlers to logger
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)

    def get_logger(self):
        return self.logger
