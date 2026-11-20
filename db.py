# -*- coding: utf-8 -*-
"""
数据库连接模块 —— Flask 与 MySQL 的"接线"层（pymysql 版）。

和 SQLite 版的三点不同：
    1. 占位符从 ? 换成 %s（pymysql 的约定）；
    2. cursor 默认返回元组，这里指定 DictCursor，
       查询结果直接就是字典，dict(row) 都可以省；
    3. MySQL 服务器可能超时断开闲置连接，
       get_db() 里 ping(reconnect=True) 自动重连，避免"第二天打开就报错"。

g / close_db / 参数化查询的原理与 SQLite 版一致，不再重复。
"""

import pymysql
from pymysql.cursors import DictCursor

from flask import g

from config import DB_CONFIG


def get_db():
    """取当前请求的连接；第一次现开，之后复用；断了自动重连。"""
    if "db" not in g:
        g.db = pymysql.connect(**DB_CONFIG, cursorclass=DictCursor)
    else:
        g.db.ping(reconnect=True)   # MySQL 等待超时把闲置连接掐掉后能自动接上
    return g.db


def close_db(_error=None):
    """请求结束时由 Flask 自动调用（app.py 里注册）。"""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def query(sql, args=(), one=False):
    """查：返回字典列表；one=True 时返回单条（没有则 None）。

    DictCursor 模式下 fetchall() 拿到的已经是 dict，直接能用。
    """
    cursor = get_db().cursor()
    cursor.execute(sql, args)
    rows = list(cursor.fetchall())
    cursor.close()
    if one:
        return rows[0] if rows else None
    return rows


def execute(sql, args=()):
    """写：INSERT / UPDATE / DELETE，写完 commit。

    与 SQLite 相同：不 commit 的写入在连接关闭时会丢。
    """
    cursor = get_db().cursor()
    cursor.execute(sql, args)
    get_db().commit()
    return cursor