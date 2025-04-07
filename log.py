#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import logging
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from datetime import datetime
from pathlib import Path
import traceback
import re
import threading
import queue

# 检查是否安装了customtkinter
try:
    import customtkinter as ctk
    HAS_CTK = True
except ImportError:
    HAS_CTK = False

# 全局日志管理器实例
_log_manager_instance = None

class LogManager:
    """
    日志管理类，负责初始化、配置和管理日志系统
    """
    def __init__(self, log_level=logging.INFO):
        """
        初始化日志管理器
        
        Args:
            log_level: 日志级别，默认为INFO
        """
        self.logger = logging.getLogger('novel_app')
        self.logger.setLevel(log_level)
        self.log_queue = queue.Queue()
        self.log_windows = []
        
        # 确保日志目录存在
        self.log_dir = Path("logs")
        self.log_dir.mkdir(exist_ok=True)
        
        # 设置日志格式
        self.formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # 如果没有处理器，添加控制台处理器
        if not self.logger.handlers:
            # 控制台处理器
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(self.formatter)
            self.logger.addHandler(console_handler)
            
            # 队列处理器(用于GUI显示)
            queue_handler = QueueHandler(self.log_queue)
            queue_handler.setFormatter(self.formatter)
            self.logger.addHandler(queue_handler)
            
            # 创建默认的日志文件
            self._setup_default_file_handler()
    
    def _setup_default_file_handler(self):
        """设置默认的文件处理器"""
        default_log_file = self.log_dir / f"novel_app_{datetime.now().strftime('%Y%m%d')}.log"
        file_handler = logging.FileHandler(default_log_file, encoding='utf-8')
        file_handler.setFormatter(self.formatter)
        self.logger.addHandler(file_handler)
        self.info(f"日志文件已创建: {default_log_file}")
    
    def get_logger(self):
        """获取logger实例"""
        return self.logger
    
    def register_window(self, window):
        """注册日志窗口"""
        if window not in self.log_windows:
            self.log_windows.append(window)
    
    def unregister_window(self, window):
        """注销日志窗口"""
        if window in self.log_windows:
            self.log_windows.remove(window)
    
    def debug(self, message):
        """记录DEBUG级别日志"""
        self.logger.debug(message)
    
    def info(self, message):
        """记录INFO级别日志"""
        self.logger.info(message)
    
    def warning(self, message):
        """记录WARNING级别日志"""
        self.logger.warning(message)
    
    def error(self, message):
        """记录ERROR级别日志"""
        self.logger.error(message)
    
    def critical(self, message):
        """记录CRITICAL级别日志"""
        self.logger.critical(message)
    
    def exception(self, message):
        """记录异常信息"""
        self.logger.exception(message)
    
    def save_log_to_file(self, filename=None):
        """
        保存日志到文件
        
        Args:
            filename: 文件名或完整路径，如果为None则使用当前时间生成默认文件名
        
        Returns:
            保存的文件路径
        """
        if filename is None:
            filename = f"novel_app_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        
        # 检查是否是完整路径
        file_path = Path(filename)
        if not file_path.is_absolute():
            # 如果不是完整路径，则保存到日志目录
            # 确保日志目录存在
            self.log_dir.mkdir(exist_ok=True)
            # 构建完整文件路径
            file_path = self.log_dir / filename
        
        # 从日志窗口获取日志文本
        log_text = ""
        for window in self.log_windows:
            if hasattr(window, 'get_log_text'):
                log_text = window.get_log_text()
                break
        
        # 如果没有日志窗口或无法获取日志文本，记录错误
        if not log_text:
            self.error("无法获取日志文本以保存到文件")
            return None
        
        try:
            # 确保目标目录存在
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(log_text)
            self.info(f"日志已保存到: {file_path}")
            return file_path
        except Exception as e:
            self.error(f"保存日志文件时出错: {e}")
            return None


class QueueHandler(logging.Handler):
    """
    将日志记录放入队列的处理器
    """
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue
    
    def emit(self, record):
        try:
            msg = self.format(record)
            self.log_queue.put((record, msg))
        except Exception:
            self.handleError(record)


