#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import json
import requests
import logging
from typing import Dict, List, Any, Optional, Union, Callable
import time
import asyncio
import re
import traceback
from datetime import datetime
import configparser
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, Toplevel, Frame, Label, Button, Entry, Text, Scrollbar
from pathlib import Path

try:
    import customtkinter as ctk

    HAS_CTK = True
except ImportError:
    print("Warning: CustomTkinter库未找到。将使用默认Tkinter主题")
    HAS_CTK = False

# 全局变量
_ai_engine_instance = None
_config_path = Path("config/ai_config.json")


class AIEngine:
    """
    AI引擎类，负责与各种AI API进行交互
    """

    def __init__(self, config: dict = None):
        """
        初始化AI引擎

        Args:
            config: 配置字典，包含API密钥等信息
        """
        self.config = config or {}
        self.logger = logging.getLogger(__name__)
        self._setup_logging()

    def _setup_logging(self):
        """设置日志"""
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)

    def update_config(self, config: Dict[str, Any]):
        """
        更新配置

        Args:
            config: 新的配置字典
        """
        self.config.update(config)
        self.logger.info(
            f"AI引擎配置已更新: {config.get('provider', 'Unknown')} - {config.get('model_name', 'Unknown')}")

    def _get_headers(self) -> dict:
        """获取请求头"""
        provider = self.config.get("provider", "OpenAI")
        api_key = self.config.get("api_key", "")

        # 根据提供商设置不同的请求头
        if provider == "智谱AI":
            return {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }
        elif provider == "硅基流动":
            return {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }
        elif provider == "讯飞星火":
            return {
                "Content-Type": "application/json",
                "Authorization": api_key
            }
        elif provider == "百度文心":
            return {
                "Content-Type": "application/json",
                "Authorization": api_key
            }
        else:
            # OpenAI及兼容OpenAI的API
            return {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }

    def _build_messages(self, prompt: str, system_prompt: Optional[str] = None) -> List[Dict[str, str]]:
        """
        构建消息列表

        Args:
            prompt: 用户提示
            system_prompt: 系统提示

        Returns:
            消息列表
        """
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        return messages

    def _build_request_body(self, system_prompt: str, user_prompt: str, stream: bool = False) -> dict:
        """
        构建请求体
        """
        provider = self.config.get("provider", "OpenAI")
        model_name = self.config.get("model_name", "gpt-4-turbo")
        max_tokens = self.config.get("max_tokens", 4000)

        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "max_tokens": max_tokens
        }

        if stream:
            payload["stream"] = True

        # 根据不同提供商调整请求参数
        if provider == "智谱AI":
            payload["do_sample"] = True
            if "max_tokens" in payload:
                payload["max_tokens"] = min(payload["max_tokens"], 8192)
        elif provider == "硅基流动":
            payload["temperature"] = 0.7

        return payload

    def generate_text(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """
        生成文本

        Args:
            prompt: 用户提示
            system_prompt: 系统提示

        Returns:
            生成的文本
        """
        provider = self.config.get("provider", "OpenAI")
        api_url = self.config.get("api_url", "https://api.openai.com/v1/chat/completions")

        if not api_url:
            raise ValueError("API URL未设置")

        headers = self._get_headers()
        payload = self._build_request_body(system_prompt or "", prompt, stream=False)

        try:
            response = requests.post(api_url, headers=headers, json=payload)
            response.raise_for_status()

            response_data = response.json()
            return self._parse_response(response_data)
        except Exception as e:
            self.logger.error(f"生成文本时出错: {e}")
            raise

    def _parse_response(self, response_data: dict) -> str:
        """解析API响应数据"""
        provider = self.config.get("provider", "OpenAI")

        try:
            if provider == "智谱AI":
                if "choices" in response_data:
                    choice = response_data["choices"][0]
                    if "message" in choice:
                        return choice["message"].get("content", "")
                    else:
                        return choice.get("content", "")
            elif provider == "硅基流动":
                if "choices" in response_data:
                    choice = response_data["choices"][0]
                    if "message" in choice:
                        return choice["message"].get("content", "")
                    else:
                        return choice.get("content", "")
            else:
                # 默认OpenAI格式
                if "choices" in response_data:
                    choice = response_data["choices"][0]
                    if "message" in choice:
                        return choice["message"].get("content", "")
                    else:
                        return choice.get("content", "")

            # 如果无法解析，返回响应的字符串表示
            return str(response_data)
        except Exception as e:
            self.logger.error(f"解析响应时出错: {e}")
            return str(response_data)

    def optimize_content(self, original_content: str, optimize_config: dict) -> str:
        """
        优化内容

        Args:
            original_content: 原始内容
            optimize_config: 优化配置
                - word_count_option: 字数处理方式 ("保持原有字数", "缩减字数", "扩展字数")
                - word_count_ratio: 字数比例 (50-300%)
                - similarity: 保留相似度 (10-90%)
                - optimize_skills: 是否优化功法描写
                - optimize_scenes: 是否优化场景描写
                - optimize_characters: 是否优化人物刻画
                - optimize_plot: 是否优化情节结构
                - custom_requirements: 自定义优化要求

        Returns:
            优化后的内容
        """
        system_prompt = """你是一位专业的小说优化助手，擅长根据用户要求改写和优化小说内容。
请根据以下要求优化用户提供的小说内容："""

        user_prompt = f"原始内容：\n{original_content}\n\n优化要求："

        # 字数处理
        word_count_option = optimize_config.get("word_count_option", "保持原有字数")
        word_count_ratio = optimize_config.get("word_count_ratio", 100)
        user_prompt += f"\n- 字数要求：{word_count_option}"
        if word_count_option != "保持原有字数":
            user_prompt += f"，目标为原文的{word_count_ratio}%"

        # 相似度
        similarity = optimize_config.get("similarity", 70)
        user_prompt += f"\n- 保留原文相似度：{similarity}%"

        # 优化选项
        if optimize_config.get("optimize_skills", False):
            user_prompt += "\n- 优化功法描写，使其更加生动和符合武侠/仙侠小说风格"

        if optimize_config.get("optimize_scenes", False):
            user_prompt += "\n- 优化场景描写，增加环境细节和氛围感"

        if optimize_config.get("optimize_characters", False):
            user_prompt += "\n- 优化人物刻画，使角色更加立体和生动"

        if optimize_config.get("optimize_plot", False):
            user_prompt += "\n- 优化情节结构，使故事发展更加合理和吸引人"

        # 自定义要求
        custom_requirements = optimize_config.get("custom_requirements", "")
        if custom_requirements:
            user_prompt += f"\n- 其他要求：{custom_requirements}"

        user_prompt += "\n\n请直接返回优化后的内容，不要包含任何解释或其他文本。"

        return self.generate_text(user_prompt, system_prompt)

    def is_configured(self) -> bool:
        """
        检查AI引擎是否已正确配置

        Returns:
            bool: 配置是否有效
        """
        api_key = self.config.get("api_key", "")
        api_url = self.config.get("api_url", "")
        model_name = self.config.get("model_name", "")

        # 判断是否有有效的API密钥和URL
        return bool(api_key and api_url and model_name)


class ConfigDialog:
    """AI配置对话框，用于设置AI引擎相关参数"""

    def __init__(self, parent, ai_engine=None, config=None):
        """
        初始化配置对话框

        Args:
            parent: 父窗口
            ai_engine: AI引擎实例，如果提供则会自动更新配置
            config: 初始配置字典
        """
        self.parent = parent
        self.ai_engine = ai_engine

        # 如果传入AI引擎，则使用其配置，否则加载配置文件
        if ai_engine and hasattr(ai_engine, 'config'):
            self.config = ai_engine.config.copy()
        elif config:
            self.config = config.copy()
        else:
            self.config = load_ai_config()

        self.result = None

        self._create_dialog()

    def _create_dialog(self):
        """创建对话框界面"""
        if HAS_CTK:
            self.dialog = ctk.CTkToplevel(self.parent)
            self._create_ctk_ui()
        else:
            self.dialog = Toplevel(self.parent)
            self._create_tk_ui()

        self.dialog.title("AI模型配置")
        self.dialog.geometry("500x550")
        self.dialog.transient(self.parent)
        self.dialog.grab_set()

        # 确保对话框居中显示
        self.dialog.update_idletasks()
        screen_width = self.dialog.winfo_screenwidth()
        screen_height = self.dialog.winfo_screenheight()
        x = (screen_width - self.dialog.winfo_width()) // 2
        y = (screen_height - self.dialog.winfo_height()) // 2
        self.dialog.geometry(f"+{x}+{y}")

        # 加载现有配置
        self._load_config()

        # 等待对话框关闭
        self.dialog.wait_window(self.dialog)

    def _create_ctk_ui(self):
        """创建CustomTkinter UI"""
        dialog = self.dialog

        # 主框架
        main_frame = ctk.CTkFrame(dialog)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # 标题
        ctk.CTkLabel(
            main_frame,
            text="AI模型配置",
            font=ctk.CTkFont(size=18, weight="bold")
        ).pack(pady=(0, 20))

        # 创建选项卡
        tab_view = ctk.CTkTabview(main_frame)
        tab_view.pack(fill=tk.BOTH, expand=True)

        # 创建标签页
        general_tab = tab_view.add("通用配置")
        advanced_tab = tab_view.add("高级设置")

        # === 通用配置标签页 ===
        general_frame = ctk.CTkFrame(general_tab)
        general_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 模型提供商
        ctk.CTkLabel(general_frame, text="模型提供商:").pack(anchor=tk.W, pady=(10, 5))

        self.provider_var = tk.StringVar()
        provider_combo = ctk.CTkComboBox(
            general_frame,
            values=["OpenAI", "智谱AI", "讯飞星火", "百度文心", "硅基流动", "自定义"],
            variable=self.provider_var,
            width=350
        )
        provider_combo.pack(fill=tk.X, pady=(0, 15))

        # API密钥
        ctk.CTkLabel(general_frame, text="API密钥:").pack(anchor=tk.W, pady=(0, 5))

        key_frame = ctk.CTkFrame(general_frame)
        key_frame.pack(fill=tk.X, pady=(0, 15))

        self.api_key_var = tk.StringVar()
        self.api_key_entry = ctk.CTkEntry(
            key_frame,
            textvariable=self.api_key_var,
            show="*",
            width=300
        )
        self.api_key_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.show_key_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            key_frame,
            text="显示",
            variable=self.show_key_var,
            command=self._toggle_key_visibility,
            width=20
        ).pack(side=tk.RIGHT, padx=(10, 0))

        # API URL
        ctk.CTkLabel(general_frame, text="API URL:").pack(anchor=tk.W, pady=(0, 5))

        self.api_url_var = tk.StringVar()
        ctk.CTkEntry(
            general_frame,
            textvariable=self.api_url_var,
            width=350
        ).pack(fill=tk.X, pady=(0, 15))

        # 模型名称
        ctk.CTkLabel(general_frame, text="模型名称:").pack(anchor=tk.W, pady=(0, 5))

        self.model_name_var = tk.StringVar()
        ctk.CTkEntry(
            general_frame,
            textvariable=self.model_name_var,
            width=350
        ).pack(fill=tk.X, pady=(0, 15))

        # === 高级设置标签页 ===
        advanced_frame = ctk.CTkFrame(advanced_tab)
        advanced_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 最大Token数
        ctk.CTkLabel(advanced_frame, text="最大Token数:").pack(anchor=tk.W, pady=(10, 5))

        self.max_tokens_var = tk.IntVar(value=4000)
        ctk.CTkSlider(
            advanced_frame,
            from_=500,
            to=16000,
            number_of_steps=155,
            variable=self.max_tokens_var
        ).pack(fill=tk.X, pady=(0, 5))

        max_tokens_display = ctk.CTkLabel(advanced_frame, text="4000")
        max_tokens_display.pack(anchor=tk.E, pady=(0, 15))

        def update_max_tokens_label(*args):
            max_tokens_display.configure(text=str(self.max_tokens_var.get()))

        self.max_tokens_var.trace_add("write", update_max_tokens_label)

        # 代理设置
        proxy_frame = ctk.CTkFrame(advanced_frame)
        proxy_frame.pack(fill=tk.X, pady=(10, 15))

        self.use_proxy_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            proxy_frame,
            text="使用代理",
            variable=self.use_proxy_var,
            command=self._toggle_proxy_state
        ).pack(anchor=tk.W, padx=10, pady=10)

        self.proxy_url_var = tk.StringVar()
        self.proxy_url_entry = ctk.CTkEntry(
            proxy_frame,
            textvariable=self.proxy_url_var,
            placeholder_text="http://127.0.0.1:7890"
        )
        self.proxy_url_entry.pack(fill=tk.X, padx=10, pady=(0, 10))
        self.proxy_url_entry.configure(state="disabled")

        # 底部按钮
        button_frame = ctk.CTkFrame(main_frame)
        button_frame.pack(fill=tk.X, pady=(20, 0))

        ctk.CTkButton(
            button_frame,
            text="测试连接",
            command=self._test_connection
        ).pack(side=tk.LEFT)

        ctk.CTkButton(
            button_frame,
            text="取消",
            command=self._on_cancel
        ).pack(side=tk.RIGHT, padx=(10, 0))

        ctk.CTkButton(
            button_frame,
            text="保存",
            command=self._on_save
        ).pack(side=tk.RIGHT)

    def _create_tk_ui(self):
        """创建Tkinter UI"""
        dialog = self.dialog

        # 主框架
        main_frame = ttk.Frame(dialog, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 标题
        ttk.Label(
            main_frame,
            text="AI模型配置",
            font=("TkDefaultFont", 14, "bold")
        ).pack(pady=(0, 20))

        # 创建选项卡
        tab_control = ttk.Notebook(main_frame)
        tab_control.pack(fill=tk.BOTH, expand=True)

        # 创建标签页
        general_tab = ttk.Frame(tab_control, padding=10)
        advanced_tab = ttk.Frame(tab_control, padding=10)

        tab_control.add(general_tab, text="通用配置")
        tab_control.add(advanced_tab, text="高级设置")

        # === 通用配置标签页 ===
        # 模型提供商
        ttk.Label(general_tab, text="模型提供商:").pack(anchor=tk.W, pady=(10, 5))

        self.provider_var = tk.StringVar()
        provider_combo = ttk.Combobox(
            general_tab,
            textvariable=self.provider_var,
            values=["OpenAI", "智谱AI", "讯飞星火", "百度文心", "硅基流动", "自定义"]
        )
        provider_combo.pack(fill=tk.X, pady=(0, 15))

        # API密钥
        ttk.Label(general_tab, text="API密钥:").pack(anchor=tk.W, pady=(0, 5))

        key_frame = ttk.Frame(general_tab)
        key_frame.pack(fill=tk.X, pady=(0, 15))

        self.api_key_var = tk.StringVar()
        self.api_key_entry = ttk.Entry(
            key_frame,
            textvariable=self.api_key_var,
            show="*"
        )
        self.api_key_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.show_key_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            key_frame,
            text="显示",
            variable=self.show_key_var,
            command=self._toggle_key_visibility
        ).pack(side=tk.RIGHT, padx=(10, 0))

        # API URL
        ttk.Label(general_tab, text="API URL:").pack(anchor=tk.W, pady=(0, 5))

        self.api_url_var = tk.StringVar()
        ttk.Entry(
            general_tab,
            textvariable=self.api_url_var
        ).pack(fill=tk.X, pady=(0, 15))

        # 模型名称
        ttk.Label(general_tab, text="模型名称:").pack(anchor=tk.W, pady=(0, 5))

        self.model_name_var = tk.StringVar()
        ttk.Entry(
            general_tab,
            textvariable=self.model_name_var
        ).pack(fill=tk.X, pady=(0, 15))

        # === 高级设置标签页 ===
        # 最大Token数
        ttk.Label(advanced_tab, text="最大Token数:").pack(anchor=tk.W, pady=(10, 5))

        token_frame = ttk.Frame(advanced_tab)
        token_frame.pack(fill=tk.X, pady=(0, 15))

        self.max_tokens_var = tk.IntVar(value=4000)
        ttk.Scale(
            token_frame,
            from_=500,
            to=16000,
            variable=self.max_tokens_var,
            orient=tk.HORIZONTAL
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        max_tokens_display = ttk.Label(token_frame, text="4000", width=8)
        max_tokens_display.pack(side=tk.RIGHT, padx=(10, 0))

        def update_max_tokens_label(*args):
            max_tokens_display.configure(text=str(self.max_tokens_var.get()))

        self.max_tokens_var.trace_add("write", update_max_tokens_label)

        # 代理设置
        proxy_frame = ttk.LabelFrame(advanced_tab, text="代理设置")
        proxy_frame.pack(fill=tk.X, pady=(10, 15))

        self.use_proxy_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            proxy_frame,
            text="使用代理",
            variable=self.use_proxy_var,
            command=self._toggle_proxy_state
        ).pack(anchor=tk.W, padx=10, pady=10)

        self.proxy_url_var = tk.StringVar()
        self.proxy_url_entry = ttk.Entry(
            proxy_frame,
            textvariable=self.proxy_url_var
        )
        self.proxy_url_entry.pack(fill=tk.X, padx=10, pady=(0, 10))
        self.proxy_url_entry.configure(state="disabled")

        # 底部按钮
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(20, 0))

        ttk.Button(
            button_frame,
            text="测试连接",
            command=self._test_connection
        ).pack(side=tk.LEFT)

        ttk.Button(
            button_frame,
            text="取消",
            command=self._on_cancel
        ).pack(side=tk.RIGHT, padx=(10, 0))

        ttk.Button(
            button_frame,
            text="保存",
            command=self._on_save
        ).pack(side=tk.RIGHT)

    def _toggle_key_visibility(self):
        """切换API密钥显示/隐藏"""
        if self.show_key_var.get():
            self.api_key_entry.configure(show="")
        else:
            self.api_key_entry.configure(show="*")

    def _toggle_proxy_state(self):
        """切换代理设置状态"""
        if self.use_proxy_var.get():
            self.proxy_url_entry.configure(state="normal")
        else:
            self.proxy_url_entry.configure(state="disabled")

    def _load_config(self):
        """加载配置到UI"""
        # 从配置对象加载
        config = self.config

        # 设置UI控件
        if "provider" in config:
            self.provider_var.set(config["provider"])
        if "api_key" in config:
            self.api_key_var.set(config["api_key"])
        if "api_url" in config:
            self.api_url_var.set(config["api_url"])
        if "model_name" in config:
            self.model_name_var.set(config["model_name"])
        if "max_tokens" in config:
            self.max_tokens_var.set(config["max_tokens"])

        # 代理设置
        if "proxy" in config and config["proxy"]:
            self.use_proxy_var.set(True)
            self.proxy_url_var.set(config["proxy"])
            self.proxy_url_entry.configure(state="normal")
        elif "proxy_url" in config and config["proxy_url"]:
            self.use_proxy_var.set(True)
            self.proxy_url_var.set(config["proxy_url"])
            self.proxy_url_entry.configure(state="normal")

    def _get_config(self):
        """从UI获取配置"""
        return {
            "provider": self.provider_var.get(),
            "api_key": self.api_key_var.get(),
            "api_url": self.api_url_var.get(),
            "model_name": self.model_name_var.get(),
            "max_tokens": self.max_tokens_var.get(),
            "proxy": self.proxy_url_var.get() if self.use_proxy_var.get() else ""
        }

    def _test_connection(self):
        """测试API连接"""
        config = self._get_config()

        if not config["api_key"]:
            messagebox.showerror("错误", "请先输入API密钥", parent=self.dialog)
            return

        try:
            self.dialog.config(cursor="wait")
            self.dialog.update()

            # 创建临时AI引擎测试连接
            test_engine = AIEngine(config)

            # 简单的测试提示
            test_prompt = "Hello, please respond with a simple greeting."
            response = test_engine.generate_text(test_prompt)

            self.dialog.config(cursor="")
            messagebox.showinfo("连接成功", f"API连接测试成功！\n\n响应: {response[:100]}...", parent=self.dialog)
        except Exception as e:
            self.dialog.config(cursor="")
            error_msg = str(e)
            if len(error_msg) > 500:
                error_msg = error_msg[:500] + "..."
            messagebox.showerror("连接失败", f"无法连接到API:\n\n{error_msg}", parent=self.dialog)

    def _on_save(self):
        """保存配置并关闭对话框"""
        config = self._get_config()

        # 验证必填字段
        if not config["api_key"]:
            messagebox.showerror("错误", "API密钥不能为空", parent=self.dialog)
            return

        if not config["api_url"]:
            messagebox.showerror("错误", "API URL不能为空", parent=self.dialog)
            return

        if not config["model_name"]:
            messagebox.showerror("错误", "模型名称不能为空", parent=self.dialog)
            return

        # 更新AI引擎配置（如果提供）
        if self.ai_engine:
            self.ai_engine.update_config(config)

        # 保存配置到结果
        self.result = config

        # 保存到配置文件
        self._save_to_config_file(config)

        # 关闭对话框
        self.dialog.destroy()

    def _on_cancel(self):
        """取消并关闭对话框"""
        self.result = None
        self.dialog.destroy()

    def _save_to_config_file(self, config):
        """保存配置到文件"""
        try:
            config_dir = Path("config")
            config_dir.mkdir(exist_ok=True)

            config_file = config_dir / "ai_config.json"

            # 创建副本，确保保存所有配置包括API密钥
            save_config = config.copy()

            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(save_config, f, ensure_ascii=False, indent=2)

            print(f"配置已保存到 {config_file}")

            # 更新全局AI引擎实例的配置
            global _ai_engine_instance
            if _ai_engine_instance:
                _ai_engine_instance.update_config(config)

        except Exception as e:
            print(f"保存配置文件时出错: {e}")
            messagebox.showwarning("警告", f"保存配置文件时出错: {e}", parent=self.dialog)


