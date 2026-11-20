# -*- coding: utf-8 -*-
"""
格物 · 科技科普站 —— Flask + MySQL 导学版
===================================================================
在 SQLite 版基础上，把数据库换成 MySQL（pymysql 驱动）。
连接配置集中在 config.py；驱动用法见 db.py；建库建表见 init_db.py。

与 SQLite 版的差异只有四处，都是 MySQL 的“方言”差异：
    1. 占位符 ? → %s
    2. date / year / time 这类列名是 MySQL 类型名，要加反引号
    3. 查询结果从 sqlite3.Row 换成 DictCursor 字典
    4. 连接可能被 MySQL 超时掐断，get_db() 里 ping(reconnect=True) 自动重连

首次运行先建库：python init_db.py
然后：python app.py  →  http://127.0.0.1:5000
"""

import json
import os
import datetime
from urllib.parse import quote

from flask import (Flask, render_template, request, redirect, url_for,
                   session, flash, abort, jsonify)
from werkzeug.security import generate_password_hash, check_password_hash

from db import query, execute, close_db
from sample_data import CATEGORIES


# ===================================================================
# 1. 应用对象与配置
# ===================================================================
app = Flask(__name__)

# SECRET_KEY 用于给 session（存在浏览器 Cookie 里）做签名。
# 没有它，一用 session 就报错；泄露了别人就能伪造你的登录状态。
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "gewu-dev-secret-2026")

# jsonify 默认把中文转成 \uXXXX；关掉更友好
app.json.ensure_ascii = False

# 开发阶段禁用静态文件缓存：改了 CSS/JS 刷新立即生效。
# Edge 等浏览器默认缓存 CSS 很久，表现为"改了没变化/页面空白"。
# 上线改回默认值（或给文件名加 hash），否则每次访问都重新下载。
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

# 请求结束后自动关闭数据库连接。
# teardown_appcontext：无论请求成功还是报错，最后都会执行一次。
app.teardown_appcontext(close_db)


# ===================================================================
# 2. 数据访问：把 SQL 收拢成几个小函数
# ===================================================================
# 路由里不该散落一长串 SQL。收拢到这里有两个好处：
#   1) 表结构变了只改这里；2) 路由读起来像业务流程，不像配置文件。

# 字段列表写成常量：多处查询共用。
# read_time AS read / book_desc AS desc：列名换成 Python 键名，
# 让模板拿到的字典形状和内存版完全一致（前端零改动的原因）。
ARTICLE_FIELDS = ("slug, cat, cat_key, title, dek, excerpt, author, role,"
                  " `date`, read_time AS `read`, art, seed, featured, tags, blocks")
BOOK_FIELDS = ("id, title, author, `year`, tag, cat, level, tone,"
               " book_desc AS `desc`, why, related_slug,"
               " pub, intro, structure, highlights, read_tip")


def row_to_article(row):
    """一行文章 → 模板认识的字典：tags / blocks 从 JSON 文本解开。"""
    a = dict(row)
    a["tags"] = json.loads(a["tags"])
    a["blocks"] = json.loads(a["blocks"])
    return a


def all_articles():
    rows = query("SELECT " + ARTICLE_FIELDS + " FROM articles ORDER BY `date` DESC")
    return [row_to_article(r) for r in rows]


def find_article(slug):
    """按 slug 查一篇文章；查无此文返回 None，由调用方决定 404。"""
    row = query("SELECT " + ARTICLE_FIELDS + " FROM articles WHERE slug = %s",
                (slug,), one=True)
    return row_to_article(row) if row else None


def row_to_book(row):
    """一行书 → 模板字典：structure / highlights 是 JSON 文本，解开成列表。"""
    b = dict(row)
    b["structure"] = json.loads(b["structure"]) if b.get("structure") else []
    b["highlights"] = json.loads(b["highlights"]) if b.get("highlights") else []
    return b


