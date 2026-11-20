# -*- coding: utf-8 -*-
"""
数据库连接配置。

改密码 / 换机器只需要动这个文件，db.py 和 init_db.py 都从这里读。
password 直接写在文件里只适合学习项目；真实项目应该放进环境变量，
并把 config.py 加入 .gitignore，避免密码随代码上传。
"""

DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "",            # 无密码就留空；有密码填在这里
    "database": "gewu",        # 不存在时 init_db.py 会自动创建
    "charset": "utf8mb4",      # 中文必须 utf8mb4，utf8 存不了 emoji
}