class OptimizeDialog:
    """内容优化对话框，用于优化小说内容"""

    def __init__(self, parent, ai_engine, content=None):
        """
        初始化优化对话框

        Args:
            parent: 父窗口
            ai_engine: AI引擎实例
            content: 初始内容
        """
        self.parent = parent
        self.ai_engine = ai_engine
        self.initial_content = content or ""
        self.result = None
        self.optimized_result = None

        # 创建对话框（不论是否配置了AI引擎）
        self._create_dialog()

    def _create_dialog(self):
        """创建对话框界面"""
        if HAS_CTK:
            self.dialog = ctk.CTkToplevel(self.parent)
            self._create_ctk_ui()
        else:
            self.dialog = Toplevel(self.parent)
            self._create_tk_ui()

        self.dialog.title("内容优化")
        self.dialog.geometry("900x700")
        self.dialog.transient(self.parent)
        self.dialog.grab_set()

        # 确保对话框居中显示
        self.dialog.update_idletasks()
        screen_width = self.dialog.winfo_screenwidth()
        screen_height = self.dialog.winfo_screenheight()
        x = (screen_width - self.dialog.winfo_width()) // 2
        y = (screen_height - self.dialog.winfo_height()) // 2
        self.dialog.geometry(f"+{x}+{y}")

        # 初始化内容
        if self.initial_content:
            self._set_content(self.initial_content)

        # 检查AI引擎配置状态
        if not self.ai_engine.is_configured():
            # 不阻止界面打开，而是在优化按钮点击时进行处理
            if HAS_CTK:
                warning_label = ctk.CTkLabel(
                    self.dialog,
                    text="警告：AI引擎未正确配置，请先在AI配置中设置API密钥",
                    text_color="red",
                    font=("Microsoft YaHei UI", 12, "bold")
                )
                warning_label.pack(side=tk.TOP, pady=5)
            else:
                warning_label = ttk.Label(
                    self.dialog,
                    text="警告：AI引擎未正确配置，请先在AI配置中设置API密钥",
                    foreground="red",
                    font=("Microsoft YaHei UI", 12, "bold")
                )
                warning_label.pack(side=tk.TOP, pady=5)

        # 等待对话框关闭
        self.dialog.wait_window(self.dialog)

    def _create_ctk_ui(self):
        """创建CustomTkinter UI"""
        dialog = self.dialog

        # 主布局
        main_layout = ctk.CTkFrame(dialog)
        main_layout.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # 顶部标题
        ctk.CTkLabel(
            main_layout,
            text="小说内容优化",
            font=ctk.CTkFont(size=18, weight="bold")
        ).pack(pady=(0, 10))

        # 创建左右分栏
        paned_window = ttk.PanedWindow(main_layout, orient=tk.HORIZONTAL)
        paned_window.pack(fill=tk.BOTH, expand=True, pady=10)

        # === 左侧：原始内容 ===
        left_frame = ctk.CTkFrame(paned_window)

        # 左侧标题
        ctk.CTkLabel(
            left_frame,
            text="原始内容",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(pady=(5, 5), anchor=tk.W)

        # 原始内容文本区域
        self.content_text = ctk.CTkTextbox(left_frame, wrap="word")
        self.content_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # 字数统计标签
        self.original_word_count_var = tk.StringVar(value="字数：0")
        ctk.CTkLabel(
            left_frame,
            textvariable=self.original_word_count_var
        ).pack(pady=5, anchor=tk.E)

        # 添加左侧面板到分栏
        paned_window.add(left_frame, weight=1)

        # === 右侧：优化设置和结果 ===
        right_frame = ctk.CTkFrame(paned_window)

        # 右侧使用选项卡布局
        tabview = ctk.CTkTabview(right_frame)
        tabview.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 创建"优化设置"标签页
        settings_tab = tabview.add("优化设置")
        # 创建"优化结果"标签页
        result_tab = tabview.add("优化结果")

        # === 优化设置标签页 ===
        settings_frame = ctk.CTkFrame(settings_tab)
        settings_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 字数处理设置
        word_count_frame = ctk.CTkFrame(settings_frame)
        word_count_frame.pack(fill=tk.X, pady=(5, 10))

        ctk.CTkLabel(
            word_count_frame,
            text="字数处理:"
        ).pack(side=tk.LEFT, padx=(10, 5), pady=10)

        self.word_count_option_var = tk.StringVar(value="保持原有字数")
        word_count_combo = ctk.CTkComboBox(
            word_count_frame,
            values=["保持原有字数", "缩减字数", "扩展字数"],
            variable=self.word_count_option_var,
            width=120
        )
        word_count_combo.pack(side=tk.LEFT, padx=5, pady=10)

        self.word_count_ratio_var = tk.IntVar(value=100)
        self.word_count_ratio_slider = ctk.CTkSlider(
            word_count_frame,
            from_=50,
            to=300,
            number_of_steps=25,
            variable=self.word_count_ratio_var
        )
        self.word_count_ratio_slider.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True, pady=10)
        self.word_count_ratio_slider.configure(state="disabled")

        self.word_count_ratio_label = ctk.CTkLabel(
            word_count_frame,
            text="100%",
            width=40
        )
        self.word_count_ratio_label.pack(side=tk.RIGHT, padx=(5, 10), pady=10)

        # 相似度设置
        similarity_frame = ctk.CTkFrame(settings_frame)
        similarity_frame.pack(fill=tk.X, pady=(0, 10))

        ctk.CTkLabel(
            similarity_frame,
            text="保留相似度:"
        ).pack(side=tk.LEFT, padx=(10, 5), pady=10)

        self.similarity_var = tk.IntVar(value=70)
        similarity_slider = ctk.CTkSlider(
            similarity_frame,
            from_=10,
            to=90,
            number_of_steps=8,
            variable=self.similarity_var
        )
        similarity_slider.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True, pady=10)

        self.similarity_label = ctk.CTkLabel(
            similarity_frame,
            text="70%",
            width=40
        )
        self.similarity_label.pack(side=tk.RIGHT, padx=(5, 10), pady=10)

        # 优化选项
        options_frame = ctk.CTkFrame(settings_frame)
        options_frame.pack(fill=tk.X, pady=(0, 10))

        options_title = ctk.CTkLabel(
            options_frame,
            text="优化选项:",
            anchor="w"
        )
        options_title.pack(fill=tk.X, padx=10, pady=(10, 5))

        # 优化选项复选框
        self.optimize_skills_var = tk.BooleanVar(value=False)
        self.optimize_scenes_var = tk.BooleanVar(value=False)
        self.optimize_characters_var = tk.BooleanVar(value=False)
        self.optimize_plot_var = tk.BooleanVar(value=False)

        ctk.CTkCheckBox(
            options_frame,
            text="优化功法描写",
            variable=self.optimize_skills_var
        ).pack(anchor=tk.W, padx=20, pady=2)

        ctk.CTkCheckBox(
            options_frame,
            text="优化场景描写",
            variable=self.optimize_scenes_var
        ).pack(anchor=tk.W, padx=20, pady=2)

        ctk.CTkCheckBox(
            options_frame,
            text="优化人物刻画",
            variable=self.optimize_characters_var
        ).pack(anchor=tk.W, padx=20, pady=2)

        ctk.CTkCheckBox(
            options_frame,
            text="优化情节结构",
            variable=self.optimize_plot_var
        ).pack(anchor=tk.W, padx=20, pady=2)

        # 自定义要求
        custom_frame = ctk.CTkFrame(settings_frame)
        custom_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        ctk.CTkLabel(
            custom_frame,
            text="自定义优化要求:",
            anchor="w"
        ).pack(fill=tk.X, padx=10, pady=(10, 5))

        self.custom_requirements_text = ctk.CTkTextbox(custom_frame, height=100)
        self.custom_requirements_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        # 优化按钮
        optimize_button = ctk.CTkButton(
            settings_frame,
            text="开始优化",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=40,
            command=self._on_optimize_clicked
        )
        optimize_button.pack(pady=(0, 10))

        # === 优化结果标签页 ===
        result_frame = ctk.CTkFrame(result_tab)
        result_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 优化结果文本区域
        self.result_text = ctk.CTkTextbox(result_frame, wrap="word")
        self.result_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 5))

        # 结果字数统计标签
        self.result_word_count_var = tk.StringVar(value="字数：0")
        ctk.CTkLabel(
            result_frame,
            textvariable=self.result_word_count_var
        ).pack(pady=5, anchor=tk.E)

        # 底部按钮区域
        button_frame = ctk.CTkFrame(result_frame)
        button_frame.pack(fill=tk.X, padx=10, pady=(5, 10))

        # 复制结果按钮
        ctk.CTkButton(
            button_frame,
            text="复制结果",
            command=self._on_copy_result
        ).pack(side=tk.LEFT, padx=(0, 10))

        # 应用结果按钮
        ctk.CTkButton(
            button_frame,
            text="应用结果",
            command=self._on_apply_result
        ).pack(side=tk.LEFT)

        # 添加右侧面板到分栏
        paned_window.add(right_frame, weight=1)

        # === 底部按钮区域 ===
        bottom_frame = ctk.CTkFrame(main_layout)
        bottom_frame.pack(fill=tk.X, pady=(10, 0))

        # 关闭按钮
        ctk.CTkButton(
            bottom_frame,
            text="关闭",
            command=self._on_close
        ).pack(side=tk.RIGHT)

        # 绑定事件
        self.word_count_option_var.trace_add("write", self._on_word_count_option_changed)
        self.word_count_ratio_var.trace_add("write", self._on_word_count_ratio_changed)
        self.similarity_var.trace_add("write", self._on_similarity_changed)

        # 添加文本更改时更新字数统计的事件
        self.content_text.bind("<KeyRelease>", self._update_word_count)

    def _create_tk_ui(self):
        """创建Tkinter UI"""
        dialog = self.dialog

        # 主框架
        main_frame = ttk.Frame(dialog, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 顶部标题
        ttk.Label(
            main_frame,
            text="小说内容优化",
            font=("TkDefaultFont", 14, "bold")
        ).pack(pady=(0, 10))

        # 创建左右分栏
        paned_window = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        paned_window.pack(fill=tk.BOTH, expand=True, pady=10)

        # === 左侧：原始内容 ===
        left_frame = ttk.Frame(paned_window)

        # 左侧标题
        ttk.Label(
            left_frame,
            text="原始内容",
            font=("TkDefaultFont", 12, "bold")
        ).pack(pady=(5, 5), anchor=tk.W)

        # 原始内容文本区域
        self.content_text = Text(left_frame, wrap="word")
        content_scrollbar = ttk.Scrollbar(left_frame, command=self.content_text.yview)
        self.content_text.configure(yscrollcommand=content_scrollbar.set)

        self.content_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5), pady=5)
        content_scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=5)

        # 字数统计标签
        self.original_word_count_var = tk.StringVar(value="字数：0")
        ttk.Label(
            left_frame,
            textvariable=self.original_word_count_var
        ).pack(pady=5, anchor=tk.E)

        # 添加左侧面板到分栏
        paned_window.add(left_frame, weight=1)

        # === 右侧：优化设置和结果 ===
        right_frame = ttk.Frame(paned_window)

        # 右侧使用选项卡布局
        tab_control = ttk.Notebook(right_frame)
        tab_control.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 创建"优化设置"标签页
        settings_tab = ttk.Frame(tab_control)
        tab_control.add(settings_tab, text="优化设置")

        # 创建"优化结果"标签页
        result_tab = ttk.Frame(tab_control)
        tab_control.add(result_tab, text="优化结果")

        # === 优化设置标签页 ===
        settings_frame = ttk.Frame(settings_tab, padding=10)
        settings_frame.pack(fill=tk.BOTH, expand=True)

        # 字数处理设置
        word_count_frame = ttk.Frame(settings_frame)
        word_count_frame.pack(fill=tk.X, pady=(5, 10))

        ttk.Label(
            word_count_frame,
            text="字数处理:"
        ).pack(side=tk.LEFT, padx=(0, 5), pady=10)

        self.word_count_option_var = tk.StringVar(value="保持原有字数")
        word_count_combo = ttk.Combobox(
            word_count_frame,
            textvariable=self.word_count_option_var,
            values=["保持原有字数", "缩减字数", "扩展字数"],
            width=15,
            state="readonly"
        )
        word_count_combo.pack(side=tk.LEFT, padx=5, pady=10)

        self.word_count_ratio_var = tk.IntVar(value=100)
        self.word_count_ratio_slider = ttk.Scale(
            word_count_frame,
            from_=50,
            to=300,
            variable=self.word_count_ratio_var,
            orient=tk.HORIZONTAL
        )
        self.word_count_ratio_slider.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True, pady=10)
        self.word_count_ratio_slider.state(["disabled"])

        self.word_count_ratio_label = ttk.Label(
            word_count_frame,
            text="100%",
            width=5
        )
        self.word_count_ratio_label.pack(side=tk.RIGHT, padx=(5, 0), pady=10)

        # 相似度设置
        similarity_frame = ttk.Frame(settings_frame)
        similarity_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(
            similarity_frame,
            text="保留相似度:"
        ).pack(side=tk.LEFT, padx=(0, 5), pady=10)

        self.similarity_var = tk.IntVar(value=70)
        similarity_slider = ttk.Scale(
            similarity_frame,
            from_=10,
            to=90,
            variable=self.similarity_var,
            orient=tk.HORIZONTAL
        )
        similarity_slider.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True, pady=10)

        self.similarity_label = ttk.Label(
            similarity_frame,
            text="70%",
            width=5
        )
        self.similarity_label.pack(side=tk.RIGHT, padx=(5, 0), pady=10)

        # 优化选项
        options_frame = ttk.LabelFrame(settings_frame, text="优化选项")
        options_frame.pack(fill=tk.X, pady=(0, 10))

        # 优化选项复选框
        self.optimize_skills_var = tk.BooleanVar(value=False)
        self.optimize_scenes_var = tk.BooleanVar(value=False)
        self.optimize_characters_var = tk.BooleanVar(value=False)
        self.optimize_plot_var = tk.BooleanVar(value=False)

        ttk.Checkbutton(
            options_frame,
            text="优化功法描写",
            variable=self.optimize_skills_var
        ).pack(anchor=tk.W, padx=10, pady=2)

        ttk.Checkbutton(
            options_frame,
            text="优化场景描写",
            variable=self.optimize_scenes_var
        ).pack(anchor=tk.W, padx=10, pady=2)

        ttk.Checkbutton(
            options_frame,
            text="优化人物刻画",
            variable=self.optimize_characters_var
        ).pack(anchor=tk.W, padx=10, pady=2)

        ttk.Checkbutton(
            options_frame,
            text="优化情节结构",
            variable=self.optimize_plot_var
        ).pack(anchor=tk.W, padx=10, pady=2)

        # 自定义要求
        custom_frame = ttk.LabelFrame(settings_frame, text="自定义优化要求")
        custom_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        self.custom_requirements_text = Text(custom_frame, height=5)
        custom_scrollbar = ttk.Scrollbar(custom_frame, command=self.custom_requirements_text.yview)
        self.custom_requirements_text.configure(yscrollcommand=custom_scrollbar.set)

        self.custom_requirements_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0), pady=5)
        custom_scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=5)

        # 优化按钮
        optimize_button = ttk.Button(
            settings_frame,
            text="开始优化",
            command=self._on_optimize_clicked
        )
        optimize_button.pack(pady=(0, 10))

        # === 优化结果标签页 ===
        result_frame = ttk.Frame(result_tab, padding=10)
        result_frame.pack(fill=tk.BOTH, expand=True)

        # 优化结果文本区域
        self.result_text = Text(result_frame, wrap="word")
        result_scrollbar = ttk.Scrollbar(result_frame, command=self.result_text.yview)
        self.result_text.configure(yscrollcommand=result_scrollbar.set)

        self.result_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5), pady=5)
        result_scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=5)

        # 结果字数统计标签
        self.result_word_count_var = tk.StringVar(value="字数：0")
        ttk.Label(
            result_frame,
            textvariable=self.result_word_count_var
        ).pack(pady=5, anchor=tk.E)

        # 底部按钮区域
        button_frame = ttk.Frame(result_frame)
        button_frame.pack(fill=tk.X, pady=(5, 10))

        # 复制结果按钮
        ttk.Button(
            button_frame,
            text="复制结果",
            command=self._on_copy_result
        ).pack(side=tk.LEFT, padx=(0, 10))

        # 应用结果按钮
        ttk.Button(
            button_frame,
            text="应用结果",
            command=self._on_apply_result
        ).pack(side=tk.LEFT)

        # 添加右侧面板到分栏
        paned_window.add(right_frame, weight=1)

        # === 底部按钮区域 ===
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.pack(fill=tk.X, pady=(10, 0))

        # 关闭按钮
        ttk.Button(
            bottom_frame,
            text="关闭",
            command=self._on_close
        ).pack(side=tk.RIGHT)

        # 绑定事件
        self.word_count_option_var.trace_add("write", self._on_word_count_option_changed)
        self.word_count_ratio_var.trace_add("write", self._on_word_count_ratio_changed)
        self.similarity_var.trace_add("write", self._on_similarity_changed)

        # 添加文本更改时更新字数统计的事件
        self.content_text.bind("<KeyRelease>", self._update_word_count)

    def _on_word_count_option_changed(self, *args):
        """当字数处理选项改变时的处理"""
        option = self.word_count_option_var.get()

        if option == "保持原有字数":
            # 禁用比例滑块
            if HAS_CTK:
                self.word_count_ratio_slider.configure(state="disabled")
            else:
                self.word_count_ratio_slider.state(["disabled"])

            # 重置比例
            self.word_count_ratio_var.set(100)
        else:
            # 启用比例滑块
            if HAS_CTK:
                self.word_count_ratio_slider.configure(state="normal")
            else:
                self.word_count_ratio_slider.state(["!disabled"])

            # 设置默认比例
            if option == "缩减字数":
                self.word_count_ratio_var.set(70)
            else:  # 扩展字数
                self.word_count_ratio_var.set(150)

    def _on_word_count_ratio_changed(self, *args):
        """当字数比例改变时的处理"""
        self.word_count_ratio_label.configure(text=f"{self.word_count_ratio_var.get()}%")

    def _on_similarity_changed(self, *args):
        """当相似度改变时的处理"""
        self.similarity_label.configure(text=f"{self.similarity_var.get()}%")

    def _get_content(self):
        """获取内容文本框中的内容"""
        if HAS_CTK:
            return self.content_text.get("0.0", "end").strip()
        else:
            return self.content_text.get("1.0", "end-1c").strip()

    def _set_content(self, content):
        """设置内容文本框的内容"""
        # 清空现有内容
        if HAS_CTK:
            self.content_text.delete("0.0", "end")
            self.content_text.insert("0.0", content)
        else:
            self.content_text.delete("1.0", "end")
            self.content_text.insert("1.0", content)

        # 更新字数统计
        self._update_word_count()

    def _get_result(self):
        """获取结果文本框中的内容"""
        if HAS_CTK:
            return self.result_text.get("0.0", "end").strip()
        else:
            return self.result_text.get("1.0", "end-1c").strip()

    def _set_result(self, content):
        """设置结果文本框的内容"""
        # 清空现有内容
        if HAS_CTK:
            self.result_text.delete("0.0", "end")
            self.result_text.insert("0.0", content)
        else:
            self.result_text.delete("1.0", "end")
            self.result_text.insert("1.0", content)

        # 更新结果字数统计
        self._update_result_word_count()

    def _get_custom_requirements(self):
        """获取自定义要求文本框中的内容"""
        if HAS_CTK:
            return self.custom_requirements_text.get("0.0", "end").strip()
        else:
            return self.custom_requirements_text.get("1.0", "end-1c").strip()

    def _update_word_count(self, event=None):
        """更新原始内容的字数统计"""
        content = self._get_content()

        # 计算不同类型的字数
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', content))
        english_words = len(re.findall(r'\b[a-zA-Z]+\b', content))
        total_chars = len(content)

        self.original_word_count_var.set(
            f"字数：{chinese_chars + english_words} (中文字符：{chinese_chars}，英文单词：{english_words})")

    def _update_result_word_count(self):
        """更新优化结果的字数统计"""
        content = self._get_result()

        # 计算不同类型的字数
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', content))
        english_words = len(re.findall(r'\b[a-zA-Z]+\b', content))
        total_chars = len(content)

        self.result_word_count_var.set(
            f"字数：{chinese_chars + english_words} (中文字符：{chinese_chars}，英文单词：{english_words})")

    def _get_optimize_config(self):
        """获取优化配置"""
        return {
            "word_count_option": self.word_count_option_var.get(),
            "word_count_ratio": self.word_count_ratio_var.get(),
            "similarity": self.similarity_var.get(),
            "optimize_skills": self.optimize_skills_var.get(),
            "optimize_scenes": self.optimize_scenes_var.get(),
            "optimize_characters": self.optimize_characters_var.get(),
            "optimize_plot": self.optimize_plot_var.get(),
            "custom_requirements": self._get_custom_requirements()
        }

    def _on_optimize_clicked(self):
        """当点击开始优化按钮时的处理"""
        content = self._get_content()

        if not content:
            messagebox.showwarning("警告", "请先输入需要优化的内容", parent=self.dialog)
            return

        # 检查AI引擎配置
        if not self.ai_engine.is_configured():
            # 提示配置AI引擎
            if messagebox.askyesno("AI配置", "AI引擎尚未配置，是否现在配置？", parent=self.dialog):
                # 关闭当前对话框
                self.dialog.withdraw()

                # 打开配置对话框
                config_dialog = ConfigDialog(self.parent, self.ai_engine)

                # 如果配置完成，重新显示优化对话框
                self.dialog.deiconify()

                # 如果配置对话框没有正确保存配置，则退出优化
                if not self.ai_engine.is_configured():
                    return
            else:
                # 用户取消配置，不继续优化
                return

        # 获取优化配置
        optimize_config = self._get_optimize_config()

        # 显示处理中提示
        self.dialog.config(cursor="wait")
        if hasattr(self.dialog, "update"):
            self.dialog.update()

        try:
            # 调用AI引擎进行优化
            optimized_content = self.ai_engine.optimize_content(content, optimize_config)

            # 保存优化结果
            self.optimized_result = optimized_content

            # 显示优化结果
            self._set_result(optimized_content)

            # 更新结果标签页
            if HAS_CTK:
                # 选择结果标签页
                tabview = [child for child in self.dialog.winfo_children()[0].winfo_children()
                           if isinstance(child, ttk.PanedWindow)][0]
                right_frame = tabview.winfo_children()[1]
                tab_control = [child for child in right_frame.winfo_children()
                               if isinstance(child, ctk.CTkTabview)][0]
                tab_control.set("优化结果")
            else:
                # 获取ttk.Notebook实例
                for child in self.dialog.winfo_children():
                    if isinstance(child, ttk.Frame):
                        for grandchild in child.winfo_children():
                            if isinstance(grandchild, ttk.PanedWindow):
                                right_frame = grandchild.winfo_children()[1]
                                for right_child in right_frame.winfo_children():
                                    if isinstance(right_child, ttk.Notebook):
                                        tab_control = right_child
                                        tab_control.select(1)  # 索引为1的是结果标签页
                                        break

            self.dialog.config(cursor="")
            messagebox.showinfo("优化完成", "内容优化已完成！", parent=self.dialog)
        except Exception as e:
            self.dialog.config(cursor="")
            error_msg = str(e)
            if len(error_msg) > 500:
                error_msg = error_msg[:500] + "..."
            messagebox.showerror("优化失败", f"内容优化过程中出错:\n{error_msg}", parent=self.dialog)

    def _on_copy_result(self):
        """当点击复制结果按钮时的处理"""
        result = self._get_result()

        if not result:
            messagebox.showwarning("警告", "没有可复制的优化结果", parent=self.dialog)
            return

        # 复制到剪贴板
        self.dialog.clipboard_clear()
        self.dialog.clipboard_append(result)

        messagebox.showinfo("复制成功", "优化结果已复制到剪贴板", parent=self.dialog)

    def _on_apply_result(self):
        """当点击应用结果按钮时的处理"""
        result = self._get_result()

        if not result:
            messagebox.showwarning("警告", "没有可应用的优化结果", parent=self.dialog)
            return

        # 确认是否应用
        if messagebox.askyesno("确认应用", "确定要用优化结果替换原始内容吗？", parent=self.dialog):
            # 保存结果到返回值
            self.result = result

            # 更新UI
            self._set_content(result)

            messagebox.showinfo("应用成功", "已将优化结果应用到原始内容", parent=self.dialog)

    def _on_close(self):
        """当点击关闭按钮时的处理"""
        self.dialog.destroy()