class LogWindow:
    """
    日志窗口类，用于显示日志信息
    """
    def __init__(self, parent, log_manager=None):
        """
        初始化日志窗口
        
        Args:
            parent: 父窗口
            log_manager: 日志管理器实例
        """
        self.parent = parent
        
        # 如果没有提供日志管理器，使用全局实例
        if log_manager is None:
            self.log_manager = get_log_manager()
        else:
            self.log_manager = log_manager
        
        # 创建窗口
        self._create_window()
        
        # 注册窗口到日志管理器
        self.log_manager.register_window(self)
        
        # 启动日志更新线程
        self.running = True
        self.update_thread = threading.Thread(target=self._update_log_from_queue)
        self.update_thread.daemon = True
        self.update_thread.start()
        
        # 记录窗口打开的日志
        self.log_manager.info("日志窗口已打开")
    
    def _create_window(self):
        """创建日志窗口UI"""
        if HAS_CTK:
            self._create_ctk_window()
        else:
            self._create_tk_window()
    
    def _create_ctk_window(self):
        """创建CustomTkinter风格的窗口"""
        # 创建窗口
        self.window = ctk.CTkToplevel(self.parent)
        self.window.title("操作日志")
        self.window.geometry("900x600")
        self.window.protocol("WM_DELETE_WINDOW", self._on_close)
        
        # 主框架
        main_frame = ctk.CTkFrame(self.window)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # 标题
        ctk.CTkLabel(
            main_frame,
            text="系统日志",
            font=ctk.CTkFont(size=18, weight="bold")
        ).pack(pady=(0, 10))
        
        # 日志级别过滤器
        filter_frame = ctk.CTkFrame(main_frame)
        filter_frame.pack(fill=tk.X, pady=(0, 10))
        
        ctk.CTkLabel(filter_frame, text="日志级别:").pack(side=tk.LEFT, padx=(0, 5))
        
        self.level_var = tk.StringVar(value="INFO")
        level_combo = ctk.CTkComboBox(
            filter_frame,
            values=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
            variable=self.level_var,
            command=self._on_level_change,
            width=120
        )
        level_combo.pack(side=tk.LEFT, padx=5)
        
        # 清空按钮
        ctk.CTkButton(
            filter_frame,
            text="清空日志",
            command=self._on_clear,
            width=100
        ).pack(side=tk.RIGHT)
        
        # 搜索框
        search_frame = ctk.CTkFrame(main_frame)
        search_frame.pack(fill=tk.X, pady=(0, 10))
        
        ctk.CTkLabel(search_frame, text="搜索:").pack(side=tk.LEFT, padx=(0, 5))
        
        self.search_var = tk.StringVar()
        search_entry = ctk.CTkEntry(
            search_frame,
            textvariable=self.search_var,
            width=250
        )
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        # 绑定回车键搜索
        search_entry.bind("<Return>", lambda e: self._on_search())
        
        ctk.CTkButton(
            search_frame,
            text="搜索",
            command=self._on_search,
            width=80
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        ctk.CTkButton(
            search_frame,
            text="清除搜索",
            command=self._on_clear_search,
            width=80
        ).pack(side=tk.LEFT)
        
        # 日志文本区域
        log_frame = ctk.CTkFrame(main_frame)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # 使用标准tkinter Text组件替代CTkTextbox，解决tag_configure问题
        self.log_text = tk.Text(log_frame, wrap="none", bg="#2b2b2b", fg="white", 
                        font=("Microsoft YaHei UI", 10))
        
        # 添加滚动条
        scrollbar = ctk.CTkScrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 日志文本添加标签配置
        self.log_text.tag_configure("DEBUG", foreground="#808080")  # 灰色
        self.log_text.tag_configure("INFO", foreground="#ffffff")   # 白色
        self.log_text.tag_configure("WARNING", foreground="#ff9900")  # 橙色
        self.log_text.tag_configure("ERROR", foreground="#ff0000")   # 红色
        self.log_text.tag_configure("CRITICAL", foreground="#ff00ff")  # 紫色
        self.log_text.tag_configure("HIGHLIGHT", background="#444444")  # 高亮搜索结果
        
        # 底部按钮区域
        button_frame = ctk.CTkFrame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        # 自动滚动选项
        self.auto_scroll_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            button_frame,
            text="自动滚动",
            variable=self.auto_scroll_var,
            width=20
        ).pack(side=tk.LEFT)
        
        # 保存按钮组
        save_frame = ctk.CTkFrame(button_frame, fg_color="transparent")
        save_frame.pack(side=tk.RIGHT)
        
        # 另存为按钮 - 新增
        ctk.CTkButton(
            save_frame,
            text="另存为",
            command=self._on_save_as,
            width=100
        ).pack(side=tk.RIGHT, padx=(10, 0))
        
        # 保存按钮
        ctk.CTkButton(
            save_frame,
            text="保存日志",
            command=self._on_save,
            width=100
        ).pack(side=tk.RIGHT, padx=(10, 0))
        
        # 关闭按钮
        ctk.CTkButton(
            save_frame,
            text="关闭",
            command=self._on_close,
            width=100
        ).pack(side=tk.RIGHT)
    
    def _create_tk_window(self):
        """创建Tkinter风格的窗口"""
        # 创建窗口
        self.window = tk.Toplevel(self.parent)
        self.window.title("操作日志")
        self.window.geometry("900x600")
        self.window.protocol("WM_DELETE_WINDOW", self._on_close)
        
        # 主框架
        main_frame = ttk.Frame(self.window, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 标题
        ttk.Label(
            main_frame,
            text="系统日志",
            font=("TkDefaultFont", 14, "bold")
        ).pack(pady=(0, 10))
        
        # 日志级别过滤器
        filter_frame = ttk.Frame(main_frame)
        filter_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(filter_frame, text="日志级别:").pack(side=tk.LEFT, padx=(0, 5))
        
        self.level_var = tk.StringVar(value="INFO")
        level_combo = ttk.Combobox(
            filter_frame,
            textvariable=self.level_var,
            values=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
            state="readonly",
            width=15
        )
        level_combo.pack(side=tk.LEFT, padx=5)
        level_combo.bind("<<ComboboxSelected>>", lambda e: self._on_level_change(self.level_var.get()))
        
        # 清空按钮
        ttk.Button(
            filter_frame,
            text="清空日志",
            command=self._on_clear
        ).pack(side=tk.RIGHT)
        
        # 搜索框
        search_frame = ttk.Frame(main_frame)
        search_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(search_frame, text="搜索:").pack(side=tk.LEFT, padx=(0, 5))
        
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(
            search_frame,
            textvariable=self.search_var
        )
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        # 绑定回车键搜索
        search_entry.bind("<Return>", lambda e: self._on_search())
        
        ttk.Button(
            search_frame,
            text="搜索",
            command=self._on_search
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Button(
            search_frame,
            text="清除搜索",
            command=self._on_clear_search
        ).pack(side=tk.LEFT)
        
        # 日志文本区域
        log_frame = ttk.Frame(main_frame)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        self.log_text = tk.Text(log_frame, wrap="none")
        log_scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scrollbar.set)
        
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 日志文本添加标签配置
        self.log_text.tag_configure("DEBUG", foreground="#808080")  # 灰色
        self.log_text.tag_configure("INFO", foreground="#000000")   # 黑色
        self.log_text.tag_configure("WARNING", foreground="#ff9900")  # 橙色
        self.log_text.tag_configure("ERROR", foreground="#ff0000")   # 红色
        self.log_text.tag_configure("CRITICAL", foreground="#ff00ff")  # 紫色
        self.log_text.tag_configure("HIGHLIGHT", background="#dddddd")  # 高亮搜索结果
        
        # 底部按钮区域
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        # 自动滚动选项
        self.auto_scroll_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            button_frame,
            text="自动滚动",
            variable=self.auto_scroll_var
        ).pack(side=tk.LEFT)
        
        # 另存为按钮 - 新增
        ttk.Button(
            button_frame,
            text="另存为",
            command=self._on_save_as
        ).pack(side=tk.RIGHT, padx=(10, 0))
        
        # 保存按钮
        ttk.Button(
            button_frame,
            text="保存日志",
            command=self._on_save
        ).pack(side=tk.RIGHT, padx=(10, 0))
        
        # 关闭按钮
        ttk.Button(
            button_frame,
            text="关闭",
            command=self._on_close
        ).pack(side=tk.RIGHT)
    
    def _update_log_from_queue(self):
        """从队列中更新日志显示"""
        while self.running:
            try:
                # 等待队列中的新日志记录，每100ms超时一次(允许线程退出检查)
                try:
                    record, message = self.log_manager.log_queue.get(block=True, timeout=0.1)
                except queue.Empty:
                    continue
                
                # 检查日志级别是否符合当前过滤条件
                if self._should_display_log(record):
                    self._append_log(record, message)
                
                # 标记处理完成
                self.log_manager.log_queue.task_done()
            except Exception as e:
                # 避免线程崩溃
                print(f"日志更新线程出错: {e}")
        
        print("日志更新线程已退出")
    
    def _should_display_log(self, record):
        """检查是否应显示该日志记录"""
        level_map = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL
        }
        
        selected_level = level_map.get(self.level_var.get(), logging.INFO)
        return record.levelno >= selected_level
    
    def _append_log(self, record, message):
        """添加日志到文本框"""
        if not hasattr(self, 'log_text') or not self.log_text.winfo_exists():
            return
        
        # 获取对应日志级别的标签
        level_name = record.levelname
        tag = level_name if level_name in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] else "INFO"
        
        try:
            # 添加日志
            self.log_text.configure(state="normal")
            self.log_text.insert("end", message + "\n", tag)
            
            # 如果自动滚动开启，则滚动到最新的日志
            if self.auto_scroll_var.get():
                self.log_text.see("end")
            
            self.log_text.configure(state="disabled")
        except tk.TclError:
            # 窗口可能已被销毁
            pass
    
    def _on_level_change(self, level):
        """日志级别改变处理"""
        # 清空当前显示的日志
        try:
            self.log_text.configure(state="normal")
            self.log_text.delete("1.0", "end")
            self.log_text.configure(state="disabled")
            
            # 记录级别变更
            self.log_manager.info(f"日志显示级别已更改为: {level}")
        except tk.TclError:
            # 窗口可能已被销毁
            pass
    
    def _on_search(self):
        """搜索处理"""
        search_text = self.search_var.get().strip()
        if not search_text:
            return
        
        try:
            # 移除现有高亮
            self.log_text.tag_remove("HIGHLIGHT", "1.0", "end")
            
            # 搜索并高亮匹配文本
            start_pos = "1.0"
            while True:
                start_pos = self.log_text.search(search_text, start_pos, "end", nocase=True)
                if not start_pos:
                    break
                
                end_pos = f"{start_pos}+{len(search_text)}c"
                self.log_text.tag_add("HIGHLIGHT", start_pos, end_pos)
                start_pos = end_pos
            
            # 记录搜索动作
            self.log_manager.info(f"日志搜索: {search_text}")
        except tk.TclError:
            # 窗口可能已被销毁
            pass
    
    def _on_clear_search(self):
        """清除搜索高亮"""
        self.search_var.set("")
        try:
            self.log_text.tag_remove("HIGHLIGHT", "1.0", "end")
            
            # 记录清除搜索
            self.log_manager.info("已清除日志搜索高亮")
        except tk.TclError:
            # 窗口可能已被销毁
            pass
    
    def _on_clear(self):
        """清空日志"""
        try:
            self.log_text.configure(state="normal")
            self.log_text.delete("1.0", "end")
            self.log_text.configure(state="disabled")
            
            # 记录清空动作
            self.log_manager.info("日志已清空")
        except tk.TclError:
            # 窗口可能已被销毁
            pass
    
    def _on_save(self):
        """保存日志到文件"""
        try:
            # 保存日志
            default_filename = f"novel_app_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
            file_path = self.log_manager.save_log_to_file(default_filename)
            
            if file_path:
                messagebox.showinfo("保存成功", f"日志已保存到:\n{file_path}", parent=self.window)
            else:
                messagebox.showerror("保存失败", "保存日志文件时出错，请检查日志。", parent=self.window)
        except Exception as e:
            messagebox.showerror("错误", f"保存日志时出错:\n{e}", parent=self.window)
            self.log_manager.error(f"保存日志时出错: {e}")
    
    def _on_save_as(self):
        """保存日志到自定义文件"""
        try:
            # 获取文件名
            default_filename = f"novel_app_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
            filename = filedialog.asksaveasfilename(
                parent=self.window,
                title="另存为",
                initialdir=str(self.log_manager.log_dir),
                initialfile=default_filename,
                defaultextension=".log",
                filetypes=[("日志文件", "*.log"), ("文本文件", "*.txt"), ("所有文件", "*.*")]
            )
            
            if not filename:
                return
            
            # 保存日志 - 直接使用完整路径
            file_path = self.log_manager.save_log_to_file(filename)
            
            if file_path:
                messagebox.showinfo("保存成功", f"日志已保存到:\n{file_path}", parent=self.window)
            else:
                messagebox.showerror("保存失败", "保存日志文件时出错，请检查日志。", parent=self.window)
        except Exception as e:
            messagebox.showerror("错误", f"保存日志时出错:\n{e}", parent=self.window)
            self.log_manager.error(f"保存日志时出错: {e}")
    
    def _on_close(self):
        """关闭窗口"""
        # 停止更新线程
        self.running = False
        
        try:
            # 注销窗口
            self.log_manager.unregister_window(self)
            
            # 记录窗口关闭
            self.log_manager.info("日志窗口已关闭")
            
            # 销毁窗口
            self.window.destroy()
        except:
            # 忽略关闭时的错误
            pass
    
    def get_log_text(self):
        """获取日志文本内容"""
        try:
            return self.log_text.get("1.0", "end")
        except:
            return ""


