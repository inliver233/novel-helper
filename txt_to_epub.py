#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TXT转EPUB工具 - 将多个TXT文本文件合并为EPUB电子书

这个脚本可以将文件夹中的多个TXT文件按照特定命名规则合并为一个EPUB电子书，
便于在电子阅读器上阅读。
"""

import os
import re
import argparse
import logging
import uuid  # 添加uuid模块导入
import zipfile
import shutil
import tempfile
from pathlib import Path
from ebooklib import epub
from bs4 import BeautifulSoup


# 配置日志系统
def setup_logger(log_level=logging.INFO):
    """配置日志系统"""
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    return logging.getLogger(__name__)


# 创建全局日志对象
logger = setup_logger()


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
        
        # 如果章节标题是"目录"，标记为特殊序号
        if chapter_title == "目录":
            logger.info(f"检测到目录文件: {filename}")
            chapter_number = -1  # 使用负数使目录排在最前面，但不作为正式章节
            
        return novel_name, chapter_number, chapter_title
    
    # 尝试其他可能的格式: 小说名_[开始-结束].txt，用于处理多章节合并文件
    pattern2 = r"(.+?)_\[(\d+)-(\d+)\]\.txt$"
    match = re.match(pattern2, filename)
    if match:
        novel_name = match.group(1)
        start_chapter = int(match.group(2))
        chapter_title = f"第{start_chapter}章"
        return novel_name, start_chapter, chapter_title
    
    # 尝试更宽松的格式：小说名称_序号_章节名称.txt（没有方括号）
    pattern3 = r"(.+?)_(\d+)_(.+?)\.txt$"
    match = re.match(pattern3, filename)
    if match:
        novel_name = match.group(1)
        chapter_number = int(match.group(2))
        chapter_title = match.group(3)
        return novel_name, chapter_number, chapter_title
        
    logger.warning(f"无法解析文件名: {filename}，不符合命名规则")
    return None, None, None


def read_txt_content(file_path):
    """读取txt文件内容，自动处理编码问题"""
    file_path = Path(file_path)
    
    if not file_path.exists():
        logger.error(f"文件不存在: {file_path}")
        return "（文件不存在）"
    
    if file_path.stat().st_size == 0:
        logger.warning(f"警告：文件 {file_path} 为空文件")
        return "（空文件）"
    
    # 尝试使用不同编码读取文件
    encodings = ['utf-8', 'gbk', 'gb2312', 'utf-16', 'latin-1']
    
    for encoding in encodings:
        try:
            logger.debug(f"尝试使用 {encoding} 编码读取文件 {file_path.name}")
            with open(file_path, 'r', encoding=encoding) as f:
                content = f.read()
                # 检查是否成功读取到内容
                if not content:
                    logger.warning(f"文件 {file_path.name} 内容为空")
                    continue
                
                logger.debug(f"文件 {file_path.name} 使用 {encoding} 编码成功读取，内容长度: {len(content)}")
                return content
        except UnicodeDecodeError:
            logger.debug(f"使用 {encoding} 编码读取 {file_path.name} 失败")
            continue
        except Exception as e:
            logger.warning(f"读取文件 {file_path.name} 时发生错误: {e}")
            continue
    
    # 所有编码都失败时，尝试二进制读取
    try:
        logger.warning(f"所有文本编码都失败，尝试二进制读取文件 {file_path}")
        with open(file_path, 'rb') as f:
            binary_data = f.read()
            # 尝试使用latin-1强制解码，这通常可以读取任何二进制数据
            content = binary_data.decode('latin-1', errors='replace')
            logger.info(f"使用二进制方式成功读取文件 {file_path.name}，内容长度: {len(content)}")
            return content
    except Exception as e:
        logger.error(f"二进制读取文件 {file_path} 失败: {e}")
    
    logger.error(f"无法以任何方式解码文件 {file_path}，将返回默认内容")
    return "（内容读取失败）"


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
        logger.warning(f"章节 '{chapter_title}' 内容为空，将添加提示文本")
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


def detect_novel_name(txt_files, folder_path):
    """
    从文件名中检测小说名称
    
    Args:
        txt_files: TXT文件名列表
        folder_path: 文件夹路径
    
    Returns:
        str: 检测到的小说名称，如果无法检测则返回None
    """
    name_counter = {}
    
    for filename in txt_files:
        name, _, _ = parse_filename(filename)
        if name:
            name_counter[name] = name_counter.get(name, 0) + 1
    
    # 返回出现次数最多的小说名称
    if name_counter:
        most_common_name = max(name_counter.items(), key=lambda x: x[1])[0]
        logger.info(f"检测到小说名称: {most_common_name}")
        return most_common_name
    
    # 如果无法从文件名检测，则使用文件夹名称
    folder_name = Path(folder_path).name
    logger.info(f"无法从文件名检测小说名称，使用文件夹名称: {folder_name}")
    return folder_name


def extract_chapters(txt_files, folder_path, novel_name=None):
    """
    从文件列表中提取章节信息
    
    Args:
        txt_files: TXT文件名列表
        folder_path: 文件夹路径
        novel_name: 指定的小说名称，如果为None则自动检测
        
    Returns:
        tuple: (小说名称, 章节列表)
    """
    chapters = []
    detected_novel_name = None
    
    for filename in txt_files:
        name, number, title = parse_filename(filename)
        if name and number is not None and title:
            # 跳过目录文件（序号为负数的文件，如-1）
            if number < 0:
                logger.info(f"跳过目录文件: {filename}")
                continue
                
            if detected_novel_name is None:
                detected_novel_name = name
            
            # 确保所有文件属于同一本小说
            if name != detected_novel_name and novel_name is None:
                logger.warning(f"警告：文件 {filename} 的小说名称 '{name}' 与其他文件 '{detected_novel_name}' 不同")
            
            chapters.append({
                'filename': filename,
                'number': number,
                'title': title,
                'path': Path(folder_path) / filename
            })
    
    # 使用指定的小说名称或检测到的小说名称
    final_novel_name = novel_name or detected_novel_name or detect_novel_name(txt_files, folder_path)
    
    # 按章节编号排序
    chapters.sort(key=lambda x: x['number'])
    
    logger.info(f"从 {len(txt_files)} 个文件中提取了 {len(chapters)} 个有效章节")
    
    # 如果没有有效章节，返回错误
    if not chapters:
        logger.error("未能提取任何有效章节，请检查文件命名格式")
        return final_novel_name, []
        
    return final_novel_name, chapters


def create_epub_book(novel_name, chapters, author=None, language='zh-CN'):
    """
    创建EPUB书籍对象
    
    Args:
        novel_name: 小说名称
        chapters: 章节列表
        author: 作者名称
        language: 语言代码
        
    Returns:
        tuple: (epub书籍对象, epub章节列表, 目录列表, 书脊列表)
    """
    # 创建epub书籍
    book = epub.EpubBook()
    book.set_title(novel_name)
    book.set_language(language)
    
    if author:
        book.add_author(author)
    
    # 添加章节
    epub_chapters = []
    toc = []
    spine = ['nav']
    
    return book, epub_chapters, toc, spine


def add_chapters_to_book(book, chapters, epub_chapters, toc, spine):
    """将章节添加到EPUB书籍"""
    added_chapters = 0
    
    if not chapters:
        logger.error("没有章节可添加")
        return 0
    
    # 添加CSS
    style = '''
    @namespace epub "http://www.idpf.org/2007/ops";
    body { 
        font-family: "Noto Serif CJK SC", "Source Han Serif CN", SimSun, serif; 
        margin: 5%; 
        line-height: 1.5;
    }
    h1 { 
        text-align: center;
        font-size: 1.5em;
        margin: 1em 0;
    }
    h2 { 
        text-align: center;
        font-size: 1.2em;
        margin: 0.8em 0;
    }
    p { 
        text-indent: 2em; 
        margin: 0.3em 0;
    }
    .cover {
        text-align: center;
        margin: 3em 0;
    }
    .author {
        text-align: center;
        margin: 1em 0;
    }
    .toc a {
        text-decoration: none;
        color: black;
    }
    '''
    css = epub.EpubItem(uid="style", 
                       file_name="style.css", 
                       media_type="text/css", 
                       content=style)
    book.add_item(css)
    
    # 添加封面页
    book_title = book.title
    book_author = "未知作者"
    if hasattr(book, 'metadata') and 'creator' in book.metadata:
        if book.metadata['creator']:
            book_author = book.metadata['creator'][0][0]
    
    cover_title = f'<h1 class="cover">{book_title}</h1>'
    cover_author = f'<p class="author">作者：{book_author}</p>'
    
    cover = epub.EpubHtml(title='封面', 
                         file_name='cover.xhtml',
                         lang=language)
    cover.content = f'''<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head>
    <title>封面</title>
    <link rel="stylesheet" type="text/css" href="style.css" />
    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
</head>
<body>
    <div class="cover">
        {cover_title}
        {cover_author}
    </div>
</body>
</html>'''
    book.add_item(cover)
    # 添加CSS引用
    cover.add_link(href="style.css", rel="stylesheet", type="text/css")
    
    # 添加目录页
    toc_content = '<h1>目录</h1>\n<div class="toc">'
    for i, chapter in enumerate(chapters):
        safe_title = chapter["title"].replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
        chapter_num = i + 1
        toc_content += f'<p><a href="chapter_{chapter_num}.xhtml">{safe_title}</a></p>\n'
    toc_content += '</div>'
    
    toc_page = epub.EpubHtml(title='目录',
                            file_name='toc.xhtml',
                            lang=language)
    toc_page.content = f'''<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head>
    <title>目录</title>
    <link rel="stylesheet" type="text/css" href="style.css" />
    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
</head>
<body>
    {toc_content}
</body>
</html>'''
    book.add_item(toc_page)
    # 添加CSS引用
    toc_page.add_link(href="style.css", rel="stylesheet", type="text/css")
    
    # 添加章节
    for i, chapter in enumerate(chapters):
        try:
            content = read_txt_content(chapter['path'])
            logger.info(f"读取章节 {i+1} 内容，长度: {len(content) if content else 0} 字节")
            
            if not content or not content.strip():
                logger.warning(f"章节 {i+1} 内容为空，使用默认文本")
                content = f"（《{chapter['title']}》章节内容为空）"
            
            # 转义内容，确保安全
            safe_title = chapter['title'].replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
            
            # 构建段落HTML
            paragraphs_html = ""
            for p in content.split('\n'):
                if p.strip():
                    p_safe = p.strip().replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
                    paragraphs_html += f'<p>{p_safe}</p>\n'
            
            # 确保章节内容不为空
            if not paragraphs_html.strip():
                logger.warning(f"章节 {i+1} 格式化后内容为空，使用默认文本")
                paragraphs_html = f"<p>（《{safe_title}》章节内容为空）</p>"
            
            # 创建章节
            chapter_id = f'chapter_{i+1}'
            file_name = f'{chapter_id}.xhtml'
            
            c = epub.EpubHtml(
                uid=chapter_id,
                title=safe_title, 
                file_name=file_name,
                lang=language
            )
            
            # 使用更简单的HTML结构
            c.content = f'''<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head>
    <title>{safe_title}</title>
    <link rel="stylesheet" type="text/css" href="style.css" />
    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
</head>
<body>
    <h1>{safe_title}</h1>
    {paragraphs_html}
</body>
</html>'''
            
            # 验证内容长度
            if len(c.content) < 100:
                logger.warning(f"章节 {i+1} 生成的HTML内容过短: {len(c.content)}字节")
            
            # 添加对CSS的引用
            c.add_link(href="style.css", rel="stylesheet", type="text/css")
            
            # 添加到书籍
            book.add_item(c)
            epub_chapters.append(c)
            added_chapters += 1
            
            logger.info(f"已添加章节 {i+1}: {safe_title} (HTML内容长度: {len(c.content)})")
        except Exception as e:
            logger.error(f"添加章节 {i+1} 时出错: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    # 确保至少添加了一个章节
    if added_chapters == 0:
        logger.error("没有任何章节被成功添加到EPUB，请检查文件内容")
    else:
        logger.info(f"成功添加 {added_chapters} 个章节")
    
    return added_chapters


def finalize_epub(book, toc, spine):
    """完成EPUB书籍的导航和目录设置"""
    try:
        # 添加导航
        book.add_item(epub.EpubNcx())
        
        # 创建导航文件
        nav = epub.EpubNav()
        nav.add_link(href="style.css", rel="stylesheet", type="text/css")
        book.add_item(nav)
        
        # 设置书籍脊柱（阅读顺序）确保正确顺序
        spine = ['nav']
        spine.append(cover)  # 添加封面
        spine.append(toc_page)  # 添加目录
        for chapter in epub_chapters:
            spine.append(chapter)  # 添加每个章节
        book.spine = spine
        
        # 设置目录 - 使用扁平结构以确保兼容性
        book.toc = [
            epub.Link('cover.xhtml', '封面', 'cover'),
            epub.Link('toc.xhtml', '目录', 'toc')
        ]
        
        # 直接添加每个章节到目录，避免使用Section结构
        for i, chapter in enumerate(epub_chapters):
            chapter_num = i + 1
            book.toc.append(epub.Link(f'chapter_{chapter_num}.xhtml', chapter.title, f'chapter_{chapter_num}'))
        
        # 添加元数据
        book.add_metadata('DC', 'description', '由TXT转EPUB工具生成')
        book.add_metadata('DC', 'publisher', 'AI小说工具')
        book.add_metadata('DC', 'source', 'TXT文件转换')
        book.add_metadata('DC', 'rights', '版权归原作者所有')
        
        # 使用正确的uuid模块
        unique_id = str(uuid.uuid4())
        book.add_metadata('DC', 'identifier', f'uuid:{unique_id}', {'id': 'pub-id'})
        
        logger.info("EPUB结构配置完成")
    except Exception as e:
        logger.error(f"配置EPUB结构时出错: {e}")
        import traceback
        logger.error(f"详细错误: {traceback.format_exc()}")


def write_epub_file(book, output_path):
    """将EPUB书籍写入文件"""
    try:
        # 检查book对象是否有效
        if not book or not hasattr(book, 'spine') or not book.spine:
            logger.error("无效的EPUB书籍对象: spine为空")
            return False
            
        # 检查书籍是否有实际内容章节
        content_items = [item for item in book.spine if item != 'nav']
        if not content_items:
            logger.error("EPUB书籍没有内容章节")
            return False
            
        # 打印调试信息
        logger.info(f"EPUB书籍信息: 标题={book.title}, 章节数={len(content_items)}")
        
        # 详细检查每个章节
        chapter_count = 0
        for item in book.items:
            if isinstance(item, epub.EpubHtml) and 'chapter_' in item.file_name:
                chapter_count += 1
                content_length = len(item.content) if item.content else 0
                logger.debug(f"章节文件 {item.file_name}: 标题={item.title}, 内容长度={content_length}")
                
                # 检查内容是否太短
                if content_length < 100:
                    logger.warning(f"章节 {item.title} 内容异常短: {content_length} 字节")
                    # 添加默认内容
                    safe_title = item.title.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
                    item.content = f'''<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head>
    <title>{safe_title}</title>
    <link rel="stylesheet" type="text/css" href="style.css" />
    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
</head>
<body>
    <h1>{safe_title}</h1>
    <p>（本章内容为空或无法正常读取，请检查原始文件）</p>
</body>
</html>'''
        
        logger.info(f"EPUB包含 {chapter_count} 个章节文件")
        
        # 检查spine中的章节顺序
        spine_chapters = [item for item in book.spine if isinstance(item, epub.EpubHtml) and 'chapter_' in item.file_name]
        logger.info(f"Spine中包含 {len(spine_chapters)} 个章节")
        logger.info(f"书脊顺序: {[getattr(item, 'file_name', item) for item in book.spine[:10]]}...")
        
        # 检查TOC和item是否对应
        logger.info(f"目录项数: {len(book.toc)}")
        toc_chapters = [item for item in book.toc if hasattr(item, 'href') and 'chapter_' in item.href]
        logger.info(f"TOC中包含 {len(toc_chapters)} 个章节链接")
        
        # 确保输出目录存在
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 写入前清理已存在的同名文件
        if output_path.exists():
            logger.warning(f"文件已存在，将被覆盖: {output_path}")
            try:
                output_path.unlink()
            except Exception as e:
                logger.warning(f"无法删除现有文件: {e}")
        
        logger.info(f"正在写入EPUB文件: {output_path}")
        
        # 使用更兼容的选项
        options = {
            'epub2_guide': True,   # 启用EPUB2指南
            'epub3_landmark': False,  # 禁用EPUB3地标
            'epub3_pages': False,   # 禁用EPUB3页面
            'landmark_title': 'Guide',  # 指南标题
            'spine_direction': None,  # 不设置脊柱方向
            'play_order': {'enabled': True},  # 启用播放顺序
            'toc_ncx': True,  # 启用toc.ncx文件生成
            'version': 2  # 使用EPUB2格式以增加兼容性
        }
        
        # 直接写入
        epub.write_epub(str(output_path), book, options)
        
        # 验证文件
        if output_path.exists():
            file_size = output_path.stat().st_size
            logger.info(f"EPUB文件已生成: {output_path}, 大小: {file_size/1024:.2f} KB")
            
            if file_size < 10000:  # 小于10KB可能有问题
                logger.warning(f"生成的EPUB文件过小 ({file_size} 字节)，可能存在问题")
                if file_size < 1000:  # 小于1KB几乎肯定有问题
                    logger.error("文件太小，可能生成失败")
                    return False
            
            # 成功
            return True
        else:
            logger.error(f"生成的EPUB文件不存在: {output_path}")
            return False
    except Exception as e:
        logger.error(f"写入EPUB文件出错: {e}")
        import traceback
        logger.error(f"详细错误: {traceback.format_exc()}")
        return False


def write_epub_file_manual(book, output_path):
    """
    使用zipfile库直接创建EPUB文件，绕过ebooklib的write_epub
    
    Args:
        book: EpubBook对象
        output_path: 输出文件路径
    
    Returns:
        bool: 是否成功写入文件
    """
    try:
        output_path = Path(output_path)
        temp_dir = Path(tempfile.mkdtemp())
        logger.info(f"创建临时目录: {temp_dir}")
        
        # 创建mimetype文件（必须是第一个文件，且不压缩）
        mimetype_path = temp_dir / "mimetype"
        with open(mimetype_path, "w", encoding="utf-8") as f:
            f.write("application/epub+zip")
        
        # 创建META-INF目录
        meta_inf_dir = temp_dir / "META-INF"
        meta_inf_dir.mkdir(exist_ok=True)
        
        # 创建container.xml
        container_path = meta_inf_dir / "container.xml"
        with open(container_path, "w", encoding="utf-8") as f:
            f.write('''<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
    <rootfiles>
        <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
    </rootfiles>
</container>''')
        
        # 创建OEBPS目录（存放内容）
        oebps_dir = temp_dir / "OEBPS"
        oebps_dir.mkdir(exist_ok=True)
        
        # 写入CSS文件
        for item in book.items:
            if isinstance(item, epub.EpubItem) and item.file_name.endswith('.css'):
                css_path = oebps_dir / item.file_name
                with open(css_path, "w", encoding="utf-8") as f:
                    f.write(item.content)
                logger.info(f"写入CSS文件: {item.file_name}")
        
        # 写入所有HTML文件（章节内容、封面、目录等）
        for item in book.items:
            if isinstance(item, epub.EpubHtml):
                html_path = oebps_dir / item.file_name
                with open(html_path, "w", encoding="utf-8") as f:
                    # 验证内容是否为空
                    if not item.content or len(item.content) < 10:
                        logger.warning(f"文件 {item.file_name} 内容为空或过短，添加默认内容")
                        # 添加默认内容
                        safe_title = item.title.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
                        item.content = f'''<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head>
    <title>{safe_title}</title>
    <link rel="stylesheet" type="text/css" href="style.css" />
    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
</head>
<body>
    <h1>{safe_title}</h1>
    <p>（本章内容已丢失，请检查原始文件）</p>
</body>
</html>'''
                    
                    # 写入内容
                    f.write(item.content)
                    content_length = len(item.content)
                    logger.info(f"写入HTML文件: {item.file_name}, 内容长度: {content_length}")
        
        # 写入导航文件
        nav_items = [item for item in book.items if isinstance(item, epub.EpubNav)]
        for nav in nav_items:
            nav_path = oebps_dir / nav.file_name
            with open(nav_path, "w", encoding="utf-8") as f:
                f.write(nav.content)
                logger.info(f"写入导航文件: {nav.file_name}")
        
        # 写入NCX文件
        ncx_items = [item for item in book.items if isinstance(item, epub.EpubNcx)]
        for ncx in ncx_items:
            ncx_path = oebps_dir / "toc.ncx"
            ncx_content = '''<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head>
    <meta name="dtb:uid" content="unique-identifier"/>
    <meta name="dtb:depth" content="1"/>
    <meta name="dtb:totalPageCount" content="0"/>
    <meta name="dtb:maxPageNumber" content="0"/>
  </head>
  <docTitle>
    <text>''' + book.title + '''</text>
  </docTitle>
  <navMap>'''
            
            # 添加各章节导航点
            for i, toc_item in enumerate(book.toc):
                if hasattr(toc_item, 'href'):
                    ncx_content += f'''
    <navPoint id="navpoint-{i+1}" playOrder="{i+1}">
      <navLabel>
        <text>{toc_item.title}</text>
      </navLabel>
      <content src="{toc_item.href}"/>
    </navPoint>'''
            
            ncx_content += '''
  </navMap>
</ncx>'''
            
            with open(ncx_path, "w", encoding="utf-8") as f:
                f.write(ncx_content)
                logger.info("写入TOC.NCX文件")
        
        # 创建OPF文件
        opf_path = oebps_dir / "content.opf"
        opf_content = '''<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="BookId">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:title>''' + book.title + '''</dc:title>'''
        
        # 添加作者
        if hasattr(book, 'metadata') and 'creator' in book.metadata:
            for creator in book.metadata['creator']:
                opf_content += f'''
    <dc:creator>{creator[0]}</dc:creator>'''
        
        # 添加语言
        opf_content += f'''
    <dc:language>{book.language}</dc:language>'''
        
        # 添加唯一标识符
        unique_id = str(uuid.uuid4())
        opf_content += f'''
    <dc:identifier id="BookId">urn:uuid:{unique_id}</dc:identifier>'''
        
        # 添加其他元数据
        if hasattr(book, 'metadata'):
            if 'description' in book.metadata:
                opf_content += f'''
    <dc:description>{book.metadata['description'][0][0]}</dc:description>'''
            if 'publisher' in book.metadata:
                opf_content += f'''
    <dc:publisher>{book.metadata['publisher'][0][0]}</dc:publisher>'''
            if 'rights' in book.metadata:
                opf_content += f'''
    <dc:rights>{book.metadata['rights'][0][0]}</dc:rights>'''
        
        opf_content += '''
  </metadata>
  <manifest>'''
        
        # 添加所有文件到manifest
        manifest_items = []
        item_id = 1
        
        # 添加NCX
        opf_content += '''
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'''
        
        # 添加样式表
        for item in book.items:
            if isinstance(item, epub.EpubItem) and item.file_name.endswith('.css'):
                opf_content += f'''
    <item id="style_{item_id}" href="{item.file_name}" media-type="text/css"/>'''
                item_id += 1
        
        # 添加HTML文件
        html_items = []
        for item in book.items:
            if isinstance(item, epub.EpubHtml):
                item_id_str = item.id if hasattr(item, 'id') and item.id else f"item_{item_id}"
                opf_content += f'''
    <item id="{item_id_str}" href="{item.file_name}" media-type="application/xhtml+xml"/>'''
                item_id += 1
                html_items.append(item)
        
        # 添加导航文件
        for item in book.items:
            if isinstance(item, epub.EpubNav):
                opf_content += f'''
    <item id="nav" href="{item.file_name}" media-type="application/xhtml+xml" properties="nav"/>'''
        
        opf_content += '''
  </manifest>
  <spine toc="ncx">'''
        
        # 添加所有项目到spine，保持正确顺序
        for item in book.spine:
            if item == 'nav':
                opf_content += '''
    <itemref idref="nav"/>'''
            elif isinstance(item, epub.EpubHtml):
                item_id_str = item.id if hasattr(item, 'id') and item.id else "item_" + str(html_items.index(item) + 1)
                opf_content += f'''
    <itemref idref="{item_id_str}"/>'''
        
        opf_content += '''
  </spine>
  <guide>'''
        
        # 添加封面和目录到指南
        for item in book.items:
            if isinstance(item, epub.EpubHtml):
                if 'cover' in item.file_name:
                    opf_content += f'''
    <reference type="cover" title="Cover" href="{item.file_name}"/>'''
                elif 'toc' in item.file_name:
                    opf_content += f'''
    <reference type="toc" title="Table of Contents" href="{item.file_name}"/>'''
        
        opf_content += '''
  </guide>
</package>'''
        
        with open(opf_path, "w", encoding="utf-8") as f:
            f.write(opf_content)
            logger.info("写入OPF文件")
        
        # 创建EPUB文件（ZIP格式）
        if output_path.exists():
            output_path.unlink()
        
        logger.info(f"创建EPUB文件: {output_path}")
        
        epub_file = zipfile.ZipFile(output_path, 'w')
        
        # 首先添加mimetype文件，不压缩
        epub_file.write(mimetype_path, "mimetype", compress_type=zipfile.ZIP_STORED)
        
        # 添加其他所有文件，使用压缩
        for root, dirs, files in os.walk(temp_dir):
            for file in files:
                if file != "mimetype":  # 跳过mimetype，因为已经添加了
                    file_path = Path(root) / file
                    arcname = str(file_path.relative_to(temp_dir))
                    epub_file.write(file_path, arcname, compress_type=zipfile.ZIP_DEFLATED)
                    logger.info(f"添加文件到EPUB: {arcname}")
        
        epub_file.close()
        
        # 清理临时目录
        shutil.rmtree(temp_dir)
        
        # 验证生成的文件
        if output_path.exists():
            file_size = output_path.stat().st_size
            logger.info(f"EPUB文件已生成: {output_path}, 大小: {file_size/1024:.2f} KB")
            
            if file_size < 10000:  # 小于10KB可能有问题
                logger.warning(f"生成的EPUB文件过小 ({file_size} 字节)，可能存在问题")
                if file_size < 1000:  # 小于1KB几乎肯定有问题
                    logger.error("文件太小，可能生成失败")
                    return False
            
            # 尝试打开ZIP文件验证其完整性
            try:
                with zipfile.ZipFile(output_path, 'r') as zf:
                    # 检查基本文件是否存在
                    required_files = ['mimetype', 'META-INF/container.xml', 'OEBPS/content.opf']
                    for req_file in required_files:
                        if req_file not in zf.namelist():
                            logger.error(f"EPUB文件格式错误：缺少必要文件 {req_file}")
                            return False
                    
                    # 检查章节文件
                    chapter_files = [name for name in zf.namelist() if name.startswith('OEBPS/chapter_')]
                    logger.info(f"EPUB中包含 {len(chapter_files)} 个章节文件")
                    
                    # 检查文件大小
                    for chapter in chapter_files:
                        info = zf.getinfo(chapter)
                        logger.debug(f"章节文件 {chapter}: 压缩前大小={info.file_size}, 压缩后大小={info.compress_size}")
                        if info.file_size == 0:
                            logger.warning(f"章节文件 {chapter} 大小为零！")
            except Exception as e:
                logger.error(f"验证EPUB文件时出错: {e}")
                return False
            
            logger.info("EPUB文件验证通过")
            return True
        else:
            logger.error(f"生成的EPUB文件不存在: {output_path}")
            return False
    except Exception as e:
        logger.error(f"手动创建EPUB文件时出错: {e}")
        import traceback
        logger.error(f"详细错误: {traceback.format_exc()}")
        return False


def merge_txt_to_epub(folder_path, output_path=None, author=None, novel_name=None, language='zh-CN'):
    """
    将文件夹中的txt文件合并为epub
    
    Args:
        folder_path: 包含txt文件的文件夹路径
        output_path: 输出epub文件的路径（可选）
        author: 作者名称（可选）
        novel_name: 小说名称（可选，如不指定则从文件名解析）
        language: 电子书语言代码
        
    Returns:
        str or None: 成功时返回输出路径，失败时返回None
    """
    try:
        folder_path = Path(folder_path)
        
        # 检查文件夹是否存在
        if not folder_path.exists() or not folder_path.is_dir():
            logger.error(f"文件夹不存在或不是有效目录: {folder_path}")
            return None
        
        # 获取所有txt文件
        txt_files = [f.name for f in folder_path.iterdir() if f.suffix.lower() == '.txt']
        if not txt_files:
            logger.error(f"在 {folder_path} 中没有找到TXT文件")
            return None
        
        logger.info(f"在 {folder_path} 中找到 {len(txt_files)} 个TXT文件")
        
        # 提取章节信息
        book_name, chapters = extract_chapters(txt_files, folder_path, novel_name)
        
        if not book_name:
            logger.error("无法确定小说名称")
            return None
        
        if not chapters:
            logger.error("未能提取任何有效章节")
            return None
        
        logger.info(f"提取出 {len(chapters)} 个章节")
        
        # 如果未指定输出路径，则使用小说名称作为文件名
        if not output_path:
            output_path = folder_path / f"{book_name}_脱水.epub"
        
        # 创建一个简单的EPUB书籍
        book = epub.EpubBook()
        book.set_title(book_name)
        book.set_language(language)
        
        if author:
            book.add_author(author)
        else:
            book.add_author("佚名")  # 默认作者
        
        # 添加CSS
        style = '''
        @namespace epub "http://www.idpf.org/2007/ops";
        body { 
            font-family: "Noto Serif CJK SC", "Source Han Serif CN", SimSun, serif; 
            margin: 5%; 
            line-height: 1.5;
        }
        h1 { 
            text-align: center;
            font-size: 1.5em;
            margin: 1em 0;
        }
        h2 { 
            text-align: center;
            font-size: 1.2em;
            margin: 0.8em 0;
        }
        p { 
            text-indent: 2em; 
            margin: 0.3em 0;
        }
        .cover {
            text-align: center;
            margin: 3em 0;
        }
        .author {
            text-align: center;
            margin: 1em 0;
        }
        .toc a {
            text-decoration: none;
            color: black;
        }
        '''
        css = epub.EpubItem(uid="style", 
                           file_name="style.css", 
                           media_type="text/css", 
                           content=style)
        book.add_item(css)
        
        # 添加封面页
        cover_title = f'<h1 class="cover">{book_name}</h1>'
        cover_author = f'<p class="author">作者：{author if author else "佚名"}</p>'
        
        cover = epub.EpubHtml(title='封面', 
                             file_name='cover.xhtml',
                             lang=language)
        cover.content = f'''<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head>
    <title>封面</title>
    <link rel="stylesheet" type="text/css" href="style.css" />
    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
</head>
<body>
    <div class="cover">
        {cover_title}
        {cover_author}
    </div>
</body>
</html>'''
        book.add_item(cover)
        # 添加CSS引用
        cover.add_link(href="style.css", rel="stylesheet", type="text/css")
        
        logger.info("已添加封面页")
        
        # 添加目录页
        toc_content = '<h1>目录</h1>\n<div class="toc">'
        for i, chapter in enumerate(chapters):
            safe_title = chapter["title"].replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
            chapter_num = i + 1
            toc_content += f'<p><a href="chapter_{chapter_num}.xhtml">{safe_title}</a></p>\n'
        toc_content += '</div>'
        
        toc_page = epub.EpubHtml(title='目录',
                                file_name='toc.xhtml',
                                lang=language)
        toc_page.content = f'''<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head>
    <title>目录</title>
    <link rel="stylesheet" type="text/css" href="style.css" />
    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
</head>
<body>
    {toc_content}
</body>
</html>'''
        book.add_item(toc_page)
        # 添加CSS引用
        toc_page.add_link(href="style.css", rel="stylesheet", type="text/css")
        
        logger.info("已添加目录页")
        
        # 添加章节
        epub_chapters = []
        success_count = 0
        error_count = 0
        
        for i, chapter in enumerate(chapters):
            try:
                content = read_txt_content(chapter['path'])
                content_length = len(content) if content else 0
                logger.info(f"读取章节 '{chapter['title']}' 内容，长度: {content_length} 字节")
                
                if not content or not content.strip():
                    logger.warning(f"章节 '{chapter['title']}' 内容为空，使用默认文本")
                    content = f"（《{chapter['title']}》章节内容为空）"
                
                # 转义内容，确保安全
                safe_title = chapter['title'].replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
                
                # 构建段落HTML
                paragraphs_html = ""
                for p in content.split('\n'):
                    if p.strip():
                        p_safe = p.strip().replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
                        paragraphs_html += f'<p>{p_safe}</p>\n'
                
                # 确保章节内容不为空
                if not paragraphs_html.strip():
                    logger.warning(f"章节 '{chapter['title']}' 格式化后内容为空，使用默认文本")
                    paragraphs_html = f"<p>（《{safe_title}》章节内容为空）</p>"
                
                # 创建章节
                chapter_id = f'chapter_{i+1}'
                file_name = f'{chapter_id}.xhtml'
                
                c = epub.EpubHtml(
                    uid=chapter_id,
                    title=safe_title, 
                    file_name=file_name,
                    lang=language
                )
                
                # 使用更简单的HTML结构
                c.content = f'''<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head>
    <title>{safe_title}</title>
    <link rel="stylesheet" type="text/css" href="style.css" />
    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
</head>
<body>
    <h1>{safe_title}</h1>
    {paragraphs_html}
</body>
</html>'''
                
                # 验证内容长度
                if len(c.content) < 100:
                    logger.warning(f"章节 '{chapter['title']}' 生成的HTML内容过短: {len(c.content)}字节")
                
                # 添加对CSS的引用
                c.add_link(href="style.css", rel="stylesheet", type="text/css")
                
                # 添加到书籍
                book.add_item(c)
                epub_chapters.append(c)
                success_count += 1
                
                logger.info(f"已添加章节 {i+1}/{len(chapters)}: {safe_title} (HTML内容长度: {len(c.content)})")
            except Exception as e:
                logger.error(f"添加章节 '{chapter['title']}' 时出错: {e}")
                error_count += 1
                import traceback
                logger.error(traceback.format_exc())
        
        logger.info(f"章节添加统计: 成功={success_count}, 失败={error_count}, 总计={len(chapters)}")
        
        if success_count == 0:
            logger.error("没有成功添加任何章节，无法继续生成EPUB")
            return None
        
        # 添加导航
        book.add_item(epub.EpubNcx())
        
        # 创建导航文件
        nav = epub.EpubNav()
        nav.add_link(href="style.css", rel="stylesheet", type="text/css")
        book.add_item(nav)
        
        # 设置书籍脊柱（阅读顺序）确保正确顺序
        spine = ['nav']
        spine.append(cover)  # 添加封面
        spine.append(toc_page)  # 添加目录
        for chapter in epub_chapters:
            spine.append(chapter)  # 添加每个章节
        book.spine = spine
        
        logger.info(f"已设置spine，包含 {len(spine)} 个项目")
        
        # 设置目录 - 使用扁平结构以确保兼容性
        book.toc = [
            epub.Link('cover.xhtml', '封面', 'cover'),
            epub.Link('toc.xhtml', '目录', 'toc')
        ]
        
        # 直接添加每个章节到目录，避免使用Section结构
        for i, chapter in enumerate(epub_chapters):
            chapter_num = i + 1
            book.toc.append(epub.Link(f'chapter_{chapter_num}.xhtml', chapter.title, f'chapter_{chapter_num}'))
        
        logger.info(f"已设置TOC，包含 {len(book.toc)} 个项目")
        
        # 添加元数据
        book.add_metadata('DC', 'description', f'{book_name} - 由AI小说工具生成')
        book.add_metadata('DC', 'publisher', 'AI小说工具')
        book.add_metadata('DC', 'rights', '版权归原作者所有')
        book.add_metadata('DC', 'identifier', f'uuid:{str(uuid.uuid4())}', {'id': 'unique-id'})
        
        logger.info("已添加元数据")
        
        # 使用我们的新函数直接创建EPUB文件
        logger.info("使用手动方式创建EPUB文件")
        if write_epub_file_manual(book, output_path):
            print(f"EPUB文件已成功生成: {output_path}")
            return str(output_path)
        else:
            logger.error("手动创建EPUB文件失败")
            
            # 失败后尝试使用ebooklib的方法作为备用
            logger.info("尝试使用ebooklib作为备用方法")
            if write_epub_file(book, output_path):
                print(f"使用备用方法成功生成EPUB文件: {output_path}")
                return str(output_path)
            else:
                logger.error("所有EPUB生成方法都失败")
                return None
    except Exception as e:
        logger.error(f"合并TXT文件时出错: {e}")
        import traceback
        logger.error(f"详细错误: {traceback.format_exc()}")
        return None


def main():
    """主函数，处理命令行参数并执行转换"""
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='将文件夹中的TXT文件合并为EPUB电子书')
    parser.add_argument('folder', help='包含TXT文件的文件夹路径')
    parser.add_argument('-o', '--output', help='输出EPUB文件的路径（可选）')
    parser.add_argument('-a', '--author', help='设置电子书的作者（可选）')
    parser.add_argument('-n', '--name', help='设置电子书的名称（可选，默认从文件名解析）')
    parser.add_argument('-l', '--language', default='zh-CN', help='设置电子书的语言（默认：zh-CN）')
    parser.add_argument('-v', '--verbose', action='store_true', help='显示详细日志')
    parser.add_argument('-q', '--quiet', action='store_true', help='仅显示错误信息')
    
    args = parser.parse_args()
    
    # 设置日志级别
    if args.verbose:
        setup_logger(logging.DEBUG)
    elif args.quiet:
        setup_logger(logging.ERROR)
    
    # 执行转换
    result = merge_txt_to_epub(args.folder, args.output, args.author, args.name, args.language)
    
    # 返回状态码
    if result:
        logger.info(f"转换完成！EPUB文件已保存到: {result}")
        return 0
    else:
        logger.error("转换失败！")
        return 1


if __name__ == "__main__":
    exit_code = main()
    exit(exit_code) 