def all_books():
    rows = query("SELECT " + BOOK_FIELDS + " FROM books ORDER BY id")
    return [row_to_book(r) for r in rows]


def find_book(book_id):
    """按 id 查一本书；查无此书返回 None，由调用方决定 404。"""
    row = query("SELECT " + BOOK_FIELDS + " FROM books WHERE id = %s",
                (book_id,), one=True)
    return row_to_book(row) if row else None


def article_comments(slug):
    rows = query(
        "SELECT id, name, initial, `time`, stars, text, section, email"
        " FROM comments WHERE article_slug = %s ORDER BY id DESC", (slug,))
    return [dict(r) for r in rows]


def add_comment(slug, user, stars, content, section):
    """写一条评论。%s 占位符按顺序对应参数——顺序错了会写串列。"""
    execute(
        "INSERT INTO comments (article_slug, name, initial, `time`, stars,"
        " text, section, email) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        (slug, user["nickname"], user["nickname"][0],
         datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
         stars, content, section, user["email"]),
    )


def get_user(email):
    """按邮箱查用户（含 password_hash）；查无此人返回 None。"""
    row = query("SELECT id, email, nickname, password_hash FROM users"
                " WHERE email = %s", (email,), one=True)
    return dict(row) if row else None


def create_user(email, nickname, password):
    """注册。存哈希，绝不存明文——数据库被看到也无法直接登录。"""
    execute("INSERT INTO users (email, nickname, password_hash) VALUES (%s,%s,%s)",
            (email, nickname, generate_password_hash(password)))


def current_user():
    """从 session 的邮箱反查用户；没登录返回 None。

    每个请求查一次库，学习站完全够用。
    要省的话把结果缓存进 g（见课后练习 5）。
    """
    email = session.get("user_email")
    if not email:
        return None
    row = query("SELECT email, nickname FROM users WHERE email = %s",
                (email,), one=True)
    return dict(row) if row else None


def safe_next(target):
    """只允许跳回本站相对路径，防 ?next=https://evil.com 开放重定向。"""
    if not target:
        return None
    target = target.replace("\\", "/")
    if target.startswith("//"):
        return None
    if "://" in target or "/" not in target.lstrip("/"):
        return None
    return target if target.startswith("/") else None


# ===================================================================
# 2.5 分页：SQL 里 LIMIT/OFFSET，页码从 URL 参数解析
# ===================================================================
# 每页条数集中一处定义；页码永远夹在 [1, total_pages] 内，
# 防止 ?page=999999 把 OFFSET 拼出负数或越界。
PER_PAGE = 9


def parse_page():
    """?page=N 解析成整数；非法值一律回落到第 1 页。"""
    try:
        return max(1, int(request.args.get("page", "1")))
    except ValueError:
        return 1


def count_rows(table, where_sql="", args=()):
    """SELECT COUNT(*) 的小封装；分页总页数靠它。"""
    return query("SELECT COUNT(*) AS n FROM " + table + where_sql, args, one=True)["n"]


def login_required(view):
    """没登录就带去登录页，登录后跳回原页面。

    @wraps 保留原函数名——没有它，url_for 会找不到 endpoint。
    """
    from functools import wraps
    @wraps(view)
    def wrapper(*args, **kwargs):
        if current_user() is None:
            flash("请先登录，再继续操作", "warn")
            return redirect(url_for("login", next=request.full_path.rstrip("?")))
        return view(*args, **kwargs)
    return wrapper


