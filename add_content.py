# -*- coding: utf-8 -*-
"""
增量更新内容：python add_content.py

和 init_db.py 的区别：
    init_db.py 是“恢复出厂”——先清空再灌数据，注册的账号、发的评论都会没。
    本脚本是“只加不删”——逐条查重，库里已有的跳过，新内容插入。
    适合日常往网站里加文章 / 加书目，不影响线上数据。

注意：sample_data.py 改了已有条目的文字时，本脚本不会更新库里的旧记录
（按标题/slug 判重直接跳过）。要“重灌”就跑 init_db.py。
"""

import json

import pymysql

from werkzeug.security import generate_password_hash

from config import DB_CONFIG
from sample_data import ARTICLES, BOOKS, RELATED_MAP, BOOK_DETAILS

conn = pymysql.connect(**DB_CONFIG)
cur = conn.cursor()

# ---------- 文章 ----------
new_a = added_a = 0
for a in ARTICLES:
    cur.execute("SELECT slug FROM articles WHERE slug = %s", (a["slug"],))
    if cur.fetchone():
        continue                      # 库里已有，跳过
    new_a += 1
    cur.execute(
        "INSERT INTO articles (slug, cat, cat_key, title, dek, excerpt, author, role,"
        " `date`, read_time, art, seed, featured, tags, blocks)"
        " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (a["slug"], a["cat"], a["cat_key"], a["title"], a["dek"], a["excerpt"],
         a["author"], a["role"], a["date"], a["read"], a["art"], a["seed"],
         1 if a.get("featured") else 0,
         json.dumps(a["tags"], ensure_ascii=False),
         json.dumps(a["blocks"], ensure_ascii=False)))
    added_a += 1
print("articles: 新增 %d / %d 篇" % (added_a, new_a))

# ---------- 书目（按书名+作者判重） ----------
new_b = added_b = 0
for b in BOOKS:
    cur.execute("SELECT id FROM books WHERE title = %s AND author = %s",
                (b["title"], b["author"]))
    if cur.fetchone():
        continue
    new_b += 1
    cur.execute(
        "INSERT INTO books (title, author, `year`, tag, cat, level, tone, book_desc, why)"
        " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (b["title"], b["author"], b["year"], b["tag"], b["cat"],
         b["level"], b["tone"], b["desc"], b["why"]))
    added_b += 1
print("books: 新增 %d / %d 本" % (added_b, new_b))

# ---------- 书→文章配对（幂等：每次全量回填一遍，保证和配对表一致） ----------
linked = 0
for title, slug in RELATED_MAP.items():
    cur.execute("UPDATE books SET related_slug = %s WHERE title = %s", (slug, title))
    if cur.rowcount:
        linked += 1
    else:
        print("警告：配对表里的书在库中找不到：", title)
print("books 配对：", linked, "/", len(RELATED_MAP), "本已关联文章")

# ---------- 书籍详情回填（幂等 UPDATE，改了 BOOK_DETAILS 重跑即可同步） ----------
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

# ---------- 演示账号（没有才建，保证随时可登录） ----------
cur.execute("SELECT id FROM users WHERE email = %s", ("demo@gewu.site",))
if not cur.fetchone():
    cur.execute("INSERT INTO users (email, nickname, password_hash) VALUES (%s,%s,%s)",
                ("demo@gewu.site", "演示读者", generate_password_hash("gewu1234")))
    print("users: 已补建演示账号 demo@gewu.site / gewu1234")
else:
    print("users: 演示账号已存在，跳过")

conn.commit()

cur.execute("SELECT COUNT(*) FROM articles"); n_a = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM books"); n_b = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM users"); n_u = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM comments"); n_c = cur.fetchone()[0]
cur.close()
conn.close()

print()
print("当前库内：文章 %d 篇 · 书目 %d 本 · 账号 %d 个 · 评论 %d 条" % (n_a, n_b, n_u, n_c))
print("已注册账号与评论全部保留，未做任何删除。")