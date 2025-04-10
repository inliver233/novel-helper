# ainovel/condenser.py
#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
import threading
import queue
import concurrent.futures
import datetime # 添加 datetime 导入
import time # 添加 time 导入, 模拟耗时
import traceback # 添加 traceback 导入
import uuid  # 用于生成唯一ID
import re  # 用于正则表达式
import tempfile  # 用于临时文件处理
import shutil  # 用于文件操作

# EPUB处理相关依赖
REQUIRED_LIBRARIES = {
    'ebooklib': False,
    'bs4': False
}

# 检查是否已安装必要的库
try:
    import ebooklib
    from ebooklib import epub
    REQUIRED_LIBRARIES['ebooklib'] = True
except ImportError:
    print("警告: ebooklib库未找到，EPUB功能将不可用。请安装：pip install ebooklib")

try:
    from bs4 import BeautifulSoup
    REQUIRED_LIBRARIES['bs4'] = True
except ImportError:
    print("警告: BeautifulSoup库未找到，EPUB功能将不可用。请安装：pip install beautifulsoup4 lxml")

# 检查是否安装了customtkinter
try:
    import customtkinter as ctk
    HAS_CTK = True
except ImportError:
    HAS_CTK = False
    # 如果没有ctk，则定义一个兼容的基类
    class CTkToplevel(tk.Toplevel): pass
    class CTkFrame(tk.Frame): pass
    class CTkLabel(tk.Label): pass
    class CTkButton(ttk.Button): pass
    class CTkEntry(ttk.Entry): pass
    class CTkRadioButton(ttk.Radiobutton): pass
    class CTkCheckBox(ttk.Checkbutton): pass
    class CTkProgressBar(ttk.Progressbar): pass
    class CTkTextbox(tk.Text): pass # 注意：Text没有直接的ttk等价物，这里用tk.Text
    class CTkOptionMenu(ttk.Combobox): pass
    class CTkFont:
        def __init__(self, size=12, weight='normal'):
             self.size = size
             self.weight = weight

# EPUB处理的辅助函数
def check_epub_dependencies():
    """检查EPUB处理所需的依赖是否已安装"""
    missing = [lib for lib, installed in REQUIRED_LIBRARIES.items() if not installed]
    if missing:
        missing_str = ", ".join(missing)
        message = f"缺少EPUB处理所需的库: {missing_str}\n"
        message += "请安装必要的依赖:\n"
        message += "pip install ebooklib beautifulsoup4 lxml"
        return False, message
    return True, "所有依赖已安装"

