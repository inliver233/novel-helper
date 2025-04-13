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
_profiles_dir = Path("config/profiles")
_current_profile_path = Path("config/current_profile.txt")


# === 配置档案管理函数 ===

def get_profile_dir() -> Path:
    """获取配置档案目录路径，如果不存在则创建"""
    profiles_dir = _profiles_dir
    profiles_dir.mkdir(parents=True, exist_ok=True)
    return profiles_dir


def list_profiles() -> List[str]:
    """
    列出所有可用的配置档案

    Returns:
        配置名称列表(不含.json后缀)
    """
    profiles_dir = get_profile_dir()
    profiles = [f.stem for f in profiles_dir.glob("*.json")]

    # 确保总是有一个"default"配置
    if "default" not in profiles and len(profiles) == 0:
        # 创建默认配置
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
        save_profile("default", default_config)
        profiles = ["default"]

    return sorted(profiles)


def get_current_profile_name() -> str:
    """
    获取当前使用的配置名称

    Returns:
        当前配置名称，如果未设置则返回'default'
    """
    if _current_profile_path.exists():
        try:
            with open(_current_profile_path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except:
            pass

    # 如果未设置或读取失败，返回default
    return "default"


def set_current_profile(profile_name: str):
    """
    设置当前使用的配置名称

    Args:
        profile_name: 配置名称
    """
    try:
        with open(_current_profile_path, "w", encoding="utf-8") as f:
            f.write(profile_name)
    except Exception as e:
        print(f"设置当前配置文件时出错: {e}")


def load_profile(profile_name: str) -> Dict:
    """
    加载特定配置档案

    Args:
        profile_name: 配置名称

    Returns:
        配置字典
    """
    profiles_dir = get_profile_dir()
    profile_path = profiles_dir / f"{profile_name}.json"

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
    if profile_path.exists():
        try:
            with open(profile_path, "r", encoding="utf-8") as f:
                loaded_config = json.load(f)
                # 更新默认配置，保留必要的字段
                for key, value in loaded_config.items():
                    if value is not None or key not in default_config:
                        default_config[key] = value
                print(f"已加载配置档案: {profile_name}")
        except Exception as e:
            print(f"加载配置档案 {profile_name} 时出错: {e}")
    else:
        # 如果配置不存在，创建一个空的默认配置
        save_profile(profile_name, default_config)
        print(f"已创建新的配置档案: {profile_name}")

    return default_config


def save_profile(profile_name: str, config: Dict):
    """
    保存配置到特定档案

    Args:
        profile_name: 配置名称
        config: 配置字典
    """
    profiles_dir = get_profile_dir()
    profile_path = profiles_dir / f"{profile_name}.json"

    try:
        with open(profile_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        print(f"配置已保存到档案: {profile_name}")
    except Exception as e:
        print(f"保存配置档案 {profile_name} 时出错: {e}")
        raise


def delete_profile(profile_name: str) -> bool:
    """
    删除配置档案

    Args:
        profile_name: 配置名称

    Returns:
        是否成功删除
    """
    # 不允许删除default配置
    if profile_name == "default":
        print("不允许删除默认配置档案")
        return False

    profiles_dir = get_profile_dir()
    profile_path = profiles_dir / f"{profile_name}.json"

    if profile_path.exists():
        try:
            profile_path.unlink()
            print(f"已删除配置档案: {profile_name}")

            # 如果删除的是当前配置，切换到default
            current = get_current_profile_name()
            if current == profile_name:
                set_current_profile("default")

            return True
        except Exception as e:
            print(f"删除配置档案 {profile_name} 时出错: {e}")
            return False
    else:
        print(f"配置档案不存在: {profile_name}")
        return False


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
        # 尝试使用全局日志系统
        try:
            import log
            # 如果导入成功，使用全局日志管理器
            log_manager = log.get_log_manager()
            self.logger = log_manager.get_logger()
            # 记录AI引擎初始化日志
            self.logger.info("AI引擎初始化")
            return
        except ImportError:
            # 如果导入失败，使用标准日志设置
            pass
        except Exception as e:
            # 如果出现其他错误，回退到标准日志设置
            print(f"使用全局日志系统时出错: {e}")
            
        # 标准日志设置（当无法使用log.py时）
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

    def __init__(self, parent, ai_engine=None, config=None, callback=None):
        """
        初始化配置对话框

        Args:
            parent: 父窗口
            ai_engine: AI引擎实例，如果提供则会自动更新配置
            config: 初始配置字典
            callback: 配置保存后的回调函数
        """
        self.parent = parent
        self.ai_engine = ai_engine
        self.callback = callback

        # 配置档案相关
        self.profiles = list_profiles()
        self.current_profile_name = get_current_profile_name()
        self.profile_var = tk.StringVar(value=self.current_profile_name)

        # 如果传入AI引擎，则使用其配置，否则加载配置文件
        if ai_engine and hasattr(ai_engine, 'config'):
            self.config = ai_engine.config.copy()
        elif config:
            self.config = config.copy()
        else:
            self.config = load_ai_config(self.current_profile_name)

        self.result = None

        self._create_dialog()

    def _create_dialog(self):
        """创建对话框界面"""
        # 确保应用正确的主题设置
        if HAS_CTK:
            try:
                # 设置外观模式和颜色主题，与主应用保持一致
                ctk.set_appearance_mode("System")  # 使用系统模式
                ctk.set_default_color_theme("blue")  # 使用蓝色主题
            except Exception as e:
                print(f"设置CTK主题时出错: {e}")
                
        if HAS_CTK:
            self.dialog = ctk.CTkToplevel(self.parent)
            self._create_ctk_ui()
        else:
            self.dialog = Toplevel(self.parent)
            self._create_tk_ui()

        self.dialog.title("AI模型配置")
        self.dialog.geometry("500x550")
        self.dialog.transient(self.parent)
        # 移除 grab_set 使对话框为非模态
        # self.dialog.grab_set()
        
        # 设置关闭窗口协议
        self.dialog.protocol("WM_DELETE_WINDOW", self._on_cancel)

        # 确保对话框居中显示
        self.dialog.update_idletasks()
        screen_width = self.dialog.winfo_screenwidth()
        screen_height = self.dialog.winfo_screenheight()
        x = (screen_width - self.dialog.winfo_width()) // 2
        y = (screen_height - self.dialog.winfo_height()) // 2
        self.dialog.geometry(f"+{x}+{y}")

        # 加载现有配置
        self._load_config()

        # 不再等待对话框关闭，允许与主窗口交互
        # self.dialog.wait_window(self.dialog)

    def _create_ctk_ui(self):
        """创建CustomTkinter UI"""
        dialog = self.dialog

        # 主框架
        main_frame = ctk.CTkFrame(dialog)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # 配置档案管理区域
        profile_frame = ctk.CTkFrame(main_frame)
        profile_frame.pack(fill=tk.X, pady=(0, 15))

        ctk.CTkLabel(
            profile_frame,
            text="配置档案:",
            font=ctk.CTkFont(size=14)
        ).pack(side=tk.LEFT, padx=(0, 5), pady=10)

        # 配置档案下拉选择框
        profile_combobox = ctk.CTkComboBox(
            profile_frame,
            values=self.profiles,
            variable=self.profile_var,
            width=180,
            command=self._on_profile_change
        )
        profile_combobox.pack(side=tk.LEFT, padx=5, pady=10)

        # 配置档案管理按钮
        btn_new = ctk.CTkButton(
            profile_frame,
            text="另存为...",
            width=80,
            command=self._save_as_new_profile
        )
        btn_new.pack(side=tk.LEFT, padx=5, pady=10)

        btn_delete = ctk.CTkButton(
            profile_frame,
            text="删除",
            width=60,
            command=self._delete_current_profile,
            fg_color="#E74C3C"  # 红色按钮
        )
        btn_delete.pack(side=tk.LEFT, padx=5, pady=10)

        # 标题
        ctk.CTkLabel(
            main_frame,
            text="AI模型配置",
            font=ctk.CTkFont(size=18, weight="bold")
        ).pack(pady=(0, 20))

        # 底部按钮 (移到选项卡之前创建和pack)
        button_frame = ctk.CTkFrame(main_frame)
        button_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(20, 0))

        ctk.CTkButton(
            button_frame,
            text="测试连接",
            command=self._test_connection,
            width=100
        ).pack(side=tk.LEFT, padx=(0, 10))

        ctk.CTkButton(
            button_frame,
            text="取消",
            command=self._on_cancel,
            width=100,
            fg_color="gray"
        ).pack(side=tk.RIGHT, padx=(10, 0))

        ctk.CTkButton(
            button_frame,
            text="保存",
            command=self._on_save,
            width=100
        ).pack(side=tk.RIGHT)

        # 创建选项卡 (在按钮框架之后pack，使其填充剩余空间)
        tab_view = ctk.CTkTabview(main_frame)
        tab_view.pack(fill=tk.BOTH, expand=True)

        # 创建标签页
        general_tab = tab_view.add("通用配置")
        advanced_tab = tab_view.add("高级设置")

        # === 通用配置标签页 ===
        # 使用更合适的布局，从grid改为更简洁的垂直布局
        general_frame = ctk.CTkFrame(general_tab)
        general_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 模型提供商
        provider_row = ctk.CTkFrame(general_frame)
        provider_row.pack(fill=tk.X, pady=(5, 10))
        
        ctk.CTkLabel(
            provider_row, 
            text="模型提供商:",
            width=80
        ).pack(side=tk.LEFT, padx=(5, 10))
        
        self.provider_var = tk.StringVar()
        provider_combo = ctk.CTkComboBox(
            provider_row,
            values=["OpenAI", "智谱AI", "讯飞星火", "百度文心", "硅基流动", "自定义"],
            variable=self.provider_var,
            width=200,
            state="readonly"
        )
        provider_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # API密钥
        api_key_label_frame = ctk.CTkFrame(general_frame)
        api_key_label_frame.pack(fill=tk.X, pady=(5, 2))
        
        ctk.CTkLabel(
            api_key_label_frame, 
            text="API密钥:"
        ).pack(side=tk.LEFT, padx=5)
        
        key_frame = ctk.CTkFrame(general_frame)
        key_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.api_key_var = tk.StringVar()
        self.api_key_entry = ctk.CTkEntry(
            key_frame,
            textvariable=self.api_key_var,
            show="*"
        )
        self.api_key_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 5))
        
        self.show_key_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            key_frame,
            text="显示",
            variable=self.show_key_var,
            command=self._toggle_key_visibility,
            width=60
        ).pack(side=tk.RIGHT, padx=(5, 5))

        # API URL
        api_url_label_frame = ctk.CTkFrame(general_frame)
        api_url_label_frame.pack(fill=tk.X, pady=(5, 2))
        
        ctk.CTkLabel(
            api_url_label_frame, 
            text="API URL:"
        ).pack(side=tk.LEFT, padx=5)
        
        api_url_frame = ctk.CTkFrame(general_frame)
        api_url_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.api_url_var = tk.StringVar()
        ctk.CTkEntry(
            api_url_frame,
            textvariable=self.api_url_var,
            placeholder_text="https://api.openai.com/v1/chat/completions"
        ).pack(fill=tk.X, padx=5)

        # 模型名称
        model_label_frame = ctk.CTkFrame(general_frame)
        model_label_frame.pack(fill=tk.X, pady=(5, 2))
        
        ctk.CTkLabel(
            model_label_frame, 
            text="模型名称:"
        ).pack(side=tk.LEFT, padx=5)
        
        model_frame = ctk.CTkFrame(general_frame)
        model_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.model_name_var = tk.StringVar()
        ctk.CTkEntry(
            model_frame,
            textvariable=self.model_name_var,
            placeholder_text="gpt-3.5-turbo"
        ).pack(fill=tk.X, padx=5)

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

    def _create_tk_ui(self):
        """创建标准Tkinter UI"""
        dialog = self.dialog
        dialog.configure(background=self._get_bg_color())

        # 主框架
        main_frame = ttk.Frame(dialog)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # 配置档案管理区域
        profile_frame = ttk.Frame(main_frame)
        profile_frame.pack(fill=tk.X, pady=(0, 15))

        ttk.Label(
            profile_frame,
            text="配置档案:",
            font=("Microsoft YaHei UI", 11)
        ).pack(side=tk.LEFT, padx=(0, 5), pady=10)

        # 配置档案下拉选择框
        profile_combobox = ttk.Combobox(
            profile_frame,
            values=self.profiles,
            textvariable=self.profile_var,
            width=18,
            state="readonly"
        )
        profile_combobox.pack(side=tk.LEFT, padx=5, pady=10)
        profile_combobox.bind("<<ComboboxSelected>>", lambda event: self._on_profile_change(profile_combobox.get()))

        # 配置档案管理按钮
        ttk.Button(
            profile_frame,
            text="另存为...",
            width=8,
            command=self._save_as_new_profile
        ).pack(side=tk.LEFT, padx=5, pady=10)

        ttk.Button(
            profile_frame,
            text="删除",
            width=6,
            command=self._delete_current_profile,
            style="Danger.TButton"  # 假设有一个危险按钮样式
        ).pack(side=tk.LEFT, padx=5, pady=10)

        # 标题
        title_label = ttk.Label(
            main_frame,
            text="AI模型配置",
            font=("Microsoft YaHei UI", 16, "bold")
        )
        title_label.pack(pady=(0, 20))

        # 底部按钮 (移到选项卡之前创建和pack)
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(20, 0))

        ttk.Button(
            button_frame,
            text="测试连接",
            command=self._test_connection
        ).pack(side=tk.LEFT, padx=(0, 10))

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

        # 创建选项卡 (在按钮框架之后pack，使其填充剩余空间)
        tab_view = ttk.Notebook(main_frame)
        tab_view.pack(fill=tk.BOTH, expand=True)

        # 创建标签页
        general_tab = ttk.Frame(tab_view)
        advanced_tab = ttk.Frame(tab_view)

        tab_view.add(general_tab, text="通用配置")
        tab_view.add(advanced_tab, text="高级设置")

        # === 通用配置标签页 ===
        # 配置general_tab的列权重
        general_tab.grid_columnconfigure(1, weight=1)

        # 模型提供商 (Row 0)
        ttk.Label(general_tab, text="模型提供商:").grid(row=0, column=0, sticky=tk.W, pady=(10, 5), padx=5)

        self.provider_var = tk.StringVar()
        provider_combo = ttk.Combobox(
            general_tab,
            textvariable=self.provider_var,
            values=["OpenAI", "智谱AI", "讯飞星火", "百度文心", "硅基流动", "自定义"],
            state="readonly"
        )
        provider_combo.grid(row=0, column=1, sticky="ew", pady=(10, 15), padx=5)

        # API密钥 (Row 1, 2)
        ttk.Label(general_tab, text="API密钥:").grid(row=1, column=0, sticky=tk.W, pady=(0, 5), padx=5)

        key_frame = ttk.Frame(general_tab)
        key_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 15), padx=5)
        key_frame.grid_columnconfigure(0, weight=1) # 让输入框填充

        self.api_key_var = tk.StringVar()
        self.api_key_entry = ttk.Entry(
            key_frame,
            textvariable=self.api_key_var,
            show="*"
        )
        self.api_key_entry.grid(row=0, column=0, sticky="ew")

        self.show_key_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            key_frame,
            text="显示",
            variable=self.show_key_var,
            command=self._toggle_key_visibility
        ).grid(row=0, column=1, padx=(10, 0))

        # API URL (Row 3, 4)
        ttk.Label(general_tab, text="API URL:").grid(row=3, column=0, sticky=tk.W, pady=(0, 5), padx=5)

        self.api_url_var = tk.StringVar()
        ttk.Entry(
            general_tab,
            textvariable=self.api_url_var
        ).grid(row=4, column=1, sticky="ew", pady=(0, 15), padx=5)

        # 模型名称 (Row 5, 6)
        ttk.Label(general_tab, text="模型名称:").grid(row=5, column=0, sticky=tk.W, pady=(0, 5), padx=5)

        self.model_name_var = tk.StringVar()
        ttk.Entry(
            general_tab,
            textvariable=self.model_name_var
        ).grid(row=6, column=1, sticky="ew", pady=(0, 15), padx=5)

        # === 高级设置标签页 ===
        advanced_frame = ttk.Frame(advanced_tab)
        advanced_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 最大Token数
        ttk.Label(advanced_frame, text="最大Token数:").pack(anchor=tk.W, pady=(10, 5))

        token_frame = ttk.Frame(advanced_frame)
        token_frame.pack(fill=tk.X, pady=(0, 15))

        self.max_tokens_var = tk.IntVar(value=4000)
        ttk.Scale(
            token_frame,
            from_=500,
            to=16000,
            variable=self.max_tokens_var,
            orient=tk.HORIZONTAL
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, pady=10)

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

    def _save_to_config_file(self, config):
        """
        保存配置到文件

        Args:
            config: 配置字典
        """
        try:
            # 获取当前选择的配置档案名称
            profile_name = self.profile_var.get()

            # 保存到指定配置档案
            save_profile(profile_name, config)

            # 设置为当前活动配置
            set_current_profile(profile_name)

            # 同时保存一份到旧的配置文件路径，保持兼容性
            config_dir = Path("config")
            config_dir.mkdir(exist_ok=True)
            config_file = _config_path

            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)

            print(f"配置已保存到 {profile_name} 和旧版配置文件")

            # 更新全局AI引擎实例的配置
            global _ai_engine_instance
            if _ai_engine_instance:
                _ai_engine_instance.update_config(config)

        except Exception as e:
            print(f"保存配置文件时出错: {e}")
            messagebox.showwarning("警告", f"保存配置文件时出错: {e}", parent=self.dialog)

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

        # 获取当前选择的配置档案名称
        profile_name = self.profile_var.get()

        # 保存到当前选择的配置档案
        self._save_to_config_file(config)

        # 调用回调函数
        if self.callback:
            self.callback(config)

        # 关闭对话框
        self.dialog.destroy()

    def _on_cancel(self):
        """取消并关闭对话框"""
        self.result = None
        self.dialog.destroy()

    def _on_profile_change(self, profile_name):
        """
        当配置档案改变时的处理

        Args:
            profile_name: 选择的配置档案名称
        """
        if profile_name == self.current_profile_name:
            return

        # 询问是否保存当前修改
        if messagebox.askyesno("保存修改",
                               f"切换到配置档案 {profile_name} 前，是否保存当前对 {self.current_profile_name} 的修改？",
                               parent=self.dialog):
            current_config = self._get_config()
            save_profile(self.current_profile_name, current_config)

        # 加载选择的配置档案
        try:
            new_config = load_profile(profile_name)

            # 更新当前选择的配置档案名称
            self.current_profile_name = profile_name

            # 更新UI显示
            self.config = new_config
            self._load_config()

            print(f"切换到配置档案: {profile_name}")
        except Exception as e:
            messagebox.showerror("错误", f"加载配置档案失败: {e}", parent=self.dialog)
            # 重置下拉框为当前配置档案
            self.profile_var.set(self.current_profile_name)

    def _save_as_new_profile(self):
        """保存为新的配置档案"""
        # 询问新配置档案名称
        new_name = simpledialog.askstring(
            "保存为新配置档案",
            "请输入新配置档案名称:",
            parent=self.dialog
        )

        if not new_name:
            return

        # 检查名称是否有效
        if not re.match(r'^[a-zA-Z0-9_\-\u4e00-\u9fa5]+$', new_name):
            messagebox.showerror("错误", "配置名称只能包含字母、数字、下划线、中文和连字符", parent=self.dialog)
            return

        # 检查是否已存在同名配置
        if new_name in self.profiles:
            if not messagebox.askyesno("确认覆盖", f"配置档案 {new_name} 已存在，是否覆盖？", parent=self.dialog):
                return

        # 获取当前配置
        current_config = self._get_config()

        try:
            # 保存为新配置档案
            save_profile(new_name, current_config)

            # 刷新配置档案列表
            self.profiles = list_profiles()

            # 更新下拉框选项
            if hasattr(self, 'dialog') and self.dialog.winfo_exists():
                profile_combobox = None

                # 查找配置档案下拉框
                for widget in self.dialog.winfo_children():
                    if isinstance(widget, ctk.CTkFrame):
                        for w in widget.winfo_children():
                            if isinstance(w, ctk.CTkFrame):
                                for cb in w.winfo_children():
                                    if isinstance(cb, ctk.CTkComboBox):
                                        profile_combobox = cb
                                        break

                # 更新下拉框选项
                if profile_combobox:
                    profile_combobox.configure(values=self.profiles)

            # 设置当前选择的配置档案
            self.profile_var.set(new_name)
            self.current_profile_name = new_name

            # 设置为当前活动配置
            set_current_profile(new_name)

            messagebox.showinfo("成功", f"已将当前配置保存为 {new_name}", parent=self.dialog)
        except Exception as e:
            messagebox.showerror("错误", f"保存配置档案失败: {e}", parent=self.dialog)

    def _delete_current_profile(self):
        """删除当前配置档案"""
        # 获取当前选择的配置档案
        profile_name = self.profile_var.get()

        # 不允许删除默认配置
        if profile_name == "default":
            messagebox.showinfo("提示", "默认配置不能被删除", parent=self.dialog)
            return

        # 确认删除
        if not messagebox.askyesno("确认删除", f"确定要删除配置档案 {profile_name} 吗？此操作不可恢复。",
                                   parent=self.dialog):
            return

        try:
            # 删除配置档案
            if delete_profile(profile_name):
                # 刷新配置档案列表
                self.profiles = list_profiles()

                # 切换到默认配置
                self.profile_var.set("default")
                self.current_profile_name = "default"

                # 加载默认配置
                new_config = load_profile("default")
                self.config = new_config
                self._load_config()

                # 更新下拉框选项
                if hasattr(self, 'dialog') and self.dialog.winfo_exists():
                    profile_combobox = None

                    # 查找配置档案下拉框
                    for widget in self.dialog.winfo_children():
                        if isinstance(widget, ctk.CTkFrame):
                            for w in widget.winfo_children():
                                if isinstance(w, ctk.CTkFrame):
                                    for cb in w.winfo_children():
                                        if isinstance(cb, ctk.CTkComboBox):
                                            profile_combobox = cb
                                            break

                    # 更新下拉框选项
                    if profile_combobox:
                        profile_combobox.configure(values=self.profiles)

                messagebox.showinfo("成功", f"已删除配置档案 {profile_name}", parent=self.dialog)
            else:
                messagebox.showerror("错误", f"删除配置档案失败", parent=self.dialog)
        except Exception as e:
            messagebox.showerror("错误", f"删除配置档案时出错: {e}", parent=self.dialog)

    def _get_bg_color(self):
        """获取系统背景颜色"""
        try:
            # 尝试获取系统背景颜色
            bg_color = self.dialog.cget("background")
            return bg_color
        except:
            # 如果失败，返回白色
            return "white"