# --- 辅助函数 ---

def get_log_manager():
    """
    获取日志管理器实例，如果不存在则创建
    
    Returns:
        LogManager实例
    """
    global _log_manager_instance
    
    if _log_manager_instance is None:
        _log_manager_instance = LogManager()
    
    return _log_manager_instance


def show_log_window(parent):
    """
    显示日志窗口
    
    Args:
        parent: 父窗口
    
    Returns:
        LogWindow实例
    """
    log_manager = get_log_manager()
    return LogWindow(parent, log_manager)


# --- 函数装饰器 ---

def log_operation(level=logging.INFO, show_args=False):
    """
    操作日志装饰器，用于记录函数调用
    
    Args:
        level: 日志级别
        show_args: 是否显示函数参数
    
    Returns:
        装饰器函数
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            log_manager = get_log_manager()
            logger = log_manager.get_logger()
            
            # 获取函数名称和模块
            func_name = func.__name__
            module_name = func.__module__
            
            # 构建日志消息
            if show_args:
                # 过滤掉self参数
                filtered_args = args[1:] if args and hasattr(args[0], func_name) else args
                args_str = ', '.join([str(arg) for arg in filtered_args])
                kwargs_str = ', '.join([f"{k}={v}" for k, v in kwargs.items()])
                params = []
                if args_str:
                    params.append(args_str)
                if kwargs_str:
                    params.append(kwargs_str)
                params_str = ', '.join(params)
                message = f"调用 {module_name}.{func_name}({params_str})"
            else:
                message = f"调用 {module_name}.{func_name}"
            
            # 记录函数调用
            logger.log(level, message)
            
            try:
                # 执行原函数
                result = func(*args, **kwargs)
                
                # 记录成功完成
                logger.log(level, f"{module_name}.{func_name} 执行成功")
                
                return result
            except Exception as e:
                # 记录错误
                logger.error(f"{module_name}.{func_name} 执行出错: {e}")
                logger.error(traceback.format_exc())
                raise
        
        return wrapper
    
    return decorator