# ===================================================================
# 3. 路由
# ===================================================================
@app.route("/")
def index():
    """首页：支持 ?cat=分类 筛选、?q=关键词 搜索、?page=页码 分页。

    筛选/搜索都走 SQL（WHERE + LIKE），翻页走 LIMIT/OFFSET——
    这就是课后练习 1、2 的实战版。featured 主推卡不受筛选影响，始终取全库。
    """
    cat = request.args.get("cat", "")
    q = request.args.get("q", "").strip()
    page = parse_page()

    # cat 必须是已知分类，否则重置为空（防止拼凑 URL 出奇怪状态）
    cat = cat if cat in [c["key"] for c in CATEGORIES if c["key"] != "all"] else ""
    cat_name = next((c["name"] for c in CATEGORIES if c["key"] == cat), "")

    # 动态拼 WHERE：条件列表最后用 AND 连接
    where, args = [], []
    if cat:
        where.append("cat_key = %s")
        args.append(cat)
    if q:
        where.append("(title LIKE %s OR excerpt LIKE %s)")
        args.extend(["%" + q + "%", "%" + q + "%"])
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""

    total = count_rows("articles", where_sql, tuple(args))
    total_all = count_rows("articles")       # Hero 区的“深度长文”始终显示全量，不随筛选变小
    total_pages = max(1, -(-total // PER_PAGE))       # 向上取整：-(-a // b)
    page = min(page, total_pages)
    offset = (page - 1) * PER_PAGE

    rows = query("SELECT " + ARTICLE_FIELDS + " FROM articles" + where_sql +
                 " ORDER BY `date` DESC LIMIT %s OFFSET %s",
                 tuple(args) + (PER_PAGE, offset))
    articles = [row_to_article(r) for r in rows]

    # 主推卡始终显示全库最新主推，不被筛选影响
    frow = query("SELECT " + ARTICLE_FIELDS + " FROM articles"
                 " WHERE featured = 1 ORDER BY `date` DESC LIMIT 1", one=True)
    featured = row_to_article(frow) if frow else None

    def page_url(target):
        """生成分页链接：保留当前筛选/搜索条件，只换页码。"""
        extra = {}
        if cat:
            extra["cat"] = cat
        if q:
            extra["q"] = q
        extra["page"] = target
        return url_for("index", **extra)

    return render_template(
        "index.html",
        active="home",
        articles=articles,
        categories=CATEGORIES,
        current_cat=cat,
        current_cat_name=cat_name,
        q=q,
        total=total,
        total_all=total_all,
        page=page,
        total_pages=total_pages,
        page_url=page_url,
        featured=featured,
    )


@app.route("/article/<slug>")
def detail(slug):
    article = find_article(slug)
    if article is None:
        abort(404)          # 交给下面的 errorhandler(404)

    toc = [b for b in article["blocks"] if b["t"] == "h2"]
    books = all_books()
    # 侧栏书目：先列“配对表里指向本文”的书（真讲这本书的），
    # 不足 3 本再按同分类补、最后拿其他分类凑数。linked_ids 用来去重，
    # 避免同一本书既出现在配对区又出现在补位区。
    linked = [b for b in books if b.get("related_slug") == slug]
    linked_ids = {b["id"] for b in linked}
    same_cat = [b for b in books if b["cat"] == article["cat_key"] and b["id"] not in linked_ids]
    others = [b for b in books if b["cat"] != article["cat_key"] and b["id"] not in linked_ids]

    return render_template(
        "detail.html",
        active="home",
        article=article,
        toc=toc,
        comments=article_comments(slug),
        related_books=(linked + same_cat + others)[:3],
        related=[a for a in all_articles() if a["slug"] != slug][:3],
    )


@app.route("/books")
def books():
    """书目页：分页 + 分类筛选；?book=ID 表示“从文章跳来，要定位到这本书”。

    定位逻辑：算出这本书在第几页 → 重定向到那一页 → 模板给它加高亮，
    浏览器/JS 再滚到锚点。分页与定位联动是本页唯一绕一点的逻辑。
    """
    cat = request.args.get("cat", "")
    cat = cat if cat in [c["key"] for c in CATEGORIES if c["key"] != "all"] else ""
    page = parse_page()
    book_id = request.args.get("book", type=int)   # type=int：非数字自动变 None

    where_sql = " WHERE cat = %s" if cat else ""
    args = (cat,) if cat else ()
    total = count_rows("books", where_sql, args)
    total_all = count_rows("books")               # Hero 区的“本精选”始终显示全量，不随筛选变小
    total_pages = max(1, -(-total // PER_PAGE))

    current_book = None
    current_cat_name = next((c["name"] for c in CATEGORIES if c["key"] == cat), "")
    if book_id:
        # 目标书的序号 = id 排在它前面（含自己）的数量；序号决定页码
        pos = count_rows("books", " WHERE id <= %s", (book_id,))
        pages_all = max(1, -(-count_rows("books") // PER_PAGE))
        target = min(max(1, -(-pos // PER_PAGE)), pages_all)
        # 带着筛选看某一本书会混乱：直接跳到无筛选的正确页
        # _anchor → 链接尾部拼上 #book-<id>，浏览器加载完自动滚到那张书卡，零 JS。
        # 注意：Flask 里这个特殊参数叫 _anchor，写成 _fragment 会被当成普通查询参数。
        if page != target or cat:
            return redirect(url_for("books", page=target, book=book_id,
                                    _anchor="book-{}".format(book_id)))
        row = query("SELECT " + BOOK_FIELDS + " FROM books WHERE id = %s",
                    (book_id,), one=True)
        if row:
            current_book = row_to_book(row)

    page = min(page, total_pages)
    offset = (page - 1) * PER_PAGE
    rows = query("SELECT " + BOOK_FIELDS + " FROM books" + where_sql +
                 " ORDER BY id LIMIT %s OFFSET %s", args + (PER_PAGE, offset))
    books_list = [row_to_book(r) for r in rows]

    def page_url(target):
        extra = {"page": target}
        if cat:
            extra["cat"] = cat
        return url_for("books", **extra)

    return render_template(
        "books.html",
        active="books",
        books=books_list,
        categories=[c for c in CATEGORIES if c["key"] != "all"],
        current_cat=cat,
        current_cat_name=current_cat_name,
        total=total,
        total_all=total_all,
        page=page,
        total_pages=total_pages,
        page_url=page_url,
        current_book=current_book,
    )


@app.route("/book/<int:book_id>")
def book_detail(book_id):
    """书籍详情页：这本书讲了什么（脉络、看点）+ 对应文章与同板块书。

    <int:book_id> 是路由自带的类型转换：URL 里不是数字就直接 404，
    不用进函数再判——这是 Flask 比手写正则省心的地方。
    """
    book = find_book(book_id)
    if book is None:
        abort(404)          # 交给 errorhandler(404)

    # 配对的文章：related_slug 有值才查，查无此文（文章被删）也不报错
    related_article = None
    if book.get("related_slug"):
        related_article = find_article(book["related_slug"])

    # 同板块的其他书，供侧栏“接着逛”
    same_cat_books = [b for b in all_books()
                      if b["cat"] == book["cat"] and b["id"] != book["id"]][:3]

    # books 表存的是板块 key（如 physics），页面要显示中文名（如 物理）
    cat_name = next((c["name"] for c in CATEGORIES if c["key"] == book["cat"]), book["cat"])

    # 购书入口：跳到平台的站内搜索页（带书名+作者），而不是写死某个商品页——
    # 商品链接会下架失效，搜索页永远稳定。quote() 把中文变成 URL 安全字符
    # （如 数学之美 → %E6%95%B0%E5%AD%A6%E4%B9%8B%E7%BE%8E），否则链接会断。
    q = quote(book["title"] + " " + book["author"])
    buy_links = [
        ("京东图书", "https://search.jd.com/Search?keyword={}&enc=utf-8".format(q)),
        ("当当网", "http://search.dangdang.com/?key={}&act=input".format(q)),
        ("豆瓣图书", "https://book.douban.com/subject_search?search_text={}".format(q)),
    ]

    return render_template(
        "book_detail.html",
        active="books",
        book=book,
        cat_name=cat_name,
        buy_links=buy_links,
        related_article=related_article,
        same_cat_books=same_cat_books,
    )


# ===================================================================
# 4. 表单：GET 显示、POST 提交（失败直接 render 以保留输入）
# ===================================================================
@app.route("/login", methods=["GET", "POST"])
def login():
    next_url = request.values.get("next", "")

    if request.method == "POST":
        account = request.form.get("account", "").strip().lower()
        password = request.form.get("password", "")

        user = get_user(account)
        # 两个条件合成一个提示：不暴露"哪些邮箱注册过"
        if user is None or not check_password_hash(user["password_hash"], password):
            # 校验失败直接 render（不是 redirect）：邮箱还能回填
            # 返回 401 是语义正确的状态码；浏览器控制台会记一条红字，不是代码报错
            return render_template(
                "login.html", active="auth", account=account,
                error="账号或密码不正确，请重新输入",
            ), 401

        session["user_email"] = account
        flash("欢迎回来，%s" % user["nickname"], "success")
        return redirect(safe_next(next_url) or url_for("index"))

    return render_template("login.html", active="auth", account="")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        nickname = request.form.get("nickname", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")
        agree = request.form.get("agree")

        # 校验顺序：先格式，再业务（重复邮箱），最后协议。
        # 前端 JS 只是体验优化，这里必须再校验一遍——绕过前端太容易。
        error = None
        if len(nickname) < 2:
            error = "昵称至少 2 个字"
        elif "@" not in email or "." not in email.split("@")[-1]:
            error = "邮箱格式看起来不对"
        elif len(password) < 8:
            error = "密码至少 8 位"
        elif password != password2:
            error = "两次输入的密码不一致"
        elif get_user(email):
            # 表里还有 UNIQUE 约束兜底：就算这里漏判，INSERT 会直接报错
            error = "这个邮箱已经注册过了，直接登录吧"
        elif not agree:
            error = "请先勾选同意用户协议与隐私说明"

        if error:
            return render_template(
                "register.html", active="auth", error=error,
                nickname=nickname, email=email,
            ), 400

        create_user(email, nickname, password)
        session["user_email"] = email      # 注册完直接登录，少一步
        flash("注册成功，已为你自动登录", "success")
        return redirect(url_for("index"))

    return render_template("register.html", active="auth")


@app.route("/logout")
def logout():
    session.pop("user_email", None)
    flash("已退出登录", "success")
    return redirect(url_for("index"))


@app.route("/comment", methods=["GET", "POST"])
@login_required
def comment():
    slug = request.values.get("article", "quantum-entanglement")
    article = find_article(slug) or all_articles()[0]

    if request.method == "POST":
        content = request.form.get("content", "").strip()
        section = request.form.get("section", "")
        try:
            stars = int(request.form.get("stars", "0"))
        except ValueError:
            stars = 0

        if len(content) < 10:
            flash("评论至少写 10 个字，方便作者回应你", "warn")
            return redirect(url_for("comment", article=article["slug"]))
        if not 1 <= stars <= 5:
            flash("请给这篇文章打个星级（1–5 星）", "warn")
            return redirect(url_for("comment", article=article["slug"]))

        add_comment(article["slug"], current_user(), stars, content, section)
        flash("评论已发布，感谢你的补充", "success")
        # PRG 模式：POST 后必须 redirect，否则用户刷新会重复提交
        return redirect(url_for("detail", slug=article["slug"]) + "#comments")

    return render_template("pub.html", active="home", article=article)


# ===================================================================
# 5. 模板过滤器与上下文处理器
# ===================================================================
@app.template_filter("cn_date")
def cn_date(value):
    """"2026-11-08" → "2026 年 11 月 8 日"；解析失败原样返回。"""
    try:
        y, m, d = value.split("-")
        return "%s 年 %s 月 %s 日" % (int(y), int(m), int(d))
    except (ValueError, AttributeError):
        return value


@app.context_processor
def inject_globals():
    """所有模板直接用 current_user / site_year，不用每个路由都传。

    current_user() 会查一次库。导航栏、页脚、评论页都要用，
    集中注入比在每个路由里传一遍干净得多。
    """
    return {"current_user": current_user(),
            "site_year": datetime.date.today().year}


# ===================================================================
# 6. JSON 接口（给小程序 / 前后端分离用）
# ===================================================================
@app.route("/api/articles")
def api_articles():
    # 过滤也换成 SQL：?cat=ai 走 WHERE，不再 Python 循环
    cat = request.args.get("cat", "")
    sql = ("SELECT slug, title, cat, `date`, read_time AS `read` FROM articles"
           + (" WHERE cat_key = %s" if cat else "") + " ORDER BY `date` DESC")
    items = [dict(r) for r in query(sql, (cat,) if cat else ())]
    return jsonify({"count": len(items), "items": items})


@app.route("/api/articles/<slug>")
def api_article(slug):
    article = find_article(slug)
    if article is None:
        return jsonify({"error": "article_not_found", "slug": slug}), 404
    return jsonify({"slug": article["slug"], "title": article["title"],
                    "cat": article["cat"], "tags": article["tags"],
                    "blocks": article["blocks"]})


@app.route("/api/health")
def api_health():
    """自检：部署后先访问它。COUNT(*) 能出数，说明库和表都在。"""
    counts = {}
    for table in ("articles", "books", "users", "comments"):
        counts[table] = query("SELECT COUNT(*) AS n FROM " + table, one=True)["n"]
    return jsonify({
        "status": "ok",
        "articles": counts["articles"],
        "books": counts["books"],
        "users": counts["users"],
        "comments": counts["comments"],
        "time": datetime.datetime.now().isoformat(timespec="seconds"),
    })


# ===================================================================
# 7. 错误处理
# ===================================================================
@app.errorhandler(404)
def not_found(_error):
    return render_template("404.html", active=""), 404


@app.errorhandler(500)
def server_error(_error):
    # debug=True 时 Flask 优先显示调试页，看不到这个模板；
    # 关掉 debug 再故意触发一次异常，才能验证这里的样式
    return render_template("500.html", active=""), 500


# ===================================================================
# 8. 启动
# ===================================================================
if __name__ == "__main__":
    # debug=True：改代码自动重启 + 出错显示堆栈，开发用；上线必须关
    # 数据库没建的话启动后第一个请求就会报错，先跑 init_db.py
    app.run(host="127.0.0.1", port=5000, debug=True)


# ===================================================================
# 课后练习（从易到难，每个都能独立验证）
# ===================================================================
# 1. /api/articles 加分页：?page=1&size=3，SQL 用 LIMIT %s OFFSET %s，
#    返回 page / total_pages。
# 2. 加搜索接口 /api/articles?q=量子：WHERE title LIKE CONCAT('%%', %s, '%%')，
#    注意 pymysql 里 %s 旁边的字面 % 要写成 %%。
# 3. 详情页评论按星级过滤：?stars=5 → WHERE article_slug=%s AND stars=%s。
# 4. 加"编辑自己的评论"：UPDATE comments SET text=%s WHERE id=%s AND email=%s。
#    WHERE 里带上 email，别人就改不了你的。
# 5. 把 current_user 的查询结果缓存进 g（同一请求只查一次）：
#    if "user" not in g: g.user = ...。改完用 api/health 对比响应速度。
# 6. comments.email 改成 user_id INT，加外键
#    FOREIGN KEY (user_id) REFERENCES users(id)，
#    体会外键约束拦下了什么；引擎必须是 InnoDB 才支持外键。
# 7. 思考题：登录失败返回 401、注册校验失败返回 400，为什么状态码不同？