class OptimizeDialog:
    """内容优化对话框，用于优化小说内容"""

    def __init__(self, parent, ai_engine, content=None, callback=None):
        """
        初始化优化对话框

        Args:
            parent: 父窗口
            ai_engine: AI引擎实例
            content: 初始内容
            callback: 回调函数，用于将优化结果返回给父窗口
        """
        self.parent = parent
        self.ai_engine = ai_engine
        self.initial_content = content or ""
        self.result = None
        self.optimized_result = None
        self.callback = callback

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
        # 移除 grab_set 使对话框为非模态
        # self.dialog.grab_set()

        # 设置关闭窗口协议
        self.dialog.protocol("WM_DELETE_WINDOW", self._on_close)

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

        # 不再等待对话框关闭，允许与主窗口交互
        # self.dialog.wait_window(self.dialog)

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
        ).pack(side=tk.LEFT, padx=(0, 10))
        
        # 保存为新条目按钮
        ctk.CTkButton(
            button_frame,
            text="保存为新条目",
            command=self._on_save_as_new
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
        """创建标准Tkinter UI"""
        dialog = self.dialog
        dialog.configure(background=self._get_bg_color())

        # 主框架
        main_frame = ttk.Frame(dialog)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # 配置档案管理区域
        profile_frame = ttk.Frame(main_frame)
        profile_frame.pack(fill=tk.X, pady=(0, 15))

        ttk.Label(
            profile_frame,
            text="配置档案:",
            font=("Microsoft YaHei UI", 11)
        ).pack(side=tk.LEFT, padx=(0, 5), pady=10)

        # 配置档案下拉选择框
        profile_combobox = ttk.Combobox(
            profile_frame,
            values=self.profiles,
            textvariable=self.profile_var,
            width=18,
            state="readonly"
        )
        profile_combobox.pack(side=tk.LEFT, padx=5, pady=10)
        profile_combobox.bind("<<ComboboxSelected>>", lambda event: self._on_profile_change(profile_combobox.get()))

        # 配置档案管理按钮
        ttk.Button(
            profile_frame,
            text="另存为...",
            width=8,
            command=self._save_as_new_profile
        ).pack(side=tk.LEFT, padx=5, pady=10)

        ttk.Button(
            profile_frame,
            text="删除",
            width=6,
            command=self._delete_current_profile,
            style="Danger.TButton"  # 假设有一个危险按钮样式
        ).pack(side=tk.LEFT, padx=5, pady=10)

        # 标题
        title_label = ttk.Label(
            main_frame,
            text="AI模型配置",
            font=("Microsoft YaHei UI", 16, "bold")
        )
        title_label.pack(pady=(0, 20))

        # 底部按钮 (移到选项卡之前创建和pack)
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(20, 0))

        ttk.Button(
            button_frame,
            text="测试连接",
            command=self._test_connection
        ).pack(side=tk.LEFT, padx=(0, 10))

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

        # 创建选项卡 (在按钮框架之后pack，使其填充剩余空间)
        tab_view = ttk.Notebook(main_frame)
        tab_view.pack(fill=tk.BOTH, expand=True)

        # 创建标签页
        general_tab = ttk.Frame(tab_view)
        advanced_tab = ttk.Frame(tab_view)

        tab_view.add(general_tab, text="通用配置")
        tab_view.add(advanced_tab, text="高级设置")

        # === 通用配置标签页 ===
        # 配置general_tab的列权重
        general_tab.grid_columnconfigure(1, weight=1)

        # 模型提供商 (Row 0)
        ttk.Label(general_tab, text="模型提供商:").grid(row=0, column=0, sticky=tk.W, pady=(10, 5), padx=5)

        self.provider_var = tk.StringVar()
        provider_combo = ttk.Combobox(
            general_tab,
            textvariable=self.provider_var,
            values=["OpenAI", "智谱AI", "讯飞星火", "百度文心", "硅基流动", "自定义"],
            state="readonly"
        )
        provider_combo.grid(row=0, column=1, sticky="ew", pady=(10, 15), padx=5)

        # API密钥 (Row 1, 2)
        ttk.Label(general_tab, text="API密钥:").grid(row=1, column=0, sticky=tk.W, pady=(0, 5), padx=5)

        key_frame = ttk.Frame(general_tab)
        key_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 15), padx=5)
        key_frame.grid_columnconfigure(0, weight=1) # 让输入框填充

        self.api_key_var = tk.StringVar()
        self.api_key_entry = ttk.Entry(
            key_frame,
            textvariable=self.api_key_var,
            show="*"
        )
        self.api_key_entry.grid(row=0, column=0, sticky="ew")

        self.show_key_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            key_frame,
            text="显示",
            variable=self.show_key_var,
            command=self._toggle_key_visibility
        ).grid(row=0, column=1, padx=(10, 0))

        # API URL (Row 3, 4)
        ttk.Label(general_tab, text="API URL:").grid(row=3, column=0, sticky=tk.W, pady=(0, 5), padx=5)

        self.api_url_var = tk.StringVar()
        ttk.Entry(
            general_tab,
            textvariable=self.api_url_var
        ).grid(row=4, column=1, sticky="ew", pady=(0, 15), padx=5)

        # 模型名称 (Row 5, 6)
        ttk.Label(general_tab, text="模型名称:").grid(row=5, column=0, sticky=tk.W, pady=(0, 5), padx=5)

        self.model_name_var = tk.StringVar()
        ttk.Entry(
            general_tab,
            textvariable=self.model_name_var
        ).grid(row=6, column=1, sticky="ew", pady=(0, 15), padx=5)

        # === 高级设置标签页 ===
        advanced_frame = ttk.Frame(advanced_tab)
        advanced_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 最大Token数
        ttk.Label(advanced_frame, text="最大Token数:").pack(anchor=tk.W, pady=(10, 5))

        token_frame = ttk.Frame(advanced_frame)
        token_frame.pack(fill=tk.X, pady=(0, 15))

        self.max_tokens_var = tk.IntVar(value=4000)
        ttk.Scale(
            token_frame,
            from_=500,
            to=16000,
            variable=self.max_tokens_var,
            orient=tk.HORIZONTAL
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, pady=10)

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

    def _save_to_config_file(self, config):
        """
        保存配置到文件

        Args:
            config: 配置字典
        """
        try:
            # 获取当前选择的配置档案名称
            profile_name = self.profile_var.get()

            # 保存到指定配置档案
            save_profile(profile_name, config)

            # 设置为当前活动配置
            set_current_profile(profile_name)

            # 同时保存一份到旧的配置文件路径，保持兼容性
            config_dir = Path("config")
            config_dir.mkdir(exist_ok=True)
            config_file = _config_path

            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)

            print(f"配置已保存到 {profile_name} 和旧版配置文件")

            # 更新全局AI引擎实例的配置
            global _ai_engine_instance
            if _ai_engine_instance:
                _ai_engine_instance.update_config(config)

        except Exception as e:
            print(f"保存配置文件时出错: {e}")
            messagebox.showwarning("警告", f"保存配置文件时出错: {e}", parent=self.dialog)

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

        # 获取当前选择的配置档案名称
        profile_name = self.profile_var.get()

        # 保存到当前选择的配置档案
        self._save_to_config_file(config)

        # 调用回调函数
        if self.callback:
            self.callback(config)

        # 关闭对话框
        self.dialog.destroy()

    def _on_cancel(self):
        """取消并关闭对话框"""
        self.result = None
        self.dialog.destroy()

    def _on_profile_change(self, profile_name):
        """
        当配置档案改变时的处理

        Args:
            profile_name: 选择的配置档案名称
        """
        if profile_name == self.current_profile_name:
            return

        # 询问是否保存当前修改
        if messagebox.askyesno("保存修改",
                               f"切换到配置档案 {profile_name} 前，是否保存当前对 {self.current_profile_name} 的修改？",
                               parent=self.dialog):
            current_config = self._get_config()
            save_profile(self.current_profile_name, current_config)

        # 加载选择的配置档案
        try:
            new_config = load_profile(profile_name)

            # 更新当前选择的配置档案名称
            self.current_profile_name = profile_name

            # 更新UI显示
            self.config = new_config
            self._load_config()

            print(f"切换到配置档案: {profile_name}")
        except Exception as e:
            messagebox.showerror("错误", f"加载配置档案失败: {e}", parent=self.dialog)
            # 重置下拉框为当前配置档案
            self.profile_var.set(self.current_profile_name)

    def _save_as_new_profile(self):
        """保存为新的配置档案"""
        # 询问新配置档案名称
        new_name = simpledialog.askstring(
            "保存为新配置档案",
            "请输入新配置档案名称:",
            parent=self.dialog
        )

        if not new_name:
            return

        # 检查名称是否有效
        if not re.match(r'^[a-zA-Z0-9_\-\u4e00-\u9fa5]+$', new_name):
            messagebox.showerror("错误", "配置名称只能包含字母、数字、下划线、中文和连字符", parent=self.dialog)
            return

        # 检查是否已存在同名配置
        if new_name in self.profiles:
            if not messagebox.askyesno("确认覆盖", f"配置档案 {new_name} 已存在，是否覆盖？", parent=self.dialog):
                return

        # 获取当前配置
        current_config = self._get_config()

        try:
            # 保存为新配置档案
            save_profile(new_name, current_config)

            # 刷新配置档案列表
            self.profiles = list_profiles()

            # 更新下拉框选项
            if hasattr(self, 'dialog') and self.dialog.winfo_exists():
                profile_combobox = None

                # 查找配置档案下拉框
                for widget in self.dialog.winfo_children():
                    if isinstance(widget, ctk.CTkFrame):
                        for w in widget.winfo_children():
                            if isinstance(w, ctk.CTkFrame):
                                for cb in w.winfo_children():
                                    if isinstance(cb, ctk.CTkComboBox):
                                        profile_combobox = cb
                                        break

                # 更新下拉框选项
                if profile_combobox:
                    profile_combobox.configure(values=self.profiles)

            # 设置当前选择的配置档案
            self.profile_var.set(new_name)
            self.current_profile_name = new_name

            # 设置为当前活动配置
            set_current_profile(new_name)

            messagebox.showinfo("成功", f"已将当前配置保存为 {new_name}", parent=self.dialog)
        except Exception as e:
            messagebox.showerror("错误", f"保存配置档案失败: {e}", parent=self.dialog)

    def _delete_current_profile(self):
        """删除当前配置档案"""
        # 获取当前选择的配置档案
        profile_name = self.profile_var.get()

        # 不允许删除默认配置
        if profile_name == "default":
            messagebox.showinfo("提示", "默认配置不能被删除", parent=self.dialog)
            return

        # 确认删除
        if not messagebox.askyesno("确认删除", f"确定要删除配置档案 {profile_name} 吗？此操作不可恢复。",
                                   parent=self.dialog):
            return

        try:
            # 删除配置档案
            if delete_profile(profile_name):
                # 刷新配置档案列表
                self.profiles = list_profiles()

                # 切换到默认配置
                self.profile_var.set("default")
                self.current_profile_name = "default"

                # 加载默认配置
                new_config = load_profile("default")
                self.config = new_config
                self._load_config()

                # 更新下拉框选项
                if hasattr(self, 'dialog') and self.dialog.winfo_exists():
                    profile_combobox = None

                    # 查找配置档案下拉框
                    for widget in self.dialog.winfo_children():
                        if isinstance(widget, ctk.CTkFrame):
                            for w in widget.winfo_children():
                                if isinstance(w, ctk.CTkFrame):
                                    for cb in w.winfo_children():
                                        if isinstance(cb, ctk.CTkComboBox):
                                            profile_combobox = cb
                                            break

                    # 更新下拉框选项
                    if profile_combobox:
                        profile_combobox.configure(values=self.profiles)

                messagebox.showinfo("成功", f"已删除配置档案 {profile_name}", parent=self.dialog)
            else:
                messagebox.showerror("错误", f"删除配置档案失败", parent=self.dialog)
        except Exception as e:
            messagebox.showerror("错误", f"删除配置档案时出错: {e}", parent=self.dialog)

    def _get_bg_color(self):
        """获取系统背景颜色"""
        try:
            # 尝试获取系统背景颜色
            bg_color = self.dialog.cget("background")
            return bg_color
        except:
            # 如果失败，返回白色
            return "white"


