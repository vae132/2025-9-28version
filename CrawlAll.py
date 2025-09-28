import requests
from bs4 import BeautifulSoup
import time
import hashlib
import re
import json
import os
import datetime  # 新增，用于解析发布时间

BASE_URL = "https://andylee.pro/wp/"
# 固定页面（如关于页面）不参与翻页爬取
PAGE_URLS = [
    "https://andylee.pro/wp/?page_id=11",
    "https://andylee.pro/wp/?page_id=18",
    "https://andylee.pro/wp/?page_id=1230",
    "https://andylee.pro/wp/?page_id=2115",
]
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
}
TARGET_USERS = ["李宗恩", "andy"]

# 进度文件，用于记录当前页码和页内文章序号（均从1开始）
PROGRESS_FILE = "progress.txt"


def fetch_url(url, headers=HEADERS, timeout=10, max_retries=10):
    """
    尝试获取 URL 内容，如果失败则重试 max_retries 次。
    成功返回 response 对象，失败返回 None。
    """
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            if response.status_code == 200:
                return response
            else:
                print(f"❌ 尝试 {attempt} 次: 获取 {url} 失败，状态码: {response.status_code}")
        except Exception as e:
            print(f"❌ 尝试 {attempt} 次: 请求 {url} 出错: {e}")
        time.sleep(2)  # 等待2秒后重试
    print(f"❌ 已尝试 {max_retries} 次，仍无法获取 {url}")
    return None


def get_last_progress():
    """
    返回上次成功爬取的进度，格式为 (page, order)。
    如果文件不存在或格式错误，则默认返回 (1, 1)。
    """
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            try:
                progress = json.load(f)
                page = progress.get("page", 1)
                order = progress.get("order", 1)
                return page, order
            except Exception as e:
                print(f"❌ 读取进度文件失败: {e}")
                return 1, 1
    return 1, 1


def save_progress(page, order):
    """
    保存当前爬取进度，page 表示当前页码，
    order 表示当前页下一篇需要爬取的文章序号（1-indexed）。
    """
    progress = {"page": page, "order": order}
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(progress, f)


def get_article_links(page=1):
    """
    获取指定页码的所有文章链接
    """
    url = f"{BASE_URL}?paged={page}"
    response = fetch_url(url)
    if not response:
        return []
    soup = BeautifulSoup(response.text, "html.parser")
    articles = soup.find_all("h2", class_="entry-title")
    links = [article.a["href"] for article in articles if article.a]
    return links


def get_article_title(article_url):
    """
    获取文章标题
    """
    response = fetch_url(article_url)
    if not response:
        return "未知标题"
    soup = BeautifulSoup(response.text, "html.parser")
    title_tag = soup.find("h1", class_="post-title entry-title")
    return title_tag.text.strip() if title_tag else "未知标题"


def get_article_content(article_url):
    """
    获取文章正文内容
    """
    response = fetch_url(article_url)
    if not response:
        return "未知内容"
    soup = BeautifulSoup(response.text, "html.parser")
    content_tag = soup.find("div", class_="entry-content")
    if content_tag:
        # 使用 decode_contents() 保留内部 HTML 格式
        return content_tag.decode_contents().strip()
    return "未知内容"


def get_article_time(article_url):
    """
    获取文章发布时间，格式为 "YYYY年MM月DD日 HH:MM"
    """
    response = fetch_url(article_url)
    if not response:
        return ""
    soup = BeautifulSoup(response.text, "html.parser")
    time_span = soup.find("span", class_="entry-date post-date")
    if time_span:
        abbr_tag = time_span.find("abbr", class_="published")
        if abbr_tag and abbr_tag.has_attr("title"):
            iso_time = abbr_tag["title"]  # 例如 "2025-01-29T16:49:00-08:00"
            try:
                dt = datetime.datetime.fromisoformat(iso_time)
                formatted_time = dt.strftime("%Y年%m月%d日 %H:%M")
                return formatted_time
            except Exception as e:
                print("❌ 解析发布时间错误:", e)
                return abbr_tag.text.strip()
        else:
            return time_span.get_text(strip=True)
    return ""


def get_page_title(page_url):
    """
    获取固定页面的标题
    """
    response = fetch_url(page_url)
    if not response:
        return "未知标题"
    soup = BeautifulSoup(response.text, "html.parser")
    title_tag = soup.find("h1")
    return title_tag.text.strip() if title_tag else "未知标题"


def generate_unique_id(article_url, index):
    """
    生成唯一的ID，结合文章URL和评论索引
    """
    return hashlib.md5(f"{article_url}-{index}".encode('utf-8')).hexdigest()


