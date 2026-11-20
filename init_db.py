# -*- coding: utf-8 -*-
"""
初始化 MySQL 数据库：python init_db.py

做四件事：
    1. 连接 MySQL（不带库名），CREATE DATABASE IF NOT EXISTS gewu
    2. 建四张表（utf8mb4，中文与 emoji 都能存）
    3. 灌入 sample_data.py 的初始数据
    4. 创建演示账号

与 SQLite 版的两个关键差异：
    1. 建库和建表分开：pymysql 连接时必须已经指定库，所以先空连建库，
       再带着 database=gewu 重连一次建表。
    2. MySQL 的 TEXT 每行最多 65535 字节，文章正文 blocks 存 JSON 可能逼近，
       统一用 MEDIUMTEXT（16MB）省心。
    3. 列名加了反引号：date / year / time 这些词同时是 MySQL 的类型名，
       加反引号最保险，也是写 MySQL 的好习惯。

重跑本脚本 = 数据全部重置（DROP TABLE）。真实项目用迁移工具做增量变更。
"""

import json

import pymysql

from werkzeug.security import generate_password_hash

from config import DB_CONFIG
from sample_data import ARTICLES, BOOKS, COMMENTS, RELATED_MAP, BOOK_DETAILS

# 第一步：不带库名连上 MySQL，把库建出来
conn = pymysql.connect(host=DB_CONFIG["host"], port=DB_CONFIG["port"],
                       user=DB_CONFIG["user"], password=DB_CONFIG["password"],
                       charset=DB_CONFIG["charset"])