# --- 辅助函数 ---

def load_ai_config():
    """
    加载AI配置

    Returns:
        配置字典
    """
    config_dir = Path("config")
    config_file = _config_path

    # 确保配置目录存在
    config_dir.mkdir(exist_ok=True)

    # 默认配置
    default_config = {
        "provider": "OpenAI",
        "model_name": "gpt-3.5-turbo",
        "api_key": "",
        "api_url": "https://api.openai.com/v1/chat/completions",
        "max_tokens": 4000,
        "temperature": 0.7,
        "use_proxy": False,
        "proxy_url": ""
    }

    # 如果配置文件存在，加载它
    if config_file.exists():
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                loaded_config = json.load(f)
                # 更新默认配置，保留API密钥等敏感信息
                for key, value in loaded_config.items():
                    if value or key not in default_config:  # 只更新非空值或新增字段
                        default_config[key] = value
                print(f"已加载AI配置: {config_file}")
        except Exception as e:
            print(f"加载AI配置时出错: {e}")
    else:
        # 创建默认配置文件
        try:
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(default_config, indent=4, ensure_ascii=False, fp=f)
                print(f"已创建默认AI配置: {config_file}")
        except Exception as e:
            print(f"创建默认AI配置时出错: {e}")

    return default_config


def get_ai_engine():
    """
    获取AI引擎实例，如果不存在则创建一个

    Returns:
        AIEngine实例
    """
    global _ai_engine_instance

    if _ai_engine_instance is None:
        # 加载配置
        config = load_ai_config()
        # 创建AI引擎实例
        _ai_engine_instance = AIEngine(config)

    return _ai_engine_instance