def parse_comment(comment, article_url, level=0, selected_color="white", index=0):
    """
    解析评论及其子评论，并返回数据字典和最新的索引值
    """
    author_tag = comment.find("cite", class_="fn")
    if not author_tag:
        return None, index
    comment_user = author_tag.text.strip()

    time_tag = comment.find("small")
    if time_tag:
        raw_time = time_tag.get_text(strip=True)
        match = re.search(r'(\d+)\s*(\d+)\s*月,\s*(\d{4})\s+at\s+(\d+):(\d+)\s*(上午|下午)', raw_time)
        if match:
            day = int(match.group(1))
            month = int(match.group(2))
            year = int(match.group(3))
            hour = int(match.group(4))
            minute = int(match.group(5))
            period = match.group(6)
            if period == "下午" and hour < 12:
                hour += 12
            time_text = f"{year}年{month:02d}月{day:02d}日 {hour:02d}:{minute:02d}"
        else:
            time_text = raw_time
    else:
        time_text = ""

    comment_text_tag = comment.find("div", class_="comment_text")
    if not comment_text_tag:
        return None, index

    # 删除评论中的回复按钮标签
    for reply in comment_text_tag.find_all("div", class_="reply"):
        reply.decompose()
    comment_text = comment_text_tag.decode_contents().strip()

    highlight = (comment_user in TARGET_USERS)
    current_index = index
    comment_id = generate_unique_id(article_url, current_index)
    index = current_index + 1

    datatest = {
        "id": comment_id,
        "author": comment_user,
        "time": time_text,
        "content": comment_text,
        "level": level,
        "highlight": highlight,
        "children": []
    }

    children_container = comment.find("ul", class_="children")
    if children_container:
        child_comments = children_container.find_all("li", class_="comment", recursive=False)
        for child in child_comments:
            child_datatest, index = parse_comment(child, article_url, level + 1, selected_color, index)
            if child_datatest:
                datatest["children"].append(child_datatest)
    return datatest, index


def get_comments(article_url, selected_color="white"):
    """
    获取文章的所有评论及其回复，并返回评论数据（列表字典）
    """
    response = fetch_url(article_url)
    if not response:
        return []
    soup = BeautifulSoup(response.text, "html.parser")
    comment_list = soup.find("ol", class_="commentlist")
    if comment_list:
        top_comments = comment_list.find_all("li", class_="comment", recursive=False)
    else:
        top_comments = soup.find_all("li", class_="comment", recursive=False)

    results = []
    index = 0
    for comment in top_comments:
        datatest, index = parse_comment(comment, article_url, selected_color=selected_color, index=index)
        if datatest:
            results.append(datatest)
    return results


def save_to_json_file(article_url, article_title, article_content, comments_datatest, page, order):
    """
    将爬取的文章信息、正文、发布时间和评论数据保存为 JSON 文件到 datatest/page{page}/ 目录下
    """
    article_time = get_article_time(article_url)
    out = {
        "article_url": article_url,
        "title": article_title,
        "content": article_content,
        "article_time": article_time,
        "comments": comments_datatest,
        "page": page,
        "order": order
    }
    unique = generate_unique_id(article_url, order)
    folder = os.path.join("datatest", f"page{page}")
    if not os.path.exists(folder):
        os.makedirs(folder)
    filename = os.path.join(folder, f"page{page}_order{order}_{unique}.json")
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"保存《{article_title}》评论数据到 {filename}")


def crawl():
    """
    爬取评论并将数据保存为 JSON 文件，每页最多处理 10 篇文章。
    支持断点续爬，进度记录包含当前页和页内文章序号。
    """
    start_page, start_order = get_last_progress()
    current_page = start_page
    articles_per_page = 10

    while True:
        print(f"📌 正在爬取第 {current_page} 页文章...")
        article_links = get_article_links(current_page)
        if not article_links:
            print("🚫 没有更多文章，停止爬取。")
            break

        # 如果当前页为断点页，则从 start_order 开始爬取，否则从第一篇开始
        if current_page == start_page:
            article_links = article_links[start_order - 1:]
            initial_order = start_order
        else:
            initial_order = 1

        for idx, link in enumerate(article_links, start=initial_order):
            article_title = get_article_title(link)
            article_content = get_article_content(link)
            print(f"📌 爬取 第 {current_page} 页 第 {idx} 篇: {link} | {article_title}")
            comments_datatest = get_comments(link)
            save_to_json_file(link, article_title, article_content, comments_datatest, current_page, idx)
            # 每成功处理一篇文章，更新进度记录（下一篇序号为 idx+1）
            save_progress(current_page, idx + 1)
            time.sleep(2)

        # 当前页处理完成，重置页内文章序号，并记录进度
        start_order = 1
        save_progress(current_page, 1)
        current_page += 1
        time.sleep(3)

    # 爬取固定页面（非分页页面）
    fixed_folder = os.path.join("datatest", "fixed")
    if not os.path.exists(fixed_folder):
        os.makedirs(fixed_folder)
    for page_url in PAGE_URLS:
        print(f"📌 爬取固定页面: {page_url}")
        page_title = get_page_title(page_url)
        article_content = get_article_content(page_url)
        print(f"📌 页面标题: {page_title}")
        comments_datatest = get_comments(page_url)
        file_id = generate_unique_id(page_url, 0)
        article_time = get_article_time(page_url)
        filename = os.path.join(fixed_folder, f"{file_id}.json")
        out = {
            "article_url": page_url,
            "title": page_title,
            "content": article_content,
            "article_time": article_time,
            "comments": comments_datatest,
            "fixed": True
        }
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(f"保存固定页面《{page_title}》到 {filename}")
        time.sleep(2)
    print("\n✅ 爬取完成，评论数据已保存到 datatest 目录中。")


if __name__ == "__main__":
    crawl()