with conn.cursor() as c:
    c.execute("CREATE DATABASE IF NOT EXISTS `gewu`"
              " DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
conn.close()
print("数据库 gewu 就绪（已存在则跳过创建）")

# 第二步：带库名重连，建表 + 灌数据
conn = pymysql.connect(**DB_CONFIG)
cur = conn.cursor()

DDL = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id            INT AUTO_INCREMENT PRIMARY KEY,
        email         VARCHAR(120) NOT NULL UNIQUE,
        nickname      VARCHAR(50)  NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS articles (
        slug      VARCHAR(80)  PRIMARY KEY,     -- slug 当主键：URL 里用它，必须唯一
        cat       VARCHAR(20)  NOT NULL,
        cat_key   VARCHAR(20)  NOT NULL,
        title     VARCHAR(200) NOT NULL,
        dek       VARCHAR(500),
        excerpt   VARCHAR(500),
        author    VARCHAR(50),
        role      VARCHAR(50),
        `date`    VARCHAR(20),                  -- 'YYYY-MM-DD'，文本排序即时间排序
        read_time VARCHAR(20),
        art       VARCHAR(20),
        seed      INT DEFAULT 3,
        featured  TINYINT DEFAULT 0,            -- 1 = 首页主推
        tags      MEDIUMTEXT,                   -- JSON 数组
        blocks    MEDIUMTEXT                    -- JSON 数组，正文块
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS books (
        id        INT AUTO_INCREMENT PRIMARY KEY,
        title     VARCHAR(200) NOT NULL,
        author    VARCHAR(100),
        `year`    VARCHAR(10),
        tag       VARCHAR(50),
        cat       VARCHAR(20),
        level     VARCHAR(10),
        tone      VARCHAR(20),
        book_desc VARCHAR(500),
        why       VARCHAR(300),
        related_slug VARCHAR(120),             -- 对应站内文章 slug；没有对应就留 NULL
        pub       VARCHAR(120),                -- 出版信息（整理自公开资料）
        intro     TEXT,                        -- 内容概述
        structure MEDIUMTEXT,                  -- JSON 数组：全书脉络
        highlights MEDIUMTEXT,                 -- JSON 数组：核心看点
        read_tip  VARCHAR(300)                 -- 读法建议
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS comments (
        id           INT AUTO_INCREMENT PRIMARY KEY,
        article_slug VARCHAR(80)  NOT NULL,
        name         VARCHAR(50)  NOT NULL,
        initial      VARCHAR(10),
        `time`       VARCHAR(20),
        stars        INT,
        text         MEDIUMTEXT NOT NULL,
        section      VARCHAR(80),
        email        VARCHAR(120)                -- 演示简化；真实项目应为 user_id
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
]
for ddl in DDL:
    cur.execute(ddl)
print("已建表 users / articles / books / comments")

# 灌数据前先清空：保证重跑脚本结果一致（幂等）
for t in ("comments", "books", "articles", "users"):
    cur.execute("DELETE FROM `" + t + "`")

# ---------- 文章 ----------
cur.executemany(
    "INSERT INTO articles (slug, cat, cat_key, title, dek, excerpt, author, role,"
    " `date`, read_time, art, seed, featured, tags, blocks)"
    " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
    [
        (a["slug"], a["cat"], a["cat_key"], a["title"], a["dek"], a["excerpt"],
         a["author"], a["role"], a["date"], a["read"], a["art"], a["seed"],
         1 if a.get("featured") else 0,
         json.dumps(a["tags"], ensure_ascii=False),
         json.dumps(a["blocks"], ensure_ascii=False))
        for a in ARTICLES
    ],
)
print("articles:", len(ARTICLES), "篇")

# ---------- 书目 ----------
cur.executemany(
    "INSERT INTO books (title, author, `year`, tag, cat, level, tone, book_desc, why)"
    " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
    [
        (b["title"], b["author"], b["year"], b["tag"], b["cat"],
         b["level"], b["tone"], b["desc"], b["why"])
        for b in BOOKS
    ],
)
print("books:", len(BOOKS), "本")

# ---------- 书→文章配对 ----------
# 书目页的“读对应文章”和文章侧栏的“延伸阅读”都靠这个字段。
# 用书名定位（全库唯一）而不是 id：重建库后 id 会变，书名不会。
linked = 0
for title, slug in RELATED_MAP.items():
    cur.execute("UPDATE books SET related_slug = %s WHERE title = %s", (slug, title))
    if cur.rowcount:
        linked += 1
    else:
        print("警告：配对表里的书在库中找不到：", title)
print("books 配对：", linked, "/", len(RELATED_MAP), "本已关联文章")

# ---------- 书籍详情回填（pub/intro/structure/highlights/read_tip） ----------
# structure 和 highlights 是列表，存成 JSON 字符串；模板里再解开。
linked_d = 0
for title, d in BOOK_DETAILS.items():
    cur.execute(
        "UPDATE books SET pub=%s, intro=%s, structure=%s, highlights=%s, read_tip=%s"
        " WHERE title = %s",
        (d["pub"], d["intro"],
         json.dumps(d["structure"], ensure_ascii=False),
         json.dumps(d["highlights"], ensure_ascii=False),
         d["read_tip"], title))
    if cur.rowcount:
        linked_d += 1
    else:
        print("警告：详情表里的书在库中找不到：", title)
print("books 详情：", linked_d, "/", len(BOOK_DETAILS), "本已回填")

# ---------- 初始评论（倒着插，详情页按 id 倒序展示） ----------
cur.executemany(
    "INSERT INTO comments (article_slug, name, initial, `time`, stars, text, email)"
    " VALUES (%s,%s,%s,%s,%s,%s,%s)",
    [
        ("quantum-entanglement", c["name"], c["initial"], c["time"],
         c["stars"], c["text"], "")
        for c in reversed(COMMENTS)
    ],
)
print("comments:", len(COMMENTS), "条初始评论")

# ---------- 演示账号 ----------
cur.execute("INSERT INTO users (email, nickname, password_hash) VALUES (%s,%s,%s)",
            ("demo@gewu.site", "演示读者", generate_password_hash("gewu1234")))
print("users: 1 个演示账号 demo@gewu.site / gewu1234")

conn.commit()
cur.close()
conn.close()

print()
print("完成。现在可以：python app.py")
print("注意：重跑本脚本会清空所有评论与注册账号（等于恢复出厂）。")