# --- 辅助函数 ---

def load_ai_config(profile_name=None):
    """
    加载AI配置

    Args:
        profile_name: 要加载的配置档案名称，如果为None则加载当前活动配置

    Returns:
        配置字典
    """
    # 如果未指定配置名称，使用当前活动配置
    if profile_name is None:
        profile_name = get_current_profile_name()

    # 加载指定的配置档案
    config = load_profile(profile_name)

    # 兼容旧版本：如果配置档案为空但存在旧的配置文件，则从旧文件加载
    if not config.get("api_key") and _config_path.exists():
        try:
            with open(_config_path, "r", encoding="utf-8") as f:
                old_config = json.load(f)
                # 只更新API密钥等敏感信息，其他保留配置档案设置
                if old_config.get("api_key"):
                    config["api_key"] = old_config["api_key"]
                if old_config.get("api_url"):
                    config["api_url"] = old_config["api_url"]
                print(f"已从旧配置文件加载API信息")

                # 保存回配置档案
                save_profile(profile_name, config)
        except Exception as e:
            print(f"从旧配置加载时出错: {e}")

    return config


def get_ai_engine():
    """
    获取AI引擎实例，如果不存在则创建一个

    Returns:
        AIEngine实例
    """
    global _ai_engine_instance

    if _ai_engine_instance is None:
        # 加载当前活动的配置
        config = load_ai_config()
        # 创建AI引擎实例
        _ai_engine_instance = AIEngine(config)
    else:
        # 如果实例已存在，确保它使用最新的配置
        config = load_ai_config()
        _ai_engine_instance.update_config(config)

    return _ai_engine_instance