# EPUB处理的核心函数 - 从epub_splitter.py提取
def html_to_text(html_content):
    """
    将HTML内容转换为纯文本
    
    Args:
        html_content: HTML格式的内容字符串
        
    Returns:
        str: 提取并格式化后的纯文本
    """
    try:
        # 优先尝试使用XML解析器（适用于EPUB中的XML文档）
        soup = BeautifulSoup(html_content, 'xml')
    except Exception as e:
        # 如果XML解析失败，回退到lxml解析器
        print(f"XML解析失败，回退到lxml: {e}")
        soup = BeautifulSoup(html_content, 'lxml')
    
    # 移除脚本和样式元素
    for script in soup(["script", "style"]):
        script.extract()
    
    # 获取文本
    text = soup.get_text()
    
    # 处理多余的空行和空格
    lines = (line.strip() for line in text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    text = '\n'.join(chunk for chunk in chunks if chunk)
    
    return text

def extract_title_from_html(html_content):
    """
    从HTML内容中提取章节标题
    
    Args:
        html_content: HTML格式的内容字符串
        
    Returns:
        str or None: 提取的章节标题，如果无法提取则返回None
    """
    try:
        # 优先尝试使用XML解析器（适用于EPUB中的XML文档）
        soup = BeautifulSoup(html_content, 'xml')
    except Exception as e:
        # 如果XML解析失败，回退到lxml解析器
        print(f"XML解析失败，回退到lxml: {e}")
        soup = BeautifulSoup(html_content, 'lxml')
    
    # 查找标题策略1: 标准HTML标题标签
    for tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
        title_tag = soup.find(tag)
        if title_tag and title_tag.get_text().strip():
            return title_tag.get_text().strip()
    
    # 查找标题策略2: 特定class或id
    title_candidates = []
    title_pattern = re.compile(r'(chapter|title|heading)', re.IGNORECASE)
    
    # 查找可能包含"chapter"、"title"、"heading"等关键词的class
    for element in soup.find_all(class_=title_pattern):
        text = element.get_text().strip()
        if text:
            title_candidates.append(text)
    
    # 查找可能包含"chapter"、"title"、"heading"等关键词的id
    for element in soup.find_all(id=title_pattern):
        text = element.get_text().strip()
        if text:
            title_candidates.append(text)
    
    # 查找标题策略3: 章节模式文本
    chapter_pattern = re.compile(r'(第\s*[0-9一二三四五六七八九十百千万]+\s*[章节]|Chapter\s+\d+)', re.IGNORECASE)
    
    for element in soup.find_all(string=chapter_pattern):
        parent = element.parent
        if parent and parent.get_text().strip():
            title_candidates.append(parent.get_text().strip())
    
    # 如果找到了候选标题，返回最长的一个(通常最完整)
    if title_candidates:
        return max(title_candidates, key=len)
    
    # 如果未找到标题，返回None
    return None

def get_safe_filename(text, max_length=50):
    """
    将文本转换为安全的文件名
    
    Args:
        text: 原始文本
        max_length: 文件名最大长度，默认50
    
    Returns:
        str: 处理后的安全文件名
    """
    if not text:
        return "unnamed"
        
    # 移除不适合作为文件名的字符
    unsafe_chars = r'[\\/*?:"<>|]'
    safe_text = re.sub(unsafe_chars, '', text)
    
    # 替换空白字符为下划线
    safe_text = re.sub(r'\s+', '_', safe_text)
    
    # 限制长度，避免文件名过长
    if len(safe_text) > max_length:
        safe_text = safe_text[:max_length-3] + '...'
        
    return safe_text

def get_spine_order(book):
    """
    获取EPUB书籍的spine顺序，这反映了阅读的正确顺序
    
    Args:
        book: EPUB书籍对象
    
    Returns:
        dict: 文档ID到序号的映射
    """
    spine_ids = [item[0] for item in book.spine]
    id_to_index = {id: index for index, id in enumerate(spine_ids)}
    return id_to_index

def clean_content(content, title):
    """
    清理章节内容，移除可能重复的标题
    
    Args:
        content: 章节内容
        title: 章节标题
    
    Returns:
        str: 清理后的内容
    """
    if not title or not content:
        return content
        
    # 尝试移除内容开头的标题
    lines = content.split('\n')
    clean_lines = []
    title_removed = False
    title_lower = title.lower().strip()
    
    # 检查前几行是否包含标题
    for line in lines:
        line_stripped = line.strip()
        line_lower = line_stripped.lower()
        
        # 如果行与标题完全匹配或包含标题
        if not title_removed and (line_lower == title_lower or title_lower in line_lower):
            title_removed = True
            continue
        clean_lines.append(line)
    
    return '\n'.join(clean_lines)

def sort_items_by_spine(items, spine_order):
    """
    按照spine顺序排序文档
    
    Args:
        items: 文档项列表
        spine_order: spine顺序字典
    
    Returns:
        list: 排序后的文档列表
    """
    def get_item_order(item):
        # 首先尝试通过ID在spine中查找顺序
        item_id = item.get_id()
        if item_id in spine_order:
            return spine_order[item_id]
        # 如果ID不在spine中，尝试通过文件名中的数字排序
        digits = ''.join(filter(str.isdigit, item_id))
        return int(digits) if digits else float('inf')
    
    try:
        # 尝试按spine顺序排序
        return sorted(items, key=get_item_order)
    except Exception as e:
        print(f"按spine顺序排序失败 ({e})，尝试按文件名中的数字排序")
        # 回退方案：按文件名中的数字排序
        return sorted(items, key=lambda x: int(''.join(filter(str.isdigit, x.get_id()))) 
                    if any(c.isdigit() for c in x.get_id()) else float('inf'))

def extract_chapters(items):
    """
    从HTML文档中提取章节内容
    
    Args:
        items: 排序后的文档项列表
    
    Returns:
        list: 包含(章节标题, 章节内容)元组的列表
    """
    chapters = []
    
    for index, item in enumerate(items):
        try:
            # 解码HTML内容
            html_content = item.get_content().decode('utf-8')
            
            # 提取章节标题
            chapter_title = extract_title_from_html(html_content)
            
            # 如果无法提取标题，使用索引作为标题
            if not chapter_title:
                item_id = item.get_id()
                chapter_title = f"Chapter {index + 1} (ID: {item_id})"
            
            # 提取章节文本
            chapter_text = html_to_text(html_content)
            
            # 清理章节内容，移除可能重复的标题
            chapter_text = clean_content(chapter_text, chapter_title)
            
            # 确保章节内容不为空
            if chapter_text.strip():
                chapters.append((chapter_title, chapter_text))
                print(f"已提取章节: {chapter_title}")
            else:
                print(f"跳过空章节: {chapter_title}")
        except Exception as e:
            print(f"处理文档 {item.get_id()} 时出错: {e}")
    
    return chapters

def split_epub(epub_path, output_dir, chapters_per_file=1, use_range_in_filename=True):
    """
    分割EPUB文件，每个输出文件包含指定数量的章节
    
    Args:
        epub_path: EPUB文件路径
        output_dir: 输出目录
        chapters_per_file: 每个txt文件中包含的章节数，默认为1
        use_range_in_filename: 是否在文件名中使用章节范围，默认为True
        
    Returns:
        bool: 操作是否成功
    """
    # 检查依赖
    deps_ok, msg = check_epub_dependencies()
    if not deps_ok:
        print(msg)
        return False
        
    try:
        # 创建输出目录（如果不存在）
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 读取EPUB文件
        print(f"正在读取EPUB文件: {epub_path}")
        book = epub.read_epub(epub_path)
        
        # 使用EPUB文件名作为书名
        book_title = Path(epub_path).stem
        book_title = get_safe_filename(book_title)
        
        print(f"处理书籍: {book_title}")
        
        # 获取所有HTML文档
        items = list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
        print(f"总共找到 {len(items)} 个文档")
        
        if not items:
            print("EPUB文件不包含任何文档")
            return False
        
        # 获取spine顺序并排序文档
        spine_order = get_spine_order(book)
        items = sort_items_by_spine(items, spine_order)
        
        # 提取章节
        chapters = extract_chapters(items)
        
        print(f"成功提取 {len(chapters)} 个章节")
        
        if not chapters:
            print("未能提取任何章节。请检查EPUB文件是否有效。")
            return False
        
        # 按指定数量分割章节并写入txt文件
        successful_files = 0
        total_files = (len(chapters) + chapters_per_file - 1) // chapters_per_file
        
        for i in range(0, len(chapters), chapters_per_file):
            chunk_chapters = chapters[i:i+chapters_per_file]
            file_index = i // chapters_per_file + 1
            
            # 生成输出文件名
            if len(chunk_chapters) == 1:
                # 当只有一个章节时，使用"书名_[序号]_章节名.txt"格式
                chapter_title = get_safe_filename(chunk_chapters[0][0])
                output_filename = os.path.join(output_dir, f"{book_title}_[{file_index:03d}]_{chapter_title}.txt")
            else:
                # 当有多个章节时，使用简单格式
                output_filename = os.path.join(output_dir, f"{book_title}_[{file_index:03d}].txt")
            
            # 写入章节到文件
            try:
                with open(output_filename, 'w', encoding='utf-8') as f:
                    for idx, (title, content) in enumerate(chunk_chapters):
                        # 写入章节标题
                        f.write(f"{title}\n\n")
                        # 写入章节内容
                        f.write(content)
                        
                        # 只在章节之间添加分隔符，最后一个章节不添加
                        if idx < len(chunk_chapters) - 1:
                            f.write("\n\n" + "-" * 50 + "\n\n")
                        else:
                            f.write("\n")
                
                print(f"已创建文件: {output_filename} (包含 {len(chunk_chapters)} 章节)")
                successful_files += 1
            except Exception as e:
                print(f"写入文件 {output_filename} 失败: {e}")
        
        print(f"总共分割为 {total_files} 个文件，成功生成 {successful_files} 个文件")
        return successful_files == total_files
        
    except Exception as e:
        print(f"分割EPUB文件时出错: {e}")
        traceback.print_exc()
        return False

# 以下是从txt_to_epub.py提取的函数
def create_chapter_html(chapter_title, content):
    """
    创建章节的HTML内容
    
    Args:
        chapter_title: 章节标题
        content: 章节内容
        
    Returns:
        str: 格式化的HTML内容
    """
    # 确保内容不为空
    if not content or not content.strip():
        print(f"章节 '{chapter_title}' 内容为空，将添加提示文本")
        content = "(此章节内容为空)"
    
    # 转义章节标题中的特殊字符
    chapter_title = chapter_title.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
    
    # 不使用BeautifulSoup，直接构建HTML
    html = '<?xml version="1.0" encoding="utf-8"?>\n'
    html += '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">\n'
    html += '<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="zh-CN">\n'
    html += '<head>\n'
    html += f'<title>{chapter_title}</title>\n'
    html += '<meta http-equiv="Content-Type" content="text/html; charset=utf-8" />\n'
    html += '</head>\n'
    html += '<body>\n'
    
    # 添加章节标题
    html += f'<h1>{chapter_title}</h1>\n'
    
    # 将内容分段并添加
    paragraphs = content.split('\n')
    for p_text in paragraphs:
        if p_text.strip():
            # 转义HTML特殊字符
            p_text = p_text.strip()
            p_text = p_text.replace('&', '&amp;')
            p_text = p_text.replace('<', '&lt;')
            p_text = p_text.replace('>', '&gt;')
            p_text = p_text.replace('"', '&quot;')
            html += f'<p>{p_text}</p>\n'
    
    html += '</body>\n'
    html += '</html>'
    
    return html

def parse_filename(filename):
    """
    从文件名中解析出小说名称、序号和章节名称
    
    Args:
        filename: 文件名字符串
        
    Returns:
        tuple: (小说名称, 章节序号, 章节标题)，解析失败则返回(None, None, None)
    """
    # 标准格式：小说名称_[序号]_章节名称.txt
    pattern = r"(.+?)_\[(\d+)\]_(.+?)\.txt$"
    match = re.match(pattern, filename)
    if match:
        novel_name = match.group(1)
        chapter_number = int(match.group(2))
        chapter_title = match.group(3)
        return novel_name, chapter_number, chapter_title
    
    # 尝试其他可能的格式: 小说名_[序号].txt，没有章节名
    pattern2 = r"(.+?)_\[(\d+)\]\.txt$"
    match = re.match(pattern2, filename)
    if match:
        novel_name = match.group(1)
        chapter_number = int(match.group(2))
        chapter_title = f"第{chapter_number}章"
        return novel_name, chapter_number, chapter_title
    
    # 尝试更宽松的格式：小说名称_序号_章节名称.txt（没有方括号）
    pattern3 = r"(.+?)_(\d+)_(.+?)\.txt$"
    match = re.match(pattern3, filename)
    if match:
        novel_name = match.group(1)
        chapter_number = int(match.group(2))
        chapter_title = match.group(3)
        return novel_name, chapter_number, chapter_title
        
    print(f"无法解析文件名: {filename}，不符合命名规则")
    return None, None, None

def merge_txt_to_epub(folder_path, output_path=None, novel_name=None, author=None, language='zh-CN'):
    """
    将多个TXT文件合并为一个EPUB电子书
    
    Args:
        folder_path: 包含TXT文件的文件夹路径
        output_path: 输出EPUB文件路径
        novel_name: 小说名称（可选）
        author: 作者名称（可选）
        language: 语言代码，默认为'zh-CN'
    
    Returns:
        bool: 操作是否成功
    """
    # 检查依赖
    deps_ok, msg = check_epub_dependencies()
    if not deps_ok:
        print(msg)
        return False
        
    try:
        # 处理输入参数
        folder_path = Path(folder_path)
        if not folder_path.exists() or not folder_path.is_dir():
            print(f"文件夹路径无效: {folder_path}")
            return False

        # 获取所有TXT文件
        txt_files = [f.name for f in folder_path.glob("*.txt") if f.is_file()]
        if not txt_files:
            print(f"文件夹中未找到TXT文件: {folder_path}")
            return False

        # 检测小说名称（如果未提供）
        if not novel_name:
            # 从文件名中推断小说名称
            for filename in txt_files:
                detected_name, _, _ = parse_filename(filename)
                if detected_name:
                    novel_name = detected_name
                    print(f"从文件名中检测到小说名称: {novel_name}")
                    break

            # 如果仍未检测到，使用文件夹名称
            if not novel_name:
                novel_name = folder_path.name
                print(f"使用文件夹名称作为小说名称: {novel_name}")

        # 构建输出路径（如果未提供）
        if not output_path:
            # 如果不是绝对路径，则基于文件夹路径
            safe_name = get_safe_filename(novel_name)
            output_path = folder_path.parent / f"{safe_name}.epub"
        else:
            output_path = Path(output_path)

        # 确保输出目录存在
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 创建EPUB书籍
        book = epub.EpubBook()
        
        # 设置元数据
        book.set_identifier(f"id-{uuid.uuid4()}")
        book.set_title(novel_name)
        if author:
            book.add_author(author)
        book.set_language(language)
        
        # 添加默认CSS样式
        style = """
        body {
            font-family: "Noto Sans CJK SC", "Source Han Sans CN", serif;
            margin: 5%;
            text-align: justify;
        }
        h1 {
            text-align: center;
            font-size: 1.5em;
            margin-bottom: 1em;
        }
        p {
            margin: 0.5em 0;
            line-height: 1.5;
            text-indent: 2em;
        }
        """
        
        css_file = epub.EpubItem(
            uid="style",
            file_name="style/style.css",
            media_type="text/css",
            content=style
        )
        book.add_item(css_file)
        
        # 解析文件，提取章节顺序和标题
        chapters_data = []
        for filename in txt_files:
            novel_name, chapter_number, chapter_title = parse_filename(filename)
            if chapter_number is None:
                # 如果无法解析，尝试从文件内容提取标题
                file_path = folder_path / filename
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        first_line = f.readline().strip()
                    if first_line:
                        if len(first_line) <= 50:  # 合理的标题长度
                            chapter_title = first_line
                        else:
                            chapter_title = filename  # 使用文件名作为标题
                    else:
                        chapter_title = filename
                    chapter_number = len(chapters_data) + 1  # 使用索引作为章节序号
                except Exception as e:
                    print(f"读取文件首行失败: {filename}, {e}")
                    chapter_title = filename
                    chapter_number = len(chapters_data) + 1
            
            chapters_data.append((filename, chapter_number, chapter_title))
        
        # 按章节序号排序
        chapters_data.sort(key=lambda x: x[1])
        
        # 创建章节
        epub_chapters = []
        spine = ['nav']
        toc = []
        
        for idx, (filename, _, chapter_title) in enumerate(chapters_data):
            try:
                # 读取章节内容
                with open(folder_path / filename, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # 创建HTML内容
                html_content = create_chapter_html(chapter_title, content)
                
                # 创建章节
                chapter_id = f"chapter_{idx+1}"
                chapter = epub.EpubHtml(
                    title=chapter_title,
                    file_name=f"chapters/chapter_{idx+1}.xhtml",
                    lang=language
                )
                chapter.content = html_content
                chapter.add_item(css_file)
                
                # 添加到书籍
                book.add_item(chapter)
                epub_chapters.append(chapter)
                spine.append(chapter)
                toc.append(chapter)
                
                print(f"已添加章节: {chapter_title}")
            except Exception as e:
                print(f"处理章节时出错: {filename}, {e}")
                # 继续处理其他章节
        
        # 添加导航文件
        book.toc = toc
        book.spine = spine
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        
        # 写入EPUB文件
        epub.write_epub(output_path, book)
        
        print(f"成功创建EPUB文件: {output_path}")
        return True
    
    except Exception as e:
        print(f"创建EPUB文件时出错: {e}")
        traceback.print_exc()
        return False

# 尝试导入其他模块
try:
    from .ai import AIEngine
    from .log import LogManager, get_log_manager
    # 导入可能需要的工具函数 (如果你的项目中有 utils.py)
    # from .utils import read_text_file, save_text_file
except ImportError as e:
    print(f"导入模块时出错，使用模拟类: {e}")
    class AIEngine:
        def generate_text(self, prompt, system_prompt):
            print(f"模拟 AI 调用: prompt={prompt[:50]}... system={system_prompt[:50]}...")
            time.sleep(1 + len(prompt) / 5000) # 模拟耗时
            simulated_len = int(len(prompt) * 0.4)
            # 确保模拟内容不为空
            if simulated_len <= 0:
                 return "模拟精简内容。"
            return "模拟精简内容。" * (simulated_len // 8)
    class LogManager:
        def __init__(self):
            # 模拟一个队列，但 CondenserWindow 不会直接使用它
            self._queue = queue.Queue()
        def info(self, msg): print(f"INFO: {msg}")
        def warning(self, msg): print(f"WARN: {msg}")
        def error(self, msg): print(f"ERROR: {msg}")
        def critical(self, msg): print(f"CRITICAL: {msg}")
        def debug(self, msg): print(f"DEBUG: {msg}")
        def exception(self, msg): print(f"EXCEPTION: {msg}")
        def get_logger(self): return self
    def get_log_manager(): return LogManager()

# 尝试导入EPUB处理模块 (先从项目内部导入，再尝试从src目录导入)
try:
    # 先尝试从相同包中导入
    try:
        from . import epub_splitter
        from . import txt_to_epub
        print("成功从当前包导入EPUB处理模块")
    except ImportError:
        # 尝试从项目根目录导入
        try:
            import epub_splitter
            import txt_to_epub
            print("成功从根目录导入EPUB处理模块")
        except ImportError:
            # 尝试从src.core导入 (根据项目结构可能的位置)
            try:
                from src.core import epub_splitter
                from src.core import txt_to_epub
                print("成功从src.core导入EPUB处理模块")
            except ImportError:
                # 如果都失败，使用模拟类
                print("无法导入EPUB处理模块，使用模拟类")
                # 假设 epub_splitter 和 txt_to_epub 也是类似的模拟或后续实现
                class MockEpubSplitter:
                     def split_epub(self, epub_path, output_dir, chapters_per_file=1):
                         print(f"模拟分割 EPUB: {epub_path} 到 {output_dir}")
                         time.sleep(1)
                         p = Path(output_dir)
                         p.mkdir(parents=True, exist_ok=True)
                         (p / f"{Path(epub_path).stem}_001_模拟章1.txt").write_text("章节1内容。"*10, encoding='utf-8')
                         (p / f"{Path(epub_path).stem}_002_模拟章2.txt").write_text("章节2内容。"*20, encoding='utf-8')
                         print("模拟分割完成")
                         return True
                epub_splitter = MockEpubSplitter()

                class MockTxtToEpub:
                     def merge_txt_to_epub(self, folder_path, output_path, novel_name=None, author=None):
                         print(f"模拟合并 TXT: {folder_path} 到 {output_path}")
                         time.sleep(1)
                         Path(output_path).touch()
                         print("模拟合并完成")
                         return True
                txt_to_epub = MockTxtToEpub()
except Exception as e:
    print(f"导入或创建EPUB处理模块时出错: {e}")
    # 确保epub_splitter和txt_to_epub始终存在
    if 'epub_splitter' not in globals():
        class MockEpubSplitter:
            def split_epub(self, epub_path, output_dir, chapters_per_file=1):
                print(f"错误恢复模拟分割 EPUB")
                return False
        epub_splitter = MockEpubSplitter()
    if 'txt_to_epub' not in globals():
        class MockTxtToEpub:
            def merge_txt_to_epub(self, folder_path, output_path, novel_name=None, author=None):
                print(f"错误恢复模拟合并 TXT")
                return False
        txt_to_epub = MockTxtToEpub()

# 定义工具函数，如果项目中没有实现
if 'read_text_file' not in globals():
    def read_text_file(file_path):
        print(f"使用内置函数读取文件: {file_path}")
        encodings = ['utf-8', 'gbk', 'gb2312']
        for enc in encodings:
            try:
                with open(file_path, 'r', encoding=enc) as f:
                    return f.read()
            except UnicodeDecodeError:
                continue
            except Exception as e:
                print(f"读取错误 ({enc}): {e}")
                raise # 抛出让上层捕获
        raise ValueError(f"无法以支持的编码读取文件: {file_path}")

if 'save_text_file' not in globals():
    def save_text_file(file_path, content):
        print(f"使用内置函数保存文件: {file_path}")
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)


class CondenserWindow(ctk.CTkToplevel if HAS_CTK else tk.Toplevel):
    """AI 精简功能窗口"""

    def __init__(self, parent, ai_engine: AIEngine, log_manager: LogManager):
        super().__init__(parent)
        self.parent = parent
        self.ai_engine = ai_engine
        self.log_manager = log_manager
        # 获取 logger 实例，用于在此类中记录日志
        self.logger = self.log_manager.get_logger()

        self.title("AI 小说精简工具")
        self.geometry("1000x700")
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # 状态变量
        self.mode_var = tk.StringVar(value="基础模式")
        self.input_path_var = tk.StringVar()
        self.output_path_var = tk.StringVar()
        self.min_ratio_var = tk.IntVar(value=30)
        self.max_ratio_var = tk.IntVar(value=50)
        self.force_regenerate_var = tk.BooleanVar(value=False)
        self.max_chunk_size_var = tk.IntVar(value=5000) # 新增：分块大小设置，默认5000字符
        self.threads_num_var = tk.IntVar(value=3) # 新增：线程数设置，默认3个线程
        self.processing_active = False
        self.worker_thread = None
        # 不再需要独立的 log_queue，直接使用 log_manager 记录

        self.bind("<Destroy>", self._on_destroy)

        self._create_ui()
        self.logger.info("AI精简窗口已打开")

    def _create_ui(self):
        """创建用户界面"""
        # 确保使用正确作用域中的类
        if HAS_CTK:
            # 如果有customtkinter，使用ctk的类
            FrameClass = ctk.CTkFrame 
            LabelClass = ctk.CTkLabel
            ButtonClass = ctk.CTkButton
            EntryClass = ctk.CTkEntry
            RadioButtonClass = ctk.CTkRadioButton
            CheckBoxClass = ctk.CTkCheckBox
            ProgressBarClass = ctk.CTkProgressBar
            TextboxClass = ctk.CTkTextbox
        else:
            # 如果没有customtkinter，使用之前定义的模拟类
            FrameClass = globals()['CTkFrame']
            LabelClass = globals()['CTkLabel']
            ButtonClass = globals()['CTkButton']
            EntryClass = globals()['CTkEntry']
            RadioButtonClass = globals()['CTkRadioButton']
            CheckBoxClass = globals()['CTkCheckBox']
            ProgressBarClass = globals()['CTkProgressBar']
            TextboxClass = globals()['CTkTextbox']

        main_frame = FrameClass(self)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
        main_frame.grid_columnconfigure(1, weight=1)
        main_frame.grid_rowconfigure(0, weight=1)

        # --- 左侧控制面板 ---
        left_panel = FrameClass(main_frame)
        left_panel.grid(row=0, column=0, padx=(0, 10), pady=5, sticky="nsew")

        # 模式选择
        mode_frame = FrameClass(left_panel)
        mode_frame.pack(fill=tk.X, pady=5)
        LabelClass(mode_frame, text="处理模式:").pack(side=tk.LEFT, padx=5)
        basic_rb = RadioButtonClass(mode_frame, text="基础模式 (TXT)", variable=self.mode_var, value="基础模式", command=self._on_mode_change)
        basic_rb.pack(side=tk.LEFT, padx=5)
        advanced_rb = RadioButtonClass(mode_frame, text="高级模式 (EPUB)", variable=self.mode_var, value="高级模式", command=self._on_mode_change)
        advanced_rb.pack(side=tk.LEFT, padx=5)

        # --- 基础模式控件 ---
        self.basic_frame = FrameClass(left_panel)

        input_frame_basic = FrameClass(self.basic_frame)
        input_frame_basic.pack(fill=tk.X, pady=5)
        self.input_label_basic = LabelClass(input_frame_basic, text="输入 (TXT文件/目录):")
        self.input_label_basic.pack(side=tk.LEFT, padx=5)
        input_entry_basic = EntryClass(input_frame_basic, textvariable=self.input_path_var, state='readonly')
        input_entry_basic.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        # 添加两个独立的按钮，分别用于选择文件和目录
        browse_input_basic_file_btn = ButtonClass(input_frame_basic, text="选择文件", width=70, command=self._browse_input_basic_file)
        browse_input_basic_file_btn.pack(side=tk.LEFT, padx=(0, 2))
        browse_input_basic_dir_btn = ButtonClass(input_frame_basic, text="选择目录", width=70, command=self._browse_input_basic)
        browse_input_basic_dir_btn.pack(side=tk.LEFT)

        output_frame_basic = FrameClass(self.basic_frame)
        output_frame_basic.pack(fill=tk.X, pady=5)
        self.output_label_basic = LabelClass(output_frame_basic, text="输出目录 (脱水TXT):")
        self.output_label_basic.pack(side=tk.LEFT, padx=5)
        output_entry_basic = EntryClass(output_frame_basic, textvariable=self.output_path_var, state='readonly')
        output_entry_basic.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        browse_output_basic_btn = ButtonClass(output_frame_basic, text="浏览...", width=60, command=self._browse_output_basic)
        browse_output_basic_btn.pack(side=tk.LEFT)

        # --- 高级模式控件 ---
        self.advanced_frame = FrameClass(left_panel)

        input_frame_adv = FrameClass(self.advanced_frame)
        input_frame_adv.pack(fill=tk.X, pady=5)
        self.input_label_adv = LabelClass(input_frame_adv, text="输入 (EPUB文件):")
        self.input_label_adv.pack(side=tk.LEFT, padx=5)
        input_entry_adv = EntryClass(input_frame_adv, textvariable=self.input_path_var, state='readonly')
        input_entry_adv.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        browse_input_adv_btn = ButtonClass(input_frame_adv, text="浏览...", width=60, command=self._browse_input_adv)
        browse_input_adv_btn.pack(side=tk.LEFT)

        output_frame_adv = FrameClass(self.advanced_frame)
        output_frame_adv.pack(fill=tk.X, pady=5)
        self.output_label_adv = LabelClass(output_frame_adv, text="输出基目录:")
        self.output_label_adv.pack(side=tk.LEFT, padx=5)
        output_entry_adv = EntryClass(output_frame_adv, textvariable=self.output_path_var, state='readonly')
        output_entry_adv.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        browse_output_adv_btn = ButtonClass(output_frame_adv, text="浏览...", width=60, command=self._browse_output_adv)
        browse_output_adv_btn.pack(side=tk.LEFT)

        # (可以添加高级模式的其他设置控件)
        LabelClass(self.advanced_frame, text="高级模式详细设置待添加...").pack(pady=10)

        # --- 通用设置 ---
        common_settings_frame = FrameClass(left_panel)
        common_settings_frame.pack(fill=tk.X, pady=10)
        # 保存为类属性
        self.common_settings_frame = common_settings_frame

        ratio_frame = FrameClass(common_settings_frame)
        ratio_frame.pack(fill=tk.X)
        LabelClass(ratio_frame, text="脱水比例 (%):").pack(side=tk.LEFT, padx=5)
        # 使用 EntryClass 或 tk.Spinbox
        if HAS_CTK:
             # CTk 没有直接的 Spinbox, 用 Entry 模拟或依赖 tk.Spinbox
             min_spin = tk.Spinbox(ratio_frame, from_=10, to=90, width=5, textvariable=self.min_ratio_var)
             max_spin = tk.Spinbox(ratio_frame, from_=10, to=95, width=5, textvariable=self.max_ratio_var)
        else:
            min_spin = tk.Spinbox(ratio_frame, from_=10, to=90, width=5, textvariable=self.min_ratio_var)
            max_spin = tk.Spinbox(ratio_frame, from_=10, to=95, width=5, textvariable=self.max_ratio_var)

        min_spin.pack(side=tk.LEFT, padx=2)
        LabelClass(ratio_frame, text="-").pack(side=tk.LEFT, padx=2)
        max_spin.pack(side=tk.LEFT, padx=2)

        # 新增：添加分块大小设置控件
        chunk_frame = FrameClass(common_settings_frame)
        chunk_frame.pack(fill=tk.X, pady=3)
        LabelClass(chunk_frame, text="分块大小 (字符):").pack(side=tk.LEFT, padx=5)
        if HAS_CTK:
             chunk_spin = tk.Spinbox(chunk_frame, from_=1000, to=20000, increment=1000, width=6, textvariable=self.max_chunk_size_var)
        else:
             chunk_spin = tk.Spinbox(chunk_frame, from_=1000, to=20000, increment=1000, width=6, textvariable=self.max_chunk_size_var)
        chunk_spin.pack(side=tk.LEFT, padx=2)
        
        # 新增：添加线程数设置控件
        threads_frame = FrameClass(common_settings_frame)
        threads_frame.pack(fill=tk.X, pady=3)
        LabelClass(threads_frame, text="并发线程数:").pack(side=tk.LEFT, padx=5)
        if HAS_CTK:
             threads_spin = tk.Spinbox(threads_frame, from_=1, to=10, width=5, textvariable=self.threads_num_var)
        else:
             threads_spin = tk.Spinbox(threads_frame, from_=1, to=10, width=5, textvariable=self.threads_num_var)
        threads_spin.pack(side=tk.LEFT, padx=2)
        
        force_check = CheckBoxClass(common_settings_frame, text="强制重新生成 (覆盖已存在文件)", variable=self.force_regenerate_var)
        force_check.pack(anchor="w", pady=5)

        # --- 文件列表 (基础模式用) ---
        self.files_frame = FrameClass(left_panel)
        LabelClass(self.files_frame, text="待处理文件:").pack(anchor='w')
        if HAS_CTK:
             self.files_text = TextboxClass(self.files_frame, height=100, state='disabled', wrap='none')
             self.files_text.pack(fill=tk.BOTH, expand=True)
        else:
             files_text_frame = tk.Frame(self.files_frame)
             files_text_frame.pack(fill=tk.BOTH, expand=True)
             self.files_text = tk.Text(files_text_frame, height=8, state='disabled', wrap='none')
             yscroll = ttk.Scrollbar(files_text_frame, orient=tk.VERTICAL, command=self.files_text.yview)
             xscroll = ttk.Scrollbar(files_text_frame, orient=tk.HORIZONTAL, command=self.files_text.xview)
             self.files_text.config(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
             yscroll.pack(side=tk.RIGHT, fill=tk.Y)
             xscroll.pack(side=tk.BOTTOM, fill=tk.X)
             self.files_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # --- 进度与控制 ---
        progress_frame = FrameClass(left_panel)
        progress_frame.pack(fill=tk.X, pady=10)
        # 保存为类属性
        self.progress_frame = progress_frame

        self.progress_bar = ProgressBarClass(progress_frame, orientation='horizontal', mode='determinate')
        if HAS_CTK:
             self.progress_bar.set(0)
        else:
             self.progress_bar.config(value=0)
        self.progress_bar.pack(fill=tk.X, expand=True, side=tk.LEFT, padx=(0, 10))

        self.start_button = ButtonClass(progress_frame, text="开始处理", command=self._start_processing)
        self.start_button.pack(side=tk.LEFT)
        self.stop_button = ButtonClass(progress_frame, text="停止", command=self._stop_processing, state='disabled')
        self.stop_button.pack(side=tk.LEFT, padx=(5, 0))

        self.status_label = LabelClass(left_panel, text="状态: 就绪")
        self.status_label.pack(anchor="w")

        # --- 右侧日志面板 ---
        # 日志将通过LogManager显示在主窗口的日志区域
        # 这里可以留空或添加提示
        right_panel = FrameClass(main_frame)
        right_panel.grid(row=0, column=1, padx=(10, 0), pady=5, sticky="nsew")
        LabelClass(right_panel, text="处理日志将显示在主窗口日志区域").pack(padx=10, pady=10)


        self._on_mode_change() # 根据默认模式初始化UI

    def _on_mode_change(self):
        """切换基础/高级模式时更新UI"""
        mode = self.mode_var.get()
        if mode == "基础模式":
            # pack_forget 安全地隐藏控件
            if self.advanced_frame.winfo_ismapped(): self.advanced_frame.pack_forget()
            # 确保 basic_frame 未被隐藏时才 pack
            if not self.basic_frame.winfo_ismapped(): self.basic_frame.pack(fill=tk.X, pady=5, before=self.common_settings_frame)
            # 确保 files_frame 未被隐藏时才 pack
            if not self.files_frame.winfo_ismapped(): self.files_frame.pack(fill=tk.BOTH, expand=True, pady=5, before=self.progress_frame)

            # 安全地更新标签文本
            if hasattr(self, 'input_label_basic') and self.input_label_basic.winfo_exists():
                self.input_label_basic.configure(text="输入 (TXT文件/目录):")
            if hasattr(self, 'output_label_basic') and self.output_label_basic.winfo_exists():
                self.output_label_basic.configure(text="输出目录 (脱水TXT):")

        elif mode == "高级模式":
            if self.basic_frame.winfo_ismapped(): self.basic_frame.pack_forget()
            if self.files_frame.winfo_ismapped(): self.files_frame.pack_forget()
            if not self.advanced_frame.winfo_ismapped(): self.advanced_frame.pack(fill=tk.X, pady=5, before=self.common_settings_frame)

            if hasattr(self, 'input_label_adv') and self.input_label_adv.winfo_exists():
                self.input_label_adv.configure(text="输入 (EPUB文件):")
            if hasattr(self, 'output_label_adv') and self.output_label_adv.winfo_exists():
                self.output_label_adv.configure(text="输出基目录:")

        # 清空路径并重置文件列表
        self.input_path_var.set("")
        self.output_path_var.set("")
        if hasattr(self, 'files_text') and self.files_text.winfo_exists():
            try:
                 self.files_text.configure(state='normal')
                 self.files_text.delete('1.0', tk.END)
                 self.files_text.configure(state='disabled')
            except tk.TclError: pass # 忽略可能的错误

    def _browse_input_basic(self):
        """浏览基础模式的输入目录"""
        path = filedialog.askdirectory(title="选择TXT文件所在目录", parent=self)
        if path:
            self._load_txt_files_from_dir(path)
            self.input_path_var.set(path)
            input_p = Path(path)
            # 设置默认输出目录
            try:
                default_output = input_p / "condensed"
                self.output_path_var.set(str(default_output))
            except Exception as e:
                self.logger.error(f"设置默认输出目录时出错: {e}")
                self.output_path_var.set("") # 清空以防万一
    
    def _browse_input_basic_file(self):
        """浏览基础模式的输入文件"""
        path = filedialog.askopenfilename(title="选择TXT文件", filetypes=[("Text files", "*.txt")], parent=self)
        if path:
            self._display_single_file(path)
            self.input_path_var.set(path)
            input_p = Path(path)
            # 设置默认输出目录
            try:
                default_output = input_p.parent / "condensed"
                self.output_path_var.set(str(default_output))
            except Exception as e:
                self.logger.error(f"设置默认输出目录时出错: {e}")
                self.output_path_var.set("") # 清空以防万一

    def _browse_output_basic(self):
        """浏览基础模式的输出目录"""
        # 建议初始目录为当前输入目录的父目录或当前输出目录
        initial_dir = ""
        current_output = self.output_path_var.get()
        if current_output and Path(current_output).exists():
             initial_dir = str(Path(current_output).parent)
        elif self.input_path_var.get():
             initial_dir = str(Path(self.input_path_var.get()).parent)

        path = filedialog.askdirectory(title="选择脱水TXT文件的输出目录", initialdir=initial_dir, parent=self)
        if path:
            self.output_path_var.set(path)

    def _browse_input_adv(self):
        """浏览高级模式的输入 (EPUB文件)"""
        path = filedialog.askopenfilename(title="选择EPUB文件", filetypes=[("EPUB files", "*.epub")], parent=self)
        if path:
            self.input_path_var.set(path)
            input_p = Path(path)
            try:
                # 默认输出基目录为EPUB文件所在目录下的同名目录
                default_output = input_p.parent / input_p.stem
                self.output_path_var.set(str(default_output))
            except Exception as e:
                self.logger.error(f"设置默认输出目录时出错: {e}")
                self.output_path_var.set("")

    def _browse_output_adv(self):
        """浏览高级模式的输出基目录"""
        initial_dir = ""
        current_output = self.output_path_var.get()
        if current_output and Path(current_output).exists():
             initial_dir = str(Path(current_output).parent)
        elif self.input_path_var.get():
             initial_dir = str(Path(self.input_path_var.get()).parent)

        path = filedialog.askdirectory(title="选择输出基目录", initialdir=initial_dir, parent=self)
        if path:
            self.output_path_var.set(path)

    def _load_txt_files_from_dir(self, dir_path):
         """加载目录中的TXT文件到列表框"""
         if not hasattr(self, 'files_text') or not self.files_text.winfo_exists(): return
         try:
             txt_files = sorted([f.name for f in Path(dir_path).glob("*.txt") if f.is_file()]) # 按名称排序
             self.files_text.configure(state='normal')
             self.files_text.delete('1.0', tk.END)
             if txt_files:
                 self.files_text.insert('1.0', "\n".join(txt_files))
                 self.logger.info(f"从 {dir_path} 加载了 {len(txt_files)} 个TXT文件")
             else:
                 self.files_text.insert('1.0', "<目录中未找到TXT文件>")
                 self.logger.warning(f"目录 {dir_path} 中未找到TXT文件")
             self.files_text.configure(state='disabled')
         except Exception as e:
             self.logger.error(f"加载TXT文件列表时出错: {e}")
             messagebox.showerror("错误", f"加载文件列表失败: {e}", parent=self)
             try: # 尝试清理文本框
                 self.files_text.configure(state='normal')
                 self.files_text.delete('1.0', tk.END)
                 self.files_text.insert('1.0', "<加载失败>")
                 self.files_text.configure(state='disabled')
             except: pass # 忽略清理过程中的错误

    def _display_single_file(self, file_path):
        """在文件列表框显示单个文件名"""
        if not hasattr(self, 'files_text') or not self.files_text.winfo_exists(): return
        try:
            self.files_text.configure(state='normal')
            self.files_text.delete('1.0', tk.END)
            self.files_text.insert('1.0', Path(file_path).name)
            self.files_text.configure(state='disabled')
            self.logger.info(f"选择了单个文件: {file_path}")
        except Exception as e:
            self.logger.error(f"显示单个文件时出错: {e}")

    # _add_log 方法不再需要，直接使用 self.logger 记录

    def _update_progress(self, value, text):
         """在主线程中安全更新UI"""
         def task():
            try:
                # 检查控件是否存在
                progress_bar_exists = hasattr(self, 'progress_bar') and self.progress_bar.winfo_exists()
                status_label_exists = hasattr(self, 'status_label') and self.status_label.winfo_exists()

                if not progress_bar_exists and not status_label_exists:
                    return # 如果两个控件都不存在，则无需更新

                if progress_bar_exists:
                    # 规范化进度值
                    progress_value = max(0, min(100, int(value)))
                    if HAS_CTK:
                        self.progress_bar.set(progress_value / 100.0)
                    else:
                        self.progress_bar['value'] = progress_value

                if status_label_exists:
                    self.status_label.configure(text=f"状态: {text}")

                # 仅当至少一个控件存在时才强制更新
                if progress_bar_exists or status_label_exists:
                    self.update_idletasks()
            except tk.TclError as e:
                 # 捕获窗口关闭等Tcl错误
                 self.logger.debug(f"更新进度UI时发生 TclError (可能窗口已关闭): {e}")
            except Exception as e:
                 # 捕获其他意外错误
                 self.logger.error(f"更新进度UI时出错: {e}", exc_info=True)
         # 使用 after 将任务委托给主线程执行
         self.after(0, task)

    def _start_processing(self):
        """开始处理任务"""
        if self.processing_active:
            messagebox.showwarning("处理中", "当前已有任务正在处理。", parent=self)
            return

        mode = self.mode_var.get()
        input_path = self.input_path_var.get()
        output_path = self.output_path_var.get()

        if not input_path:
            messagebox.showerror("错误", f"请选择有效的输入{'文件/目录' if mode == '基础模式' else 'EPUB文件'}!", parent=self)
            return
        # 更严格地检查输入路径是否存在
        input_p = Path(input_path)
        if not input_p.exists():
             messagebox.showerror("错误", f"输入路径不存在: {input_path}", parent=self)
             return
        if mode == "基础模式" and not (input_p.is_file() or input_p.is_dir()):
             messagebox.showerror("错误", f"基础模式需要选择TXT文件或目录: {input_path}", parent=self)
             return
        if mode == "高级模式" and not (input_p.is_file() and input_p.suffix.lower() == '.epub'):
             messagebox.showerror("错误", f"高级模式需要选择EPUB文件: {input_path}", parent=self)
             return


        if not output_path:
             messagebox.showerror("错误", f"请选择有效的输出{'目录' if mode == '基础模式' else '基目录'}!", parent=self)
             return

        # 确保输出目录存在
        try:
            Path(output_path).mkdir(parents=True, exist_ok=True)
        except Exception as e:
             messagebox.showerror("错误", f"无法创建输出目录 '{output_path}': {e}", parent=self)
             return

        self.processing_active = True
        self.start_button.configure(state='disabled')
        self.stop_button.configure(state='normal')
        # 安全地设置进度条初始值
        self._update_progress(0, "开始处理...")
        self.logger.info(f"开始 {mode} 处理...") # 使用 logger 记录

        # 创建并启动工作线程
        if mode == "基础模式":
            target_func = self._run_basic_mode
        else: # 高级模式
            target_func = self._run_advanced_mode
            # 可以在这里添加对 epub_splitter 和 txt_to_epub 真实性的检查（如果需要）
            # if isinstance(epub_splitter, MockEpubSplitter) or isinstance(txt_to_epub, MockTxtToEpub):
            #    self.logger.warning("高级模式的部分功能为模拟实现")

        self.worker_thread = threading.Thread(target=target_func, args=(input_path, output_path), daemon=True)
        self.worker_thread.start()

    def _stop_processing(self):
        """停止处理任务"""
        if not self.processing_active:
            return
        self.processing_active = False # 设置停止标志
        self.stop_button.configure(state='disabled')
        self.logger.warning("收到停止信号，正在尝试停止...") # 使用 logger 记录

    def _processing_finished(self, success=True, message="处理完成"):
         """处理完成后的UI更新 (委托给主线程)"""
         def task():
            # 确保控件仍然存在
            start_exists = hasattr(self, 'start_button') and self.start_button.winfo_exists()
            stop_exists = hasattr(self, 'stop_button') and self.stop_button.winfo_exists()

            # 重置 processing_active 标志
            self.processing_active = False

            if start_exists: self.start_button.configure(state='normal')
            if stop_exists: self.stop_button.configure(state='disabled')

            final_progress = 100
            current_progress = 0
            try:
                 # 安全地获取当前进度
                 if HAS_CTK and hasattr(self, 'progress_bar') and self.progress_bar.winfo_exists():
                      current_progress = self.progress_bar.get() * 100
                 elif not HAS_CTK and hasattr(self, 'progress_bar') and self.progress_bar.winfo_exists():
                      current_progress = self.progress_bar['value']
            except Exception as e:
                 self.logger.debug(f"获取当前进度时出错: {e}")

            if not success:
                 final_progress = int(current_progress) # 失败时停留在当前进度

            self._update_progress(final_progress, message) # 更新进度条和状态

            # 根据成功与否记录日志和显示消息框
            if success:
                 self.logger.info(f"处理成功完成: {message}")
                 messagebox.showinfo("完成", message, parent=self)
            else:
                 self.logger.error(f"处理失败: {message}")
                 messagebox.showerror("失败", f"处理失败: {message}", parent=self)
         self.after(0, task)

    def _on_close(self):
        """关闭窗口时的处理"""
        if self.processing_active:
            if messagebox.askyesno("确认关闭", "正在处理任务，确定要关闭窗口吗？\n（后台任务将被尝试停止）", icon='warning', parent=self):
                self._stop_processing() # 尝试设置停止标志
                # 不直接 destroy，让 _on_destroy 处理
                self.after(100, self.destroy) # 稍等一下再销毁
            # else: # 用户取消，则不关闭
        else:
             self.destroy() # 没有任务运行时直接关闭

    def _on_destroy(self, event=None):
        """窗口销毁时的清理"""
        self.processing_active = False # 确保停止标志被设置
        # 如果有其他需要清理的资源，在此处处理
        self.logger.info("AI精简窗口已关闭")


    # --- 工作线程执行的函数将在下一步填充 ---
    def _run_basic_mode(self, input_path_str, output_dir_str):
        """基础模式: 处理单个TXT文件或目录中的所有TXT文件，将处理结果保存到输出目录"""
        self.logger.info(f"基础模式开始: 输入={input_path_str}, 输出={output_dir_str}")
        
        try:
            input_path = Path(input_path_str)
            output_dir = Path(output_dir_str)
            
            # 确保输出目录存在
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # 确定要处理的文件列表
            files_to_process = []
            if input_path.is_file():
                # 单个文件
                if input_path.suffix.lower() == '.txt':
                    files_to_process.append(input_path)
                else:
                    raise ValueError(f"非TXT文件: {input_path}")
            elif input_path.is_dir():
                # 目录中的所有TXT文件
                files_to_process = list(input_path.glob("*.txt"))
                if not files_to_process:
                    raise ValueError(f"目录中未找到TXT文件: {input_path}")
            else:
                raise ValueError(f"无效的输入路径: {input_path}")
            
            # 开始处理文件
            total_files = len(files_to_process)
            self.logger.info(f"共找到 {total_files} 个TXT文件待处理")
            
            # 更新进度
            self.after(0, self._update_progress, 5, f"准备处理 {total_files} 个文件...")
            
            # 使用线程池并发处理文件
            processed_count = 0
            processed_successful = 0
            errors = []
            
            # 获取脱水比例设置
            min_ratio = self.min_ratio_var.get()
            max_ratio = self.max_ratio_var.get()
            force_regenerate = self.force_regenerate_var.get()
            
            # 获取用户设置的线程数
            threads_num = self.threads_num_var.get()
            self.logger.info(f"基础模式处理，并发线程数: {threads_num}")
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(total_files, threads_num)) as executor:
                # 提交所有任务
                future_to_file = {
                    executor.submit(
                        self._process_single_txt_task, 
                        file_path, 
                        output_dir,
                        min_ratio,
                        max_ratio,
                        force_regenerate
                    ): file_path for file_path in files_to_process
                }
                
                # 处理完成的任务
                for future in concurrent.futures.as_completed(future_to_file):
                    if not self.processing_active:
                        # 用户停止了处理
                        raise InterruptedError("用户停止")
                    
                    file_path = future_to_file[future]
                    processed_count += 1
                    progress = 5 + int((processed_count / total_files) * 90)
                    
                    try:
                        success, message = future.result()
                        if success:
                            processed_successful += 1
                            self.logger.info(f"已处理文件 ({processed_count}/{total_files}): {file_path.name} - {message}")
                        else:
                            errors.append(f"{file_path.name}: {message}")
                            self.logger.error(f"处理文件失败 ({processed_count}/{total_files}): {file_path.name} - {message}")
                    except Exception as e:
                        errors.append(f"{file_path.name}: {str(e)}")
                        self.logger.error(f"处理文件异常 ({processed_count}/{total_files}): {file_path.name} - {str(e)}")
                    
                    # 更新进度
                    self.after(0, self._update_progress, progress, f"处理中: {processed_count}/{total_files} - {file_path.name}")
            
            # 处理完成
            if errors:
                error_msg = f"完成但有错误 ({processed_successful}/{total_files} 成功)"
                self.logger.warning(f"{error_msg}. 错误列表: {', '.join(errors)}")
                self.after(0, self._processing_finished, False, error_msg)
            else:
                success_msg = f"所有文件处理完成 ({processed_successful}/{total_files})"
                self.logger.info(success_msg)
                self.after(0, self._processing_finished, True, success_msg)
            
        except InterruptedError:
            self.logger.warning("基础模式处理被用户停止")
            self.after(0, self._processing_finished, False, "处理被停止")
        except Exception as e:
            self.logger.critical(f"基础模式处理出错: {e}", exc_info=True)
            self.after(0, self._processing_finished, False, f"处理出错: {e}")


    def _process_single_txt_task(self, file_path: Path, output_dir: Path, min_ratio: int, max_ratio: int, force_regenerate: bool):
        """处理单个TXT文件任务"""
        self.logger.debug(f"处理文件: {file_path.name}")
        
        # 构建输出文件路径 (使用与输入文件相同的文件名，但在指定输出目录下)
        output_path = output_dir / f"{file_path.stem}_condensed.txt"
        
        # 如果文件已存在且不强制重新生成，则跳过
        if output_path.exists() and not force_regenerate:
            return True, "已存在，跳过"
        
        try:
            # 读取文件内容
            try:
                # 尝试多种编码读取文件
                encodings = ['utf-8', 'gbk', 'gb2312']
                content = None
                error_msg = None
                
                for enc in encodings:
                    try:
                        with open(file_path, 'r', encoding=enc) as f:
                            content = f.read()
                        break
                    except UnicodeDecodeError:
                        continue
                    except Exception as e:
                        error_msg = f"读取出错 ({enc}): {e}"
                        break
                
                if content is None:
                    if error_msg:
                        return False, error_msg
                    else:
                        return False, f"无法以支持的编码读取文件"
            except Exception as e:
                return False, f"读取文件时出错: {e}"
            
            # 检查文件大小和内容有效性
            if not content.strip():
                return False, "文件内容为空"
            
            # 使用AI进行内容精简
            try:
                condensed_content = self._condense_text_internal(content, min_ratio, max_ratio)
                if condensed_content is None:  # 处理被中断
                    return False, "处理被中断"
                if not condensed_content.strip():
                    return False, "AI返回内容为空"
            except Exception as e:
                return False, f"调用AI精简时出错: {e}"
            
            # 保存精简后的内容
            try:
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(condensed_content)
            except Exception as e:
                return False, f"保存输出文件时出错: {e}"
            
            # 处理成功
            return True, f"成功精简 (输出: {output_path.name})"
            
        except Exception as e:
            return False, f"处理文件时出现未知错误: {e}"

    def _condense_text_internal(self, text, min_ratio, max_ratio, is_chunk=False, chunk_index=0, total_chunks=0):
        """使用AI引擎精简文本内容"""
        if not self.processing_active:  # 检查是否应停止处理
            return None
        
        # 如果文本过短，可能不需要精简
        if len(text) < 500:
            return text
            
        # 获取用户设置的分块大小和线程数
        max_chunk_size = self.max_chunk_size_var.get()
        threads_num = self.threads_num_var.get()
        
        text_length = len(text)
        
        # 如果文本长度超过分块大小，则进行分块处理
        if text_length > max_chunk_size:
            self.logger.info(f"文本长度为 {text_length} 字符，将分块处理...")
            
            # 计算分块数和每块大小
            total_sub_chunks = (text_length + max_chunk_size - 1) // max_chunk_size
            self.logger.info(f"将分为 {total_sub_chunks} 个子块进行处理，并发线程数: {threads_num}")
            
            # 子块信息，包含原始文本、位置等信息
            sub_chunks_info = []
            
            # 准备子块信息
            for i in range(total_sub_chunks):
                # 计算当前分块的起止位置
                start_pos = i * max_chunk_size
                end_pos = min(start_pos + max_chunk_size, text_length)
                sub_chunk = text[start_pos:end_pos]
                
                # 为分块添加索引信息
                current_sub_chunk_index = i + 1
                
                # 计算当前分块的目标精简比例（与整体保持一致）
                sub_min_target_length = int(len(sub_chunk) * min_ratio / 100)
                sub_max_target_length = int(len(sub_chunk) * max_ratio / 100)
                
                # 创建子分块的上下文信息
                sub_is_chunk = True
                sub_chunk_index = current_sub_chunk_index
                sub_total_chunks = total_sub_chunks
                
                # 如果原来就是一个大块中的一部分，则更新索引信息
                if is_chunk:
                    sub_chunk_info = f"【这是第{chunk_index}部分的第{current_sub_chunk_index}/{total_sub_chunks}子块，总共{total_chunks}部分】"
                else:
                    sub_chunk_info = f"【这是第{current_sub_chunk_index}/{total_sub_chunks}子块】"
                
                # 将子块信息添加到列表
                sub_chunks_info.append({
                    'index': i,  # 原始索引，用于后续排序
                    'text': sub_chunk,
                    'sub_chunk_info': sub_chunk_info,
                    'min_target_length': sub_min_target_length,
                    'max_target_length': sub_max_target_length,
                    'range': f"{start_pos}-{end_pos}"
                })
                
                self.logger.info(f"准备子块 {current_sub_chunk_index}/{total_sub_chunks}，字符范围: {start_pos}-{end_pos}")
            
            # 使用线程池并发处理子块
            results = []  # 存储处理结果
            
            def process_sub_chunk(chunk_info):
                """处理单个子块的函数"""
                if not self.processing_active:  # 检查是否应停止处理
                    return None
                
                sub_chunk = chunk_info['text']
                sub_chunk_info = chunk_info['sub_chunk_info']
                sub_min_target_length = chunk_info['min_target_length']
                sub_max_target_length = chunk_info['max_target_length']
                chunk_range = chunk_info['range']
                orig_index = chunk_info['index']
                
                self.logger.info(f"开始处理子块 {orig_index+1}/{total_sub_chunks}，字符范围: {chunk_range}")
                
                # 构建系统提示，指导AI如何进行内容精简
                exact_target_length = (sub_min_target_length + sub_max_target_length) // 2
                
                system_prompt = f"""你是一个专业的小说精简助手，擅长保留小说核心情节同时减少文本量。
请遵循以下原则：
1. 保留故事的主要情节、关键场景和角色发展。
2. 去除不必要的场景描写、重复内容和冗长对话。
3. 减少修饰性语言，但保持文风一致性。
4. 【重要】目标精简比例为原文的{min_ratio}%到{max_ratio}%。
5. 【字数要求-非常重要】你必须输出{exact_target_length}±{(sub_max_target_length-exact_target_length)//2}个字符。
   - 最少字符数: {sub_min_target_length}
   - 最理想字符数: {exact_target_length}
   - 最大字符数: {sub_max_target_length}
6. 【严格警告】禁止输出少于{sub_min_target_length}个字符！如果你输出的内容不足这个字数，将被视为失败。
7. 保持人物对话的自然流畅和逻辑性。
8. 返回完整的精简后内容，不要包含解释、总结或其他非小说内容。
9. 不要遗漏重要情节转折点和关键角色互动。
10. 尽量保留原有段落结构，使精简后的内容仍易于阅读。
11. 【再次强调】计算并确保你的输出字符数在{sub_min_target_length}到{sub_max_target_length}之间，最好接近{exact_target_length}个字符。"""

                # 最大重试次数
                max_retries = 3
                
                # 处理当前子块
                for retry in range(max_retries):
                    # 构建用户提示
                    user_prompt = f"""请对以下小说内容进行精简。

【重要字数要求】
- 必须输出的字符数范围: {sub_min_target_length}-{sub_max_target_length}字符
- 理想字符数: {exact_target_length}字符
- 字符数不足{sub_min_target_length}将被视为失败

目标精简比例：原文的{min_ratio}%-{max_ratio}%

小说片段：{sub_chunk_info}

{sub_chunk}

注意事项:
1. 请直接返回精简后的内容，不要添加任何解释、概述或其他额外文本
2. 必须输出{sub_min_target_length}-{sub_max_target_length}字符，最好接近{exact_target_length}字符
3. 保留所有关键情节、人物对话和情感发展
4. 保持原文风格，避免过度总结或简化"""

                    # 调用AI引擎生成精简内容
                    self.logger.info(f"调用AI精简子块，子块长度: {len(sub_chunk)}" + (f"，第{retry+1}次尝试" if retry > 0 else ""))
                    try:
                        condensed_sub_text = self.ai_engine.generate_text(user_prompt, system_prompt)
                        self.logger.info(f"AI精简子块完成，精简后长度: {len(condensed_sub_text)}")
                        
                        # 计算实际精简比例
                        if sub_chunk and condensed_sub_text:
                            ratio = (len(condensed_sub_text) / len(sub_chunk)) * 100
                            self.logger.info(f"子块精简比例: {ratio:.2f}% (目标: {min_ratio}%-{max_ratio}%)")
                            
                            # 检查是否符合目标比例
                            if ratio < min_ratio and retry < max_retries - 1:
                                self.logger.warning(f"子块精简比例过低: {ratio:.2f}% < {min_ratio}%，将重试...")
                                # 每次重试都调整提示词强调更长内容，增加强调程度
                                retry_emphasis = ["重要提醒", "严重警告", "最终警告"][min(retry, 2)]
                                system_prompt += f"\n\n【{retry_emphasis}】你输出的内容过少！必须至少达到{sub_min_target_length}个字符，目标为{exact_target_length}个字符。你上次只输出了{len(condensed_sub_text)}个字符，达到了原文的{ratio:.2f}%，但最低要求是{min_ratio}%。请确保输出足够的内容！"
                                continue
                            
                            # 如果是最后一次尝试或者比例符合要求，接受结果
                            return {
                                'index': orig_index,  # 保存原始索引
                                'text': condensed_sub_text,
                                'success': True
                            }
                    except Exception as e:
                        self.logger.error(f"处理子块 {orig_index+1}/{total_sub_chunks} 出错: {e}")
                        if retry < max_retries - 1:
                            self.logger.info(f"将重试子块 {orig_index+1}/{total_sub_chunks}...")
                            continue
                
                # 如果所有重试都失败，则使用原始子块内容（为了保持故事完整性）
                self.logger.warning(f"无法精简子块 {orig_index+1}/{total_sub_chunks}，将使用原始内容")
                return {
                    'index': orig_index,
                    'text': sub_chunk,
                    'success': False
                }
            
            # 使用线程池并发处理
            with concurrent.futures.ThreadPoolExecutor(max_workers=threads_num) as executor:
                # 提交所有任务
                futures = []
                for chunk_info in sub_chunks_info:
                    future = executor.submit(process_sub_chunk, chunk_info)
                    futures.append(future)
                
                # 处理完成的任务结果
                for future in concurrent.futures.as_completed(futures):
                    if not self.processing_active:  # 检查是否应停止处理
                        return None
                    
                    try:
                        result = future.result()
                        if result is not None:
                            results.append(result)
                    except Exception as e:
                        self.logger.error(f"子块处理线程异常: {e}")
            
            # 如果没有获取到任何结果，可能是处理被中止
            if not results:
                self.logger.warning("未获取到任何子块处理结果")
                return None
            
            # 按原始索引排序结果，确保合并后的文本按正确顺序
            results.sort(key=lambda x: x['index'])
            
            # 提取处理后的文本
            condensed_sub_chunks = [r['text'] for r in results]
            
            # 合并所有子块处理结果
            condensed_text = "\n\n".join(condensed_sub_chunks)
            self.logger.info(f"所有子块处理完成，合并后长度: {len(condensed_text)}")
            
            # 计算整体精简比例
            if text and condensed_text:
                ratio = (len(condensed_text) / len(text)) * 100
                self.logger.info(f"整体精简比例: {ratio:.2f}% (目标: {min_ratio}%-{max_ratio}%)")
            
            return condensed_text
        
        # 以下是原有的处理逻辑，用于处理小于阈值的文本
        # 计算目标字符数范围
        min_target_length = int(len(text) * min_ratio / 100)
        max_target_length = int(len(text) * max_ratio / 100)
        exact_target_length = (min_target_length + max_target_length) // 2
        
        # 最大重试次数
        max_retries = 0
        
        try:
            # 构建系统提示，指导AI如何进行内容精简
            system_prompt = f"""你是一个专业的小说精简助手，擅长保留小说核心情节同时减少文本量。
请遵循以下原则：
1. 保留故事的主要情节、关键场景和角色发展。
2. 去除不必要的场景描写、重复内容和冗长对话。
3. 【重要】对于精简后的内容，最重要的是要提取原来的文风文笔，不要改变原文的写作风格，要看上去认得出是原文的精简版。而不是写一个概要。把握原文作者的语言喜好，词汇喜好等等很重要
4. 【重要】目标精简比例为原文的{min_ratio}%到{max_ratio}%。
5. 【字数要求-非常重要】你必须输出{exact_target_length+500}±{(max_target_length-exact_target_length+500)//2}个字符。
   - 最少字符数: {min_target_length+500}
   - 最理想字符数: {exact_target_length+500}
   - 最大字符数: {max_target_length+500}
6. 【严格警告】禁止输出少于{min_target_length}个字符！如果你输出的内容不足这个字数，将被视为失败。
7. 保持人物对话的自然流畅和逻辑性。
8. 返回完整的精简后内容，不要包含解释、总结或其他非小说内容。
9. 不要遗漏重要情节转折点和关键角色互动。
10. 尽量保留原有段落结构，使精简后的内容仍易于阅读。
11. 【再次强调】计算并确保你的输出字符数在{min_target_length}到{max_target_length+500}之间，最好接近{exact_target_length+500}个字符。"""

            for retry in range(max_retries):
                # 构建用户提示
                chunk_info = ""
                if is_chunk:
                    chunk_info = f"【这是第{chunk_index}/{total_chunks}部分，请保持与其他部分的连贯性】"
                    
                user_prompt = f"""请对以下小说内容进行精简。

【重要字数要求】
- 必须输出的字符数范围: {min_target_length+500}-{max_target_length+500}字符
- 理想字符数: {exact_target_length+500}字符
- 字符数不足{min_target_length+500}将被视为失败

目标精简比例：原文的{min_ratio}%-{max_ratio}%

小说片段：{chunk_info}

{text}

注意事项:
1. 请直接返回精简后的内容，不要添加任何解释、概述或其他额外文本
2. 必须输出{min_target_length+500}-{max_target_length+500}字符，最好接近{exact_target_length+500}字符
3. 保留所有关键情节、人物对话和情感发展
4. 保持原文风格，避免过度总结或简化"""

                # 调用AI引擎生成精简内容
                self.logger.info(f"开始调用AI精简内容，文本长度: {len(text)}" + (f"，第{retry+1}次尝试" if retry > 0 else ""))
                condensed_text = self.ai_engine.generate_text(user_prompt, system_prompt)
                self.logger.info(f"AI精简完成，精简后长度: {len(condensed_text)}")
                
                # 计算实际精简比例
                if text and condensed_text:
                    ratio = (len(condensed_text) / len(text)) * 100
                    self.logger.info(f"精简比例: {ratio:.2f}% (目标: {min_ratio}%-{max_ratio}%)")
                    
                    # 检查是否符合目标比例
                    if ratio < min_ratio and retry < max_retries - 1:
                        self.logger.warning(f"精简比例过低: {ratio:.2f}% < {min_ratio}%，将重试...")
                        # 每次重试都调整提示词强调更长内容，增加强调程度
                        retry_emphasis = ["重要提醒", "严重警告", "最终警告"][min(retry, 2)]
                        system_prompt += f"\n\n【{retry_emphasis}】你输出的内容过少！必须至少达到{min_target_length+500}个字符，目标为{exact_target_length+500}个字符。你上次只输出了{len(condensed_text)}个字符，达到了原文的{ratio:.2f}%，但最低要求是{min_ratio}%。请确保输出足够的内容！"
                        continue
                
                # 如果是最后一次尝试或者比例符合要求，返回结果
                return condensed_text
                
        except Exception as e:
            self.logger.error(f"调用AI精简内容时出错: {e}")
            raise

    def _run_advanced_mode(self, epub_path_str, base_output_dir_str):
        """高级模式: 处理EPUB文件，将其分割为TXT，脱水处理后重新合并为EPUB"""
        self.logger.info(f"高级模式开始: EPUB={epub_path_str}, 输出基目录={base_output_dir_str}")
        
        try:
            epub_path = Path(epub_path_str)
            base_output_dir = Path(base_output_dir_str)
            
            # 创建处理目录结构
            split_dir = base_output_dir / "splitted"  # 分割后的TXT文件存放目录
            condensed_dir = base_output_dir / "condensed"  # 脱水后的TXT文件存放目录
            final_epub_path = base_output_dir / f"{epub_path.stem}_condensed.epub"  # 最终输出的EPUB路径
            
            # 确保目录存在
            split_dir.mkdir(parents=True, exist_ok=True)
            condensed_dir.mkdir(parents=True, exist_ok=True)
            
            # 步骤1: 分割EPUB为TXT文件
            self.after(0, self._update_progress, 5, "步骤 1/3: 分割 EPUB...")
            self.logger.info(f"开始分割EPUB: {epub_path}")
            
            try:
                # 检查epub_splitter是否为模拟对象
                if hasattr(epub_splitter, '__module__') and 'Mock' in epub_splitter.__module__:
                    # 使用模拟对象
                    self.logger.warning("使用模拟EPUB分割器 - 真实功能可能不可用")
                    success = epub_splitter.split_epub(str(epub_path), str(split_dir))
                else:
                    # 使用实际的模块
                    success = epub_splitter.split_epub(str(epub_path), str(split_dir))
                    
                if not success:
                    raise Exception("EPUB分割失败")
                    
                self.logger.info(f"EPUB分割完成，输出到: {split_dir}")
            except Exception as e:
                self.logger.error(f"分割EPUB时出错: {e}")
                raise Exception(f"分割EPUB时出错: {e}")
            
            if not self.processing_active: 
                raise InterruptedError("用户停止")
                
            # 步骤2: 脱水处理TXT文件
            self.after(0, self._update_progress, 20, "步骤 2/3: 脱水处理TXT文件...")
            
            # 获取分割后的TXT文件
            txt_files = sorted(list(split_dir.glob("*.txt")))
            if not txt_files:
                raise Exception(f"在 {split_dir} 中未找到分割后的TXT文件")
                
            total_files = len(txt_files)
            self.logger.info(f"找到 {total_files} 个TXT文件需要脱水处理")
            
            # 获取脱水比例设置
            min_ratio = self.min_ratio_var.get()
            max_ratio = self.max_ratio_var.get()
            force_regenerate = self.force_regenerate_var.get()
            
            # 处理文件
            processed_count = 0
            processed_successful = 0
            errors = []
            
            # 获取用户设置的线程数
            threads_num = self.threads_num_var.get()
            max_workers = min(total_files, threads_num)
            self.logger.info(f"高级模式处理，并发线程数: {threads_num}，实际线程数: {max_workers}")
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 提交所有任务
                future_to_file = {}
                for i, file_path in enumerate(txt_files):
                    # 输出路径保持与原文件名相同的格式
                    output_file_path = condensed_dir / file_path.name
                    
                    # 提交任务
                    future = executor.submit(
                        self._process_txt_file_for_epub,
                        file_path,
                        output_file_path,
                        min_ratio,
                        max_ratio,
                        force_regenerate,
                        i+1,  # chunk_index
                        total_files  # total_chunks
                    )
                    future_to_file[future] = file_path
                    
                # 处理完成的任务
                for future in concurrent.futures.as_completed(future_to_file):
                    if not self.processing_active:
                        raise InterruptedError("用户停止")
                        
                    file_path = future_to_file[future]
                    processed_count += 1
                    
                    # 计算处理进度 (脱水阶段占总进度的75%, 从20%到95%)
                    progress = 20 + int((processed_count / total_files) * 75)
                    
                    try:
                        success, message = future.result()
                        if success:
                            processed_successful += 1
                            self.logger.info(f"已处理文件 ({processed_count}/{total_files}): {file_path.name} - {message}")
                        else:
                            errors.append(f"{file_path.name}: {message}")
                            self.logger.error(f"处理文件失败 ({processed_count}/{total_files}): {file_path.name} - {message}")
                    except Exception as e:
                        errors.append(f"{file_path.name}: {str(e)}")
                        self.logger.error(f"处理文件异常 ({processed_count}/{total_files}): {file_path.name} - {str(e)}")
                        
                    # 更新进度
                    self.after(0, self._update_progress, progress, f"脱水处理: {processed_count}/{total_files} - {file_path.name}")
            
            # 检查是否有足够的文件成功处理
            if processed_successful == 0:
                raise Exception("所有文件处理失败，无法继续")
                
            if processed_successful < total_files:
                self.logger.warning(f"部分文件 ({processed_successful}/{total_files}) 处理成功，继续合并EPUB")
                
            if not self.processing_active: 
                raise InterruptedError("用户停止")
                
            # 步骤3: 合并为EPUB
            self.after(0, self._update_progress, 95, "步骤 3/3: 合并为EPUB...")
            self.logger.info(f"开始合并TXT文件为EPUB")
            
            try:
                # 检查txt_to_epub是否为模拟对象
                if hasattr(txt_to_epub, '__module__') and 'Mock' in txt_to_epub.__module__:
                    # 使用模拟对象
                    self.logger.warning("使用模拟TXT合并器 - 真实功能可能不可用")
                    success = txt_to_epub.merge_txt_to_epub(
                        str(condensed_dir), 
                        str(final_epub_path), 
                        novel_name=epub_path.stem
                    )
                else:
                    # 使用实际的模块
                    success = txt_to_epub.merge_txt_to_epub(
                        str(condensed_dir), 
                        str(final_epub_path), 
                        novel_name=epub_path.stem
                    )
                    
                if not success:
                    raise Exception("合并EPUB失败")
                    
                self.logger.info(f"TXT合并EPUB完成，输出到: {final_epub_path}")
            except Exception as e:
                self.logger.error(f"合并EPUB时出错: {e}")
                raise Exception(f"合并EPUB时出错: {e}")
                
            # 处理完成
            success_msg = f"EPUB处理完成! 输出文件: {final_epub_path.name}"
            if errors:
                warning_msg = f"{success_msg} (部分章节处理失败: {len(errors)}/{total_files})"
                self.logger.warning(warning_msg)
                self.logger.debug(f"错误详情: {errors}")
                self.after(0, self._processing_finished, True, warning_msg)
            else:
                self.logger.info(success_msg)
                self.after(0, self._processing_finished, True, success_msg)

        except InterruptedError:
            self.logger.warning("高级模式处理被用户停止")
            self.after(0, self._processing_finished, False, "处理被停止")
        except Exception as e:
            self.logger.critical(f"高级模式处理出错: {e}", exc_info=True)
            self.after(0, self._processing_finished, False, f"处理出错: {e}")
            
    def _process_txt_file_for_epub(self, file_path: Path, output_path: Path, min_ratio: int, max_ratio: int, force_regenerate: bool, chunk_index: int, total_chunks: int):
        """处理用于EPUB的单个TXT文件，使用AI精简内容"""
        try:
            # 检查输出文件是否已存在
            if output_path.exists() and not force_regenerate:
                self.logger.info(f"{file_path.name} - 已存在，跳过")
                return True, "已存在，跳过"
            
            # 读取文件内容
            try:
                content = None
                error_msg = None
                
                # 尝试使用不同编码读取
                encodings = ['utf-8', 'gbk', 'gb2312', 'utf-16', 'cp936']
                for enc in encodings:
                    try:
                        with open(file_path, 'r', encoding=enc) as f:
                            content = f.read()
                        break
                    except UnicodeDecodeError:
                        continue
                    except Exception as e:
                        error_msg = f"读取出错 ({enc}): {e}"
                        break
                
                if content is None:
                    if error_msg:
                        return False, error_msg
                    else:
                        return False, "无法以支持的编码读取文件"
            except Exception as e:
                return False, f"读取文件时出错: {e}"
            
            # 检查内容是否为空
            if not content.strip():
                # 如果内容为空，直接创建空文件保持章节结构完整性
                try:
                    with open(output_path, 'w', encoding='utf-8') as f:
                        f.write("")
                    return True, "内容为空，创建空文件"
                except Exception as e:
                    return False, f"创建空文件时出错: {e}"
            
            # 使用AI进行内容精简，指示这是EPUB的一部分
            try:
                condensed_content = self._condense_text_internal(
                    content, 
                    min_ratio, 
                    max_ratio, 
                    is_chunk=True,
                    chunk_index=chunk_index,
                    total_chunks=total_chunks
                )
                
                if condensed_content is None:  # 处理被中断
                    return False, "处理被中断"
                    
                if not condensed_content.strip():
                    return False, "AI返回内容为空"
                    
                # 检查精简比例是否过低
                ratio = (len(condensed_content) / len(content)) * 100
                if ratio < min_ratio * 0.5:  # 如果低于最小比例的一半
                    self.logger.warning(f"精简比例极低: {ratio:.2f}% << {min_ratio}%，可能需要手动检查结果")
            except Exception as e:
                return False, f"调用AI精简时出错: {e}"
                
            # 保存精简后的内容
            try:
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(condensed_content)
            except Exception as e:
                return False, f"保存输出文件时出错: {e}"
                
            # 计算精简比例
            original_length = len(content)
            condensed_length = len(condensed_content)
            ratio = (condensed_length / original_length * 100) if original_length > 0 else 0
            
            # 处理成功
            return True, f"成功精简 ({ratio:.1f}%)"
            
        except Exception as e:
            return False, f"处理文件时出现未知错误: {e}"


# --- 用于测试的入口 ---
if __name__ == '__main__':
    import os
    import sys
    from pathlib import Path
    
    # 将项目根目录添加到Python路径中，确保能够导入ainovel包
    file_path = Path(__file__)
    root_dir = file_path.parent.parent.absolute()
    sys.path.insert(0, str(root_dir))
    
    if HAS_CTK:
        root = ctk.CTk()
        # 设置主题等
        # ctk.set_appearance_mode("dark")
    else:
        root = tk.Tk()

    # 尝试设置主题（如果 sv_ttk 可用）
    try:
        import sv_ttk
        HAS_SVTTK = True
        if not HAS_CTK and HAS_SVTTK: # 只有在没有ctk且有sv_ttk时才使用
            sv_ttk.set_theme("dark") # 或者 "light"
            print("应用 sv-ttk 主题")
    except ImportError:
        HAS_SVTTK = False
        print("Warning: sv-ttk主题库未找到。使用默认Tkinter主题。")
    except Exception as e:
        print(f"应用 sv-ttk 主题失败: {e}")


    root.title("主窗口")
    root.geometry("300x200")

    # 尝试导入其他模块
    try:
        # 先尝试从ainovel包导入
        try:
            from ainovel.ai import AIEngine, get_ai_engine
            from ainovel.log import LogManager, get_log_manager
            real_ai_engine = get_ai_engine()
            real_log_manager = get_log_manager()
            print("成功从ainovel包导入模块")
        except ImportError:
            # 如果失败，使用模拟对象
            print("无法从ainovel包导入模块，使用模拟对象")
            # 使用上面定义的模拟类
            real_ai_engine = AIEngine()
            real_log_manager = LogManager()
    except Exception as e:
        print(f"初始化AI引擎或日志管理器时出错: {e}")
        # 使用模拟对象
        real_ai_engine = AIEngine()
        real_log_manager = LogManager()


    def open_condenser():
        # 传递真实的日志管理器
        win = CondenserWindow(root, real_ai_engine, real_log_manager)
        win.grab_set()

    if HAS_CTK:
        btn = ctk.CTkButton(root, text="打开 AI 精简工具", command=open_condenser)
        btn.pack(pady=50)
    else:
        # 使用 ttk 按钮以应用主题
        style = ttk.Style()
        # print(style.theme_names()) # 查看可用主题
        # print(style.theme_use()) # 查看当前主题
        btn = ttk.Button(root, text="打开 AI 精简工具", command=open_condenser)
        btn.pack(pady=50)


    # 添加一个简单的日志显示区域到主窗口（用于测试）
    log_frame = ttk.Frame(root)
    log_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
    log_text = tk.Text(log_frame, height=5, state='disabled', wrap='word')
    log_scroll = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=log_text.yview)
    log_text.config(yscrollcommand=log_scroll.set)
    log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
    log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    # 模拟 LogWindow 的日志更新逻辑
    def update_main_log():
        try:
            # 使用动态导入避免前面导入失败
            import queue
            while True:
                 # 注意：这里假设real_log_manager有log_queue，如果它没有，需要调整
                 if hasattr(real_log_manager, 'log_queue'):
                     record, msg = real_log_manager.log_queue.get_nowait()
                     log_text.configure(state='normal')
                     log_text.insert(tk.END, msg + '\n')
                     log_text.see(tk.END)
                     log_text.configure(state='disabled')
                 else:
                     # 如果没有队列，无法自动更新
                     break
        except queue.Empty:
            pass
        except Exception as e:
            print(f"更新主窗口日志时出错: {e}")
        # 持续更新
        if root.winfo_exists():
             root.after(200, update_main_log)

    # 只有当日志管理器有队列时才启动更新
    if hasattr(real_log_manager, 'log_queue'):
        root.after(100, update_main_log)
    else:
        log_text.configure(state='normal')
        log_text.insert('1.0', "主日志区域 (自动更新需 LogManager 实现队列)\n")
        log_text.configure(state='disabled')


    root.mainloop()
