# --- START OF FILE 小说助手_完整修复版.py ---

import os
import re
import json
import datetime
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, simpledialog, Menu, Toplevel, Listbox, Scrollbar, Frame, Label, \
    Entry, Button, PanedWindow
from pathlib import Path
import shutil  # For moving directories and emptying trash
import uuid  # Potentially for more robust unique naming
import glob
import tkinter.font as tkFont
import configparser  # 用于保存配置
import platform  # 获取操作系统信息
import subprocess  # For opening folders on macOS and Linux

# Import the theme library - place this early
try:
    import sv_ttk

    HAS_SVTTK = True
except ImportError:
    # print("Warning: sv-ttk theme library not found. Using default Tkinter theme.")
    sv_ttk = None
    HAS_SVTTK = False

# 尝试导入CustomTkinter
try:
    import customtkinter as ctk

    HAS_CTK = True
    HAS_CTK_PANED = False  # CustomTkinter没有PanedWindow组件，仍需使用ttk.PanedWindow
except ImportError:
    print("Warning: CustomTkinter库未找到。将使用默认Tkinter主题，建议安装：pip install customtkinter")
    HAS_CTK = False
    HAS_CTK_PANED = False


# --- 添加字体管理类 ---
class FontManager:
    def __init__(self):
        """初始化字体管理器"""
        self.system_fonts = []
        self.custom_fonts = []
        self.current_font = "Microsoft YaHei UI"  # 默认字体
        self.font_size = 15  # 默认字体大小
        self.config_path = Path("settings.ini")  # 配置文件路径
        self.use_custom_fonts = False  # 是否使用自定义字体而非系统字体
        self.custom_fonts_dir = Path("font")  # 自定义字体文件夹路径
        self.load_system_fonts()
        self.load_settings()  # 加载保存的设置

        # 确保字体文件夹存在
        if not self.custom_fonts_dir.exists():
            try:
                self.custom_fonts_dir.mkdir(exist_ok=True)
                print(f"已创建字体文件夹: {self.custom_fonts_dir}")
            except Exception as e:
                print(f"创建字体文件夹失败: {e}")

    def load_system_fonts(self):
        """加载系统字体"""
        try:
            # 使用tkinter获取系统字体
            font_families = list(tkFont.families())
            # 过滤掉一些特殊字体
            self.system_fonts = [f for f in font_families if not f.startswith('@') and f != 'MS Gothic']
            self.system_fonts.sort()
        except Exception as e:
            print(f"加载系统字体时出错: {e}")
            self.system_fonts = ["Microsoft YaHei UI", "SimSun", "Arial", "Times New Roman"]

    def load_custom_fonts_from_directory(self, directory_path):
        """从指定目录加载自定义字体文件"""
        self.custom_fonts = []
        try:
            font_path = Path(directory_path)
            if not font_path.exists() or not font_path.is_dir():
                return False

            # 支持的字体文件扩展名
            font_extensions = ['.ttf', '.otf', '.ttc', '.fon']

            # 遍历目录查找字体文件
            for ext in font_extensions:
                for font_file in font_path.glob(f'*{ext}'):
                    # 仅添加文件名（不含扩展名）作为字体名称
                    self.custom_fonts.append({
                        "name": font_file.stem,
                        "path": str(font_file)
                    })

            return len(self.custom_fonts) > 0
        except Exception as e:
            print(f"从目录加载字体时出错: {e}")
            return False

    def register_custom_font(self, font_path):
        """注册自定义字体(平台限制)"""
        try:
            font_path_obj = Path(font_path)
            if not font_path_obj.exists() or not font_path_obj.is_file():
                return False

            # Windows平台尝试注册字体
            system = platform.system()
            if system == 'Windows':
                # 使用Windows API尝试临时加载字体
                import ctypes
                from ctypes import wintypes

                # Windows API常量
                HWND_BROADCAST = 0xFFFF
                WM_FONTCHANGE = 0x001D
                FR_PRIVATE = 0x10

                gdi32 = ctypes.WinDLL('gdi32')
                user32 = ctypes.WinDLL('user32')

                # AddFontResourceEx函数
                add_font_resource_ex = gdi32.AddFontResourceExW
                add_font_resource_ex.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.PVOID]
                add_font_resource_ex.restype = wintypes.INT

                # 尝试加载字体
                font_path_str = str(font_path_obj)
                result = add_font_resource_ex(font_path_str, FR_PRIVATE, 0)

                # 通知应用字体变化
                if result > 0:
                    user32.SendMessageW(HWND_BROADCAST, WM_FONTCHANGE, 0, 0)
                    return True

            return False
        except Exception as e:
            print(f"注册自定义字体时出错: {e}")
            return False

    def get_all_fonts(self):
        """获取所有可用字体（系统或自定义，取决于设置）"""
        # 根据设置返回不同的字体集
        if self.use_custom_fonts:
            # 只返回自定义字体
            fonts = [f["name"] for f in self.custom_fonts]
            # 如果自定义字体为空，提供提示信息
            if not fonts:
                return ["<文件夹中无字体文件>"]
            return fonts
        else:
            # 只返回系统字体
            return self.system_fonts

    def load_settings(self):
        """从配置文件加载字体设置"""
        try:
            if self.config_path.exists():
                config = configparser.ConfigParser()
                config.read(self.config_path, encoding='utf-8')

                if 'Fonts' in config:
                    if 'current_font' in config['Fonts']:
                        saved_font = config['Fonts']['current_font']
                        # 确保字体存在于系统中
                        if saved_font in self.system_fonts or any(f['name'] == saved_font for f in self.custom_fonts):
                            self.current_font = saved_font

                    if 'font_size' in config['Fonts']:
                        try:
                            self.font_size = int(config['Fonts']['font_size'])
                        except ValueError:
                            pass  # 使用默认值

                    if 'use_custom_fonts' in config['Fonts']:
                        self.use_custom_fonts = config['Fonts'].getboolean('use_custom_fonts')

                if 'CustomFonts' in config:
                    # 加载上次使用的自定义字体文件夹
                    if 'last_folder' in config['CustomFonts']:
                        last_folder = config['CustomFonts']['last_folder']
                        custom_folder_path = Path(last_folder)
                        if custom_folder_path.exists():
                            self.custom_fonts_dir = custom_folder_path
                            if self.use_custom_fonts:
                                self.load_custom_fonts_from_directory(last_folder)
                        else:
                            # 如果之前的文件夹不存在，使用默认font文件夹
                            self.custom_fonts_dir = Path("font")
        except Exception as e:
            print(f"加载字体设置时出错: {e}")

    def save_settings(self, custom_fonts_folder=None):
        """保存字体设置到配置文件"""
        try:
            config = configparser.ConfigParser()

            # 尝试读取现有配置
            if self.config_path.exists():
                config.read(self.config_path, encoding='utf-8')

            # 确保Fonts节存在
            if 'Fonts' not in config:
                config['Fonts'] = {}

            config['Fonts']['current_font'] = self.current_font
            config['Fonts']['font_size'] = str(self.font_size)
            config['Fonts']['use_custom_fonts'] = str(self.use_custom_fonts)

            # 保存自定义字体文件夹
            if 'CustomFonts' not in config:
                config['CustomFonts'] = {}

            # 如果提供了新的文件夹路径，则使用它，否则使用当前路径
            if custom_fonts_folder:
                config['CustomFonts']['last_folder'] = custom_fonts_folder
            else:
                config['CustomFonts']['last_folder'] = str(self.custom_fonts_dir)

            # 写入配置文件
            with open(self.config_path, 'w', encoding='utf-8') as f:
                config.write(f)

            return True
        except Exception as e:
            print(f"保存字体设置时出错: {e}")
            return False


# --- Custom Dialog for Moving Entries ---
# (代码与上一个版本相同，保持不变)
class MoveEntryDialog(ctk.CTkToplevel if HAS_CTK else Toplevel):
    def __init__(self, parent, existing_categories, current_category):
        super().__init__(parent)
        self.title("移动条目到分类")
        self.geometry("450x250")  # 稍微调整尺寸
        self.transient(parent)
        self.grab_set()
        # 设置窗口背景匹配主题
        if HAS_CTK:
            bg_color = ctk.ThemeManager.theme["CTkFrame"]["fg_color"]
            mode_index = 0 if ctk.get_appearance_mode().lower() == 'light' else 1
            dialog_bg = bg_color[mode_index] if isinstance(bg_color, (list, tuple)) else bg_color
            self.configure(fg_color=dialog_bg)

        self.result = None
        # 修正：如果 current_category 为 None（例如，从搜索结果移动），不过滤
        if current_category is not None:
            self.existing_categories = sorted([cat for cat in existing_categories if cat != current_category])
        else:
            self.existing_categories = sorted(existing_categories)

        # --- 控件 ---
        if HAS_CTK:
            main_frame = ctk.CTkFrame(self, fg_color="transparent")  # 透明背景，使用 Toplevel 背景色
            main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

            ctk.CTkLabel(main_frame, text="选择或创建目标分类:",
                         font=("Microsoft YaHei UI", 14, "bold")).grid(row=0, column=0, columnspan=2, pady=(0, 20),
                                                                       sticky='w')

            ctk.CTkLabel(main_frame, text="选择现有分类:", font=("Microsoft YaHei UI", 15)).grid(row=1, column=0,
                                                                                                 padx=(0, 10),
                                                                                                 sticky='w')
            self.category_combo = ctk.CTkComboBox(main_frame, values=self.existing_categories, width=280,
                                                  font=("Microsoft YaHei UI", 15))
            self.category_combo.grid(row=1, column=1, sticky='ew')
            # 修复：CTkComboBox 没有 <<ComboboxSelected>> 事件，使用 command
            self.category_combo.configure(command=self.on_combo_select)  # 使用 command 回调

            ctk.CTkLabel(main_frame, text="或新建分类:", font=("Microsoft YaHei UI", 15)).grid(row=2, column=0,
                                                                                               padx=(0, 10),
                                                                                               pady=(15, 0), sticky='w')
            self.new_category_entry = ctk.CTkEntry(main_frame, width=280, font=("Microsoft YaHei UI", 15))
            self.new_category_entry.grid(row=2, column=1, pady=(15, 0), sticky='ew')
            self.new_category_entry.bind("<KeyRelease>", self.on_entry_type)

            button_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
            button_frame.grid(row=3, column=0, columnspan=2, pady=(30, 0))  # 增加按钮上边距

            # 调整按钮大小和字体
            ok_button = ctk.CTkButton(button_frame, text="确定", command=self.on_ok, width=80,
                                      font=("Microsoft YaHei UI", 15))
            ok_button.pack(side=tk.LEFT, padx=10)
            cancel_button = ctk.CTkButton(button_frame, text="取消", command=self.on_cancel, width=80,
                                          font=("Microsoft YaHei UI", 15),
                                          fg_color="#E0E0E0" if ctk.get_appearance_mode().lower() == 'light' else "#505050",
                                          # 根据主题调整取消按钮颜色
                                          text_color="#303030" if ctk.get_appearance_mode().lower() == 'light' else "#D0D0D0")
            cancel_button.pack(side=tk.LEFT, padx=10)
        else:
            # 原始Tkinter版本实现 (保持不变)
            main_frame = ttk.Frame(self, padding="10")
            main_frame.pack(fill=tk.BOTH, expand=True)
            ttk.Label(main_frame, text="选择现有分类或输入新分类:").grid(row=0, column=0, columnspan=2, pady=(0, 10),
                                                                         sticky='w')
            ttk.Label(main_frame, text="选择分类:").grid(row=1, column=0, padx=(0, 5), sticky='w')
            self.category_combo = ttk.Combobox(main_frame, values=self.existing_categories, state="readonly", width=30)
            self.category_combo.grid(row=1, column=1, sticky='ew')
            self.category_combo.bind("<<ComboboxSelected>>", self.on_combo_select)
            ttk.Label(main_frame, text="或新建分类:").grid(row=2, column=0, padx=(0, 5), pady=(5, 0), sticky='w')
            self.new_category_entry = ttk.Entry(main_frame)
            self.new_category_entry.grid(row=2, column=1, pady=(5, 0), sticky='ew')
            self.new_category_entry.bind("<KeyRelease>", self.on_entry_type)
            button_frame = ttk.Frame(main_frame)
            button_frame.grid(row=3, column=0, columnspan=2, pady=(15, 0))
            ok_button = ttk.Button(button_frame, text="确定", command=self.on_ok)
            ok_button.pack(side=tk.LEFT, padx=5)
            cancel_button = ttk.Button(button_frame, text="取消", command=self.on_cancel)
            cancel_button.pack(side=tk.LEFT, padx=5)

        main_frame.columnconfigure(1, weight=1)

        # Set focus initially
        if self.existing_categories:
            if hasattr(self.category_combo, 'focus_set'): self.category_combo.focus_set()
            if HAS_CTK and hasattr(self.category_combo,
                                   '_entry'): self.category_combo._entry.focus_set()  # CTk ComboBox focus fix
        elif hasattr(self.new_category_entry, 'focus_set'):
            self.new_category_entry.focus_set()

        self.wait_window(self)

    # 适配 CTkComboBox 的 command 回调
    def on_combo_select(self, choice=None):  # command 会传递选择的值
        """Clear the entry field when a category is selected from the combobox."""
        if hasattr(self, 'new_category_entry') and self.new_category_entry.winfo_exists():  # 确保 entry 存在
            self.new_category_entry.delete(0, tk.END)

    def on_entry_type(self, event=None):
        """Clear the combobox selection when typing in the entry field."""
        if hasattr(self,
                   'new_category_entry') and self.new_category_entry.winfo_exists() and self.new_category_entry.get():
            if hasattr(self, 'category_combo') and self.category_combo.winfo_exists():  # 确保 combo 存在
                self.category_combo.set('')  # Clear selection

    def on_ok(self):
        selected_category = self.category_combo.get()
        new_category_name = self.new_category_entry.get().strip()

        if new_category_name:
            if new_category_name == "_trash":
                messagebox.showerror("错误", "分类名称 '_trash' 是保留名称。", parent=self)
                return
            if re.search(r'[<>:"/\\|?*]', new_category_name) or any(ord(c) < 32 for c in new_category_name):
                messagebox.showerror("错误", "分类名称包含无效字符或控制字符。", parent=self)
                return
            self.result = new_category_name
        elif selected_category:
            self.result = selected_category
        else:
            messagebox.showwarning("选择分类", "请选择一个现有分类或输入一个新的分类名称。", parent=self)
            return

        self.destroy()

    def on_cancel(self):
        self.result = None
        self.destroy()


# --- Custom Dialog for Viewing Trash ---
# (代码与上一个版本相同，保持不变)
class TrashDialog(Toplevel):
    def __init__(self, parent, trash_items):
        super().__init__(parent)
        self.title("回收站内容")
        self.geometry("550x450")  # 稍大一点
        self.transient(parent)
        self.grab_set()

        self.selected_items = []
        self.result_action = None

        # --- 使用 ttk 样式 ---
        style = ttk.Style(self)
        # 尝试应用父窗口的主题 (如果父窗口是 CTk)
        parent_bg = self.master.cget('bg')  # 获取父窗口背景色

        self.configure(bg=parent_bg)  # 设置对话框背景色
        style.configure("TFrame", background=parent_bg)
        style.configure("TLabel", background=parent_bg, font=("Microsoft YaHei UI", 11))
        style.configure("TButton", font=("Microsoft YaHei UI", 11), padding=5)

        # 如果父窗口是 CTk，尝试获取更精确的颜色
        list_bg, list_fg, list_select_bg, list_select_fg = None, None, None, None
        list_hl_bg, list_hl_color = None, None
        dialog_fg = 'white'  # 默认文本颜色改为白色，更适合深色背景

        if HAS_CTK and isinstance(parent, ctk.CTk):
            current_mode = ctk.get_appearance_mode().lower()
            mode_index = 0 if current_mode == 'light' else 1

            bg_color = ctk.ThemeManager.theme["CTkFrame"]["fg_color"]
            fg_color = ctk.ThemeManager.theme["CTkLabel"]["text_color"]
            select_bg = ctk.ThemeManager.theme["CTkButton"]["fg_color"]
            select_fg = ctk.ThemeManager.theme["CTkButton"]["text_color"]

            dialog_bg = bg_color[mode_index] if isinstance(bg_color, (list, tuple)) else bg_color
            dialog_fg = fg_color[mode_index] if isinstance(fg_color, (list, tuple)) else fg_color
            list_select_bg = select_bg[mode_index] if isinstance(select_bg, (list, tuple)) else select_bg
            list_select_fg = select_fg[mode_index] if isinstance(select_fg, (list, tuple)) else select_fg
            list_bg = ctk.ThemeManager.theme["CTkTextbox"]["fg_color"][mode_index]
            list_hl_bg = ctk.ThemeManager.theme["CTkFrame"]["border_color"][mode_index]
            list_hl_color = list_select_bg

            self.configure(bg=dialog_bg)
            style.configure("TFrame", background=dialog_bg)
            style.configure("TLabel", background=dialog_bg, foreground=dialog_fg)
            # ttk按钮颜色仍可能受限
            btn_bg = ctk.ThemeManager.theme["CTkButton"]["fg_color"][mode_index]
            btn_fg = ctk.ThemeManager.theme["CTkButton"]["text_color"][mode_index]
            style.map("TButton",
                      background=[('active', btn_bg), ('!disabled', btn_bg)],
                      foreground=[('active', btn_fg), ('!disabled', btn_fg)])

        main_frame = ttk.Frame(self, padding="15")  # 增加内边距
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main_frame, text="回收站中的项目 (文件或分类):",
                  font=("Microsoft YaHei UI", 13, "bold"),
                  foreground=dialog_fg).pack(anchor=tk.W, pady=(0, 10))

        list_frame = ttk.Frame(main_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 15))

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL)
        self.listbox = Listbox(
            list_frame,
            yscrollcommand=scrollbar.set,
            selectmode=tk.EXTENDED,
            exportselection=False,
            relief=tk.FLAT,
            borderwidth=1,
            font=("Microsoft YaHei UI", 15),
            activestyle='none',
            bd=10,  # 添加内边距但不改变数据
            fg="white"  # 设置文本颜色为白色
        )
        scrollbar.config(command=self.listbox.yview)

        # 始终使用深色背景和白色文本
        select_bg = "#464646"  # 深灰色背景
        select_fg = "white"  # 白色文本
        list_bg = "#2b2b2b"  # 深灰色背景

        # 应用颜色
        self.listbox.config(
            selectbackground=select_bg,
            selectforeground=select_fg,
            bg=list_bg
        )

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.item_map = {}
        for item_path in sorted(trash_items, key=lambda p: p.name):
            display_name = item_path.name
            self.listbox.insert(tk.END, display_name)
            self.item_map[display_name] = item_path

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X)

        # 使用CTk按钮替代ttk按钮，确保按钮可见
        if HAS_CTK:
            # 获取当前主题模式和颜色
            mode = "dark" if ctk.get_appearance_mode().lower() == "dark" else "light"
            # 从父窗口获取软色调颜色
            soft_colors = parent.soft_colors[mode] if hasattr(parent, 'soft_colors') else {
                "button_blue": "#4a6f8a",
                "button_blue_hover": "#5a819b",
                "button_red": "#8b4e52",
                "button_red_hover": "#9b5e62",
                "list_select_fg": "white"
            }

            restore_button = ctk.CTkButton(
                button_frame,
                text="恢复选中项",
                fg_color=soft_colors["button_blue"],
                hover_color=soft_colors["button_blue_hover"],
                text_color="white",
                command=self.on_restore
            )
            restore_button.pack(side=tk.LEFT, padx=5, pady=5)

            delete_button = ctk.CTkButton(
                button_frame,
                text="永久删除选中项",
                fg_color=soft_colors["button_red"],
                hover_color=soft_colors["button_red_hover"],
                text_color="white",
                command=self.on_delete_selected
            )
            delete_button.pack(side=tk.LEFT, padx=5, pady=5)

            close_button = ctk.CTkButton(
                button_frame,
                text="关闭",
                fg_color=soft_colors["button_blue"],
                hover_color=soft_colors["button_blue_hover"],
                text_color="white",
                command=self.on_cancel
            )
            close_button.pack(side=tk.RIGHT, padx=5, pady=5)
        else:
            # 使用高对比度的ttk按钮
            style.configure("TButton", foreground="black", background="light gray")

            restore_button = ttk.Button(button_frame, text="恢复选中项", command=self.on_restore)
            restore_button.pack(side=tk.LEFT, padx=5, pady=5)

            delete_button = ttk.Button(button_frame, text="永久删除选中项", command=self.on_delete_selected)
            delete_button.pack(side=tk.LEFT, padx=5, pady=5)

            close_button = ttk.Button(button_frame, text="关闭", command=self.on_cancel)
            close_button.pack(side=tk.RIGHT, padx=5, pady=5)

        self.protocol("WM_DELETE_WINDOW", self.on_cancel)
        self.wait_window(self)

    def on_restore(self):
        selected_indices = self.listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("选择项目", "请先选择要恢复的项目。", parent=self)
            return
        self.selected_items = [self.item_map[self.listbox.get(index)] for index in selected_indices]
        self.result_action = "restore"
        self.destroy()

    def on_delete_selected(self):
        selected_indices = self.listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("选择项目", "请先选择要永久删除的项目。", parent=self)
            return

        items_to_delete_paths = []
        items_to_delete_names = []
        for index in selected_indices:
            display_name = self.listbox.get(index)
            items_to_delete_paths.append(self.item_map[display_name])
            items_to_delete_names.append(f"'{display_name}'")

        num_items = len(items_to_delete_paths)
        name_list_str = "\n - ".join(items_to_delete_names) if num_items <= 5 else f"\n({num_items}个项目)"

        if messagebox.askyesno("确认永久删除",
                               f"确定要从回收站永久删除以下项目吗？\n{name_list_str}\n\n**警告：此操作无法撤销！**",
                               icon='warning', parent=self):
            self.selected_items = items_to_delete_paths
            self.result_action = "delete"
            self.destroy()

    def on_cancel(self):
        self.selected_items = []
        self.result_action = None
        self.destroy()


# --- Backend Logic (NovelManager) ---
# (代码与上一个版本相同，保持不变)
class NovelManager:
    def __init__(self, root_dir="novel_data"):
        """Initialize novel manager using pathlib."""
        self.root_dir = Path(root_dir).resolve()
        self.trash_dir = self.root_dir / "_trash"
        self._ensure_directories()
        self.categories = self._load_categories()

    def _ensure_directories(self):
        """Ensure base and trash directories exist."""
        self.root_dir.mkdir(exist_ok=True)
        self.trash_dir.mkdir(exist_ok=True)

    def _load_categories(self):
        """Load categories from directories, excluding trash, and return sorted."""
        try:
            cats = [d.name for d in self.root_dir.iterdir()
                    if d.is_dir() and d.name != "_trash"]
            cats.sort(key=lambda x: x.lower())  # Sort case-insensitively
            return cats
        except OSError as e:
            print(f"Error loading categories from {self.root_dir}: {e}")
            # Propagate the error or return empty list? Returning empty might hide issues.
            raise OSError(f"无法加载分类目录: {e}")

    def _get_safe_filename(self, title):
        """Create a safe filename from a title."""
        safe_title = re.sub(r'[<>:"/\\|?*]', "_", title)
        safe_title = re.sub(r'\s+', '_', safe_title)
        safe_title = safe_title.strip('_. ')
        if safe_title.upper() in ("CON", "PRN", "AUX", "NUL") or \
                re.match(r"^(COM|LPT)\d$", safe_title.upper()):
            safe_title = "_" + safe_title
        return safe_title if safe_title else "untitled"

    def _get_entry_path(self, category, title):
        """Get the Path object for a given category and title."""
        safe_filename = self._get_safe_filename(title) + ".md"
        category_path = self.root_dir / category
        return category_path / safe_filename

    def save_entry(self, category, title, content, tags=None, existing_path_str=None):
        """Save or update an entry. Handles rename/move via existing_path_str."""
        if not title:
            raise ValueError("标题不能为空")

        category_path = self.root_dir / category
        if not category_path.is_dir():
            try:
                # Attempt to add category if dir doesn't exist
                self.add_category(category)  # This raises error on invalid name/failure
            except (ValueError, OSError) as e:
                raise ValueError(f"无效或无法创建分类 '{category}': {e}")
        elif category not in self.categories:
            # Dir exists but not in list, add it
            self.categories.append(category)
            self.categories.sort(key=lambda x: x.lower())

        tags = tags or []
        now_iso = datetime.datetime.now().isoformat()
        new_file_path = self._get_entry_path(category, title)

        metadata = {
            "title": title,
            "created_at": now_iso,
            "updated_at": now_iso,
            "tags": tags
        }

        existing_path = Path(existing_path_str) if existing_path_str else None
        original_created_at = now_iso

        # Handle update/rename case
        if existing_path and existing_path.exists() and existing_path.is_file():
            try:
                existing_data = self.get_entry_by_path(existing_path, read_content=False)
                if existing_data and "metadata" in existing_data:
                    original_created_at = existing_data["metadata"].get("created_at", now_iso)
            except Exception as e:
                print(f"Warning: Could not read metadata from {existing_path}: {e}")

            # Check if filename needs to change (due to title change)
            # Note: _get_entry_path calculates the NEW expected path based on NEW title
            is_rename_or_move = (new_file_path != existing_path)
        else:
            existing_path = None  # Ensure it's None for new entries
            is_rename_or_move = False

        metadata["created_at"] = original_created_at
        metadata["updated_at"] = now_iso
        metadata["title"] = title  # Ensure user-facing title is correct

        file_content = f"---\n{json.dumps(metadata, ensure_ascii=False, indent=2)}\n---\n\n{content}"

        try:
            new_file_path.parent.mkdir(parents=True, exist_ok=True)

            # Prevent overwriting a DIFFERENT file if safe filename clashes
            if new_file_path.exists() and new_file_path != existing_path:
                # If it's the same logical file being updated (existing_path == new_file_path), allow overwrite.
                # Otherwise, raise error.
                raise FileExistsError(f"目标文件名 '{new_file_path.name}' 在分类 '{category}' 中已存在。")

            new_file_path.write_text(file_content, encoding="utf-8")

            # Delete old file *after* successful save if path changed
            if existing_path and existing_path.exists() and existing_path != new_file_path:
                try:
                    existing_path.unlink()
                except OSError as del_e:
                    print(f"Warning: Could not delete old file '{existing_path}' after rename/move: {del_e}")

            return str(new_file_path)
        except OSError as e:
            raise OSError(f"无法写入文件 '{new_file_path}': {e}")

    def delete_entry(self, entry_path_str):
        """Move an entry file to the trash directory."""
        path = Path(entry_path_str)
        if not path.exists() or not path.is_file() or self.trash_dir in path.parents:
            raise FileNotFoundError(f"无法删除：文件无效或已在回收站 '{entry_path_str}'")

        try:
            original_category = path.parent.name
            now_iso = datetime.datetime.now().isoformat()
            metadata = {"title": path.stem}
            content = ""
            try:
                entry_data = self.get_entry_by_path(path, read_content=True)
                if entry_data:
                    metadata = entry_data.get("metadata", metadata)
                    content = entry_data.get("content", "")
            except Exception as read_e:
                print(f"Warning: Could not read data from {path} before trashing: {read_e}")

            # Add trash metadata (no need to write back to original)
            metadata["_original_category"] = original_category
            metadata["_deleted_at"] = now_iso
            # Ensure title field exists in metadata for trash filename
            metadata["title"] = metadata.get("title", path.stem)

            # Define unique trash filename
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            base_name = self._get_safe_filename(metadata["title"])  # Use metadata title
            trash_filename = f"{ts}_{base_name}{path.suffix or '.md'}"
            target_trash_path = self.trash_dir / trash_filename

            counter = 0
            while target_trash_path.exists():
                counter += 1
                trash_filename = f"{ts}_{base_name}_{counter}{path.suffix or '.md'}"
                target_trash_path = self.trash_dir / trash_filename

            # Move the file
            shutil.move(str(path), str(target_trash_path))
            print(f"Moved entry to trash: {target_trash_path}")
            return True

        except Exception as e:
            raise OSError(f"无法移动文件 '{path}' 到回收站: {e}")

    def move_entry(self, entry_path_str, target_category):
        """Move an entry file to a different category."""
        entry_path = Path(entry_path_str)
        if not entry_path.exists() or not entry_path.is_file():
            raise FileNotFoundError(f"源文件不存在: {entry_path_str}")
        if self.trash_dir in entry_path.parents:
            raise ValueError("不能从此方法移出回收站中的文件。")
        if target_category == "_trash":
            raise ValueError("不能使用 'move' 移动到回收站，请使用 'delete'。")

        target_category_path = self.root_dir / target_category
        if not target_category_path.exists():
            try:
                self.add_category(target_category)  # Creates dir and adds to list
            except (ValueError, OSError) as e:
                raise OSError(f"无法创建目标分类 '{target_category}' 以进行移动: {e}")
        elif target_category not in self.categories:
            # Dir exists but not in list, add it
            self.categories.append(target_category)
            self.categories.sort(key=lambda x: x.lower())

        new_path = target_category_path / entry_path.name

        if new_path.exists():
            raise FileExistsError(f"目标位置已存在同名文件: {new_path}")

        try:
            shutil.move(str(entry_path), str(new_path))
            return str(new_path)
        except Exception as e:
            raise OSError(f"无法移动文件 '{entry_path}' 到 '{new_path}': {e}")

    def search(self, query, categories=None):
        """Search content across specified categories (or all)."""
        results = []
        search_query = query.lower().strip()
        if not search_query: return results

        search_categories = categories if categories is not None else self.categories

        for category in search_categories:
            category_path = self.root_dir / category
            if not category_path.is_dir(): continue

            for file_path in category_path.glob("*.md"):
                try:
                    # Read metadata first for title
                    entry_data = self.get_entry_by_path(file_path, read_content=False)
                    title = file_path.stem
                    if entry_data and entry_data.get("metadata") and entry_data["metadata"].get("title"):
                        title = entry_data["metadata"]["title"]

                    title_match = search_query in title.lower()
                    content_match = False

                    if not title_match:
                        # Read content only if title didn't match
                        entry_data_full = self.get_entry_by_path(file_path, read_content=True)
                        content = entry_data_full.get("content", "") if entry_data_full else ""
                        content_match = search_query in content.lower()

                    if title_match or content_match:
                        results.append({
                            "category": category,
                            "title": title,
                            "path": str(file_path)
                        })
                except Exception as e:
                    print(f"Error processing file {file_path} during search: {e}")
                    continue

        results.sort(key=lambda x: (x["category"].lower(), x["title"].lower()))
        return results

    def get_entry_by_path(self, file_path_str, read_content=True):
        """Get entry data (metadata and optionally content) from a file path."""
        path = Path(file_path_str)
        if not path.exists() or not path.is_file():
            return None

        try:
            full_content = path.read_text(encoding="utf-8")
        except Exception as e:
            print(f"Error reading file {path}: {e}")
            return None

        metadata = {"title": path.stem}  # Default title from filename
        content_text = full_content

        if full_content.startswith("---"):
            match = re.match(r"^---\s*?\n(.*?)\n^---\s*?\n?(.*)", full_content, re.MULTILINE | re.DOTALL)
            if match:
                metadata_str = match.group(1).strip()
                content_text = match.group(2).strip()
                try:
                    loaded_meta = json.loads(metadata_str)
                    if isinstance(loaded_meta, dict):
                        # Use metadata title, fallback to filename stem if missing/empty
                        if not loaded_meta.get("title"):
                            loaded_meta["title"] = path.stem
                        metadata = loaded_meta
                    else:
                        print(f"Warning: Metadata in {path} is not a JSON object.")
                except json.JSONDecodeError as json_e:
                    print(f"Warning: Invalid JSON metadata in {path}: {json_e}")
            else:
                print(f"Warning: Malformed metadata block in {path}.")

        entry_data = {
            "metadata": metadata,
            "path": str(path)
        }
        if read_content:
            entry_data["content"] = content_text

        return entry_data

    def list_entries(self, category):
        """List titles and paths of entries in a category, sorted."""
        entries = []
        category_path = self.root_dir / category
        if not category_path.is_dir(): return entries

        for file_path in category_path.glob("*.md"):
            entry_data = self.get_entry_by_path(file_path, read_content=False)
            title = file_path.stem
            if entry_data and entry_data.get("metadata") and entry_data["metadata"].get("title"):
                title = entry_data["metadata"]["title"]
            entries.append({"title": title, "path": str(file_path)})

        entries.sort(key=lambda x: x["title"].lower())  # Sort case-insensitively
        return entries

    def add_category(self, new_category):
        """Add a new category directory and update the list."""
        clean_category = new_category.strip()
        if not clean_category: raise ValueError("分类名称不能为空。")
        if clean_category == "_trash": raise ValueError("分类名称 '_trash' 是保留名称。")
        if re.search(r'[<>:"/\\|?*]', clean_category) or any(ord(c) < 32 for c in clean_category):
            raise ValueError(f"分类名称 '{clean_category}' 包含无效字符。")

        category_path = self.root_dir / clean_category
        if clean_category not in self.categories:
            try:
                category_path.mkdir(exist_ok=True)
                self.categories.append(clean_category)
                self.categories.sort(key=lambda x: x.lower())
                return True
            except OSError as e:
                raise OSError(f"无法创建分类目录 '{clean_category}': {e}")
        else:
            # Category in list, ensure directory exists
            category_path.mkdir(exist_ok=True)
            return False  # Indicate it already existed

    def remove_category(self, category):
        """Move a category directory and its contents to the trash."""
        if category not in self.categories:
            raise ValueError(f"分类 '{category}' 不存在。")

        category_path = self.root_dir / category
        if category_path.is_dir():
            try:
                target_trash_path = self.trash_dir / category_path.name
                counter = 0
                while target_trash_path.exists():
                    counter += 1
                    target_trash_path = self.trash_dir / f"{category_path.name}_{counter}"

                shutil.move(str(category_path), str(target_trash_path))
                self.categories.remove(category)  # Update internal list
                print(f"Moved category to trash: {target_trash_path}")
                return True
            except Exception as e:
                raise OSError(f"无法移动分类 '{category_path}' 到回收站: {e}")
        else:
            # Directory missing, but in list? Remove from list.
            print(f"Warning: Category '{category}' in list but directory missing. Removing from list.")
            self.categories.remove(category)
            return True

    def rename_category(self, current_name, new_name):
        """Rename a category directory and update the list."""
        clean_new_name = new_name.strip()
        if not clean_new_name: raise ValueError("新分类名称不能为空。")
        if clean_new_name == current_name: return True  # No change
        if clean_new_name == "_trash": raise ValueError("新分类名称 '_trash' 是保留名称。")
        if clean_new_name in self.categories: raise ValueError(f"目标分类名称 '{clean_new_name}' 已存在。")
        if re.search(r'[<>:"/\\|?*]', clean_new_name) or any(ord(c) < 32 for c in clean_new_name):
            raise ValueError(f"新分类名称 '{clean_new_name}' 包含无效字符。")
        if current_name not in self.categories: raise ValueError(f"源分类 '{current_name}' 不存在。")

        old_path = self.root_dir / current_name
        new_path = self.root_dir / clean_new_name

        if not old_path.is_dir():
            # Dir missing, just rename in list
            print(f"Warning: Directory '{current_name}' not found. Renaming in list only.")
            self.categories[self.categories.index(current_name)] = clean_new_name
            self.categories.sort(key=lambda x: x.lower())
            return True

        if new_path.exists():
            # This check is important even if clean_new_name not in self.categories initially
            # A directory might exist physically without being in the list if created externally
            raise FileExistsError(f"目标分类目录 '{clean_new_name}' 已物理存在。")

        try:
            shutil.move(str(old_path), str(new_path))
            self.categories[self.categories.index(current_name)] = clean_new_name
            self.categories.sort(key=lambda x: x.lower())
            return True
        except Exception as e:
            raise OSError(f"无法重命名分类 '{current_name}' 为 '{clean_new_name}': {e}")

    # --- Trash Management Methods ---

    def list_trash(self):
        """List all items directly inside the trash directory."""
        if not self.trash_dir.exists(): return []
        # Filter out common system hidden files
        return sorted([p for p in self.trash_dir.iterdir() if not p.name.startswith('.')],
                      key=lambda p: p.name)

    def restore_trash_item(self, trash_path_str):
        """Restore a single item from the trash."""
        trash_path = Path(trash_path_str)
        if not trash_path.exists() or self.trash_dir not in trash_path.parents:
            raise FileNotFoundError(f"回收站项目不存在或路径无效: {trash_path}")

        target_path = None

        # Handle .md files (restore to original category if possible)
        if trash_path.is_file() and trash_path.suffix == ".md":
            entry_data = self.get_entry_by_path(trash_path, read_content=False)
            original_category = entry_data.get("metadata", {}).get("_original_category") if entry_data else None

            target_category_path = self.root_dir  # Default to root
            if original_category and original_category != "_trash":
                target_category_path = self.root_dir / original_category
                if not target_category_path.exists():
                    print(f"Info: Creating missing category '{original_category}' during restore.")
                    try:
                        self.add_category(original_category)  # Creates dir and adds to list
                    except Exception as e:
                        print(f"Warning: Failed to recreate category '{original_category}': {e}. Restoring to root.")
                        target_category_path = self.root_dir
                elif original_category not in self.categories:
                    # Add to list if dir exists but wasn't listed
                    self.categories.append(original_category)
                    self.categories.sort(key=lambda x: x.lower())
            else:
                print(f"Warning: Original category not found for {trash_path.name}. Restoring to root.")

            # Try to reconstruct original filename
            original_filename_match = re.match(r"^\d{8}_\d{6}(?:_\d+)?_(.*)", trash_path.name)
            base_filename = original_filename_match.group(1) if original_filename_match else trash_path.name
            target_path = target_category_path / base_filename

        # Handle directories (restore to root)
        elif trash_path.is_dir():
            category_name = re.sub(r'_\d+$', '', trash_path.name)  # Remove potential _1, _2 suffix
            target_path = self.root_dir / category_name

            # Add category back to list if necessary (use cleaned name)
            if category_name not in self.categories:
                # Check if dir exists physically before adding to list
                if not (self.root_dir / category_name).exists():
                    self.categories.append(category_name)
                    self.categories.sort(key=lambda x: x.lower())
                else:
                    print(f"Info: Directory '{category_name}' already exists, not adding duplicate to list.")

        else:  # Unsupported item type? Restore to root.
            print(f"Warning: Unsupported item type in trash: {trash_path.name}. Restoring to root.")
            target_path = self.root_dir / trash_path.name

        # Handle name collisions at target location
        if target_path:
            counter = 0
            original_target_path = target_path
            while target_path.exists():
                counter += 1
                stem = original_target_path.stem
                suffix = original_target_path.suffix
                if original_target_path.is_dir(): suffix = ""  # No suffix for dirs
                target_path = original_target_path.parent / f"{stem}_{counter}{suffix}"

            try:
                shutil.move(str(trash_path), str(target_path))
                print(f"Restored '{trash_path.name}' to '{target_path}'")
                if target_path.is_file() and target_path.suffix == ".md":
                    self._cleanup_restored_metadata(target_path)
                return str(target_path)
            except Exception as e:
                raise OSError(f"无法恢复项目 '{trash_path.name}' 到 '{target_path}': {e}")
        else:
            raise ValueError(f"无法确定 '{trash_path.name}' 的恢复位置。")

    def _cleanup_restored_metadata(self, file_path):
        """Remove internal trash metadata keys from a restored file."""
        try:
            entry_data = self.get_entry_by_path(file_path, read_content=True)
            if entry_data and isinstance(entry_data.get("metadata"), dict):
                metadata = entry_data["metadata"]
                metadata.pop("_original_category", None)
                metadata.pop("_deleted_at", None)
                content = entry_data.get("content", "")
                # Re-save the file
                file_content = f"---\n{json.dumps(metadata, ensure_ascii=False, indent=2)}\n---\n\n{content}"
                file_path.write_text(file_content, encoding="utf-8")
            elif entry_data:
                print(f"Info: No valid metadata dict found in {file_path} during cleanup.")
        except Exception as e:
            print(f"Warning: Could not clean metadata in restored file {file_path}: {e}")

    def permanently_delete_trash_item(self, trash_path_str):
        """Permanently delete a single item from the trash."""
        trash_path = Path(trash_path_str)
        if not trash_path.exists() or self.trash_dir not in trash_path.parents:
            raise FileNotFoundError(f"回收站项目不存在或路径无效: {trash_path}")
        try:
            if trash_path.is_file():
                trash_path.unlink()
                print(f"Permanently deleted file: {trash_path}")
            elif trash_path.is_dir():
                shutil.rmtree(trash_path)
                print(f"Permanently deleted directory: {trash_path}")
            else:  # Symlinks, other types
                trash_path.unlink()
                print(f"Permanently deleted item: {trash_path}")
            return True
        except Exception as e:
            raise OSError(f"无法永久删除回收站项目 '{trash_path.name}': {e}")

    def empty_trash(self):
        """Permanently delete all items in the trash directory."""
        deleted_count = 0
        errors = []
        trash_items = self.list_trash()
        if not trash_items: return 0, []

        for item_path in trash_items:
            try:
                self.permanently_delete_trash_item(str(item_path))
                deleted_count += 1
            except Exception as e:
                errors.append(f"无法删除 '{item_path.name}': {e}")

        print(f"Emptied trash. {deleted_count}/{len(trash_items)} items deleted.")
        if errors: print("Errors:", errors)
        return deleted_count, errors


# --- Frontend GUI (NovelManagerGUI) ---
class NovelManagerGUI:
    def __init__(self, root, manager):
        self.root = root
        self.root.title("网文创作助手 V3.2 (界面修复)")
        self.root.geometry("1300x850")

        self.manager = manager
        self.font_manager = FontManager()  # 创建字体管理器实例
        self.current_font = self.font_manager.current_font  # 当前字体
        self.font_size = 15  # 默认字体大小

        # --- Theme and Color Setup ---
        self.current_theme_mode = "system"
        self._apply_initial_theme_settings()  # Sets initial theme and root BG

        # --- State Variables ---
        self.current_category = None
        self.current_entry_path = None
        self.entry_data_map = {}
        self.is_search_active = False

        # --- Initialize Context Menus ---
        self.category_menu = Menu(self.root, tearoff=0)
        self.entry_menu = Menu(self.root, tearoff=0)

        # --- UI Creation ---
        self._setup_style()  # Configure ttk styles if needed
        # 移除 self._create_menu() 调用
        self._create_ui()  # Create main widgets

        # --- Initial Data Load ---
        self.load_categories()  # Load categories into listbox

        # Apply theme again after all widgets are created
        self._apply_theme()  # Ensure Listboxes etc. get themed

        # 在初始化结束时添加UI美化
        self._apply_ui_enhancements()

        # 确保立即应用颜色到列表框
        if hasattr(self, 'category_listbox'):
            self._beautify_listbox(self.category_listbox)
        if hasattr(self, 'entry_listbox'):
            self._beautify_listbox(self.entry_listbox)

        # 设置一个短暂延迟确保样式应用完成
        self.root.after(100, self._ensure_listbox_styling)

        # 确保在切换标签、点击列表等操作后重新应用样式
        self.root.bind_all("<FocusIn>", self._delayed_style_refresh)
        self.root.bind_all("<ButtonRelease-1>", self._delayed_style_refresh)

    def _delayed_style_refresh(self, event=None):
        """当焦点或鼠标点击发生变化时延迟刷新样式"""
        self.root.after(50, self._ensure_listbox_styling)

    def _apply_initial_theme_settings(self):
        """Sets the initial theme based on detection or default."""
        if HAS_CTK:
            try:
                # Use darkdetect if available, otherwise use CTk's system setting
                import darkdetect
                detected_mode = "dark" if darkdetect.isDark() else "light"
                ctk.set_appearance_mode(detected_mode)
                self.current_theme_mode = detected_mode.lower()
                print(f"Detected system theme: {self.current_theme_mode}")
            except ImportError:
                print("darkdetect not found, using CTk system detection.")
                ctk.set_appearance_mode("System")
                # Get the *actual* mode CTk resolved to
                self.current_theme_mode = ctk.get_appearance_mode().lower()
                print(f"Set theme to System, effective mode: {self.current_theme_mode}")

            ctk.set_default_color_theme("blue")
            self._update_root_background()

        elif HAS_SVTTK:
            try:
                # Try to detect mode for sv-ttk as well
                import darkdetect
                detected_mode = "dark" if darkdetect.isDark() else "light"
                sv_ttk.set_theme(detected_mode)
                self.current_theme_mode = detected_mode.lower()
                print(f"Detected system theme for sv-ttk: {self.current_theme_mode}")
            except ImportError:
                print("darkdetect not found, defaulting sv-ttk to light.")
                sv_ttk.set_theme("light")
                self.current_theme_mode = "light"
            except Exception as e:
                print(f"Warning: Failed to set initial sv-ttk theme: {e}")
                self.current_theme_mode = "light"  # Fallback
            self._update_root_background()
        else:
            # Default Tkinter theme
            self.current_theme_mode = "light"  # Assume light for default tk
            self._update_root_background()

        # 在最后添加，确保在任何主题引擎下都能正确初始化
        # 预先定义软色调颜色方案，供后续使用
        self.soft_colors = {
            "light": {
                "list_bg": "#f8f8f8",  # 非常浅的灰色（列表背景）
                "list_select_bg": "#e9eef2",  # 非常浅的蓝灰色（选中背景）
                "list_select_fg": "#333333",  # 深灰色文本（选中文本）
                "button_blue": "#a7c5eb",  # 柔和的淡蓝色（主按钮）
                "button_blue_hover": "#89b0e0",  # 稍深的淡蓝（hover）
                "button_red": "#f0b6bc",  # 柔和的淡红色（删除按钮）
                "button_red_hover": "#e6a0a7",  # 稍深的淡红（hover）
                "button_green": "#b7e0c4",  # 柔和的淡绿色（保存按钮）
                "button_green_hover": "#a0d3b0"  # 稍深的淡绿（hover）
            },
            "dark": {
                "list_bg": "#2a2a2a",  # 暗灰色（列表背景）
                "list_select_bg": "#3f4e5d",  # 暗蓝灰色（选中背景）
                "list_select_fg": "#ffffff",  # 白色文本（选中文本）
                "button_blue": "#4a6f8a",  # 暗模式下的柔和蓝（主按钮）
                "button_blue_hover": "#5a819b",  # 稍亮的蓝（hover）
                "button_red": "#8b4e52",  # 暗模式下的柔和红（删除按钮）
                "button_red_hover": "#9b5e62",  # 稍亮的红（hover）
                "button_green": "#4d7359",  # 暗模式下的柔和绿（保存按钮）
                "button_green_hover": "#5d8369"  # 稍亮的绿（hover）
            }
        }

    def _update_root_background(self):
        """Updates the root window background based on the current theme."""
        root_bg = 'SystemButtonFace'  # Default fallback
        try:
            if HAS_CTK:
                bg_color_tuple = ctk.ThemeManager.theme["CTkFrame"]["fg_color"]
                mode_index = 0 if self.current_theme_mode == 'light' else 1
                root_bg = bg_color_tuple[mode_index] if isinstance(bg_color_tuple, (list, tuple)) else bg_color_tuple
            elif HAS_SVTTK:
                style = ttk.Style()
                root_bg = style.lookup('.', 'background')  # Get theme background
            # else: use default SystemButtonFace

            self.root.configure(bg=root_bg)
            # print(f"Set root background to: {root_bg} for mode {self.current_theme_mode}")
        except Exception as e:
            print(f"Warning: Failed to set root background: {e}")

    def _setup_style(self):
        """Configure styles (mostly for ttk components)."""
        if not HAS_CTK:  # Only needed if not using CustomTkinter primarily
            style = ttk.Style()
            try:
                # Try setting PanedWindow background - might not work reliably on all themes/OS
                pane_bg = style.lookup('.', 'background')  # Get theme background
                style.configure("TPanedwindow", background=pane_bg, borderwidth=0, sashpad=1)
                # Sash styling might also be limited
                style.configure("TPanedwindow.Sash", gripcount=0, sashthickness=6, relief=tk.FLAT, background=pane_bg)
                print("Attempted TPanedwindow style configuration.")
            except Exception as e:
                print(f"Warning: Error configuring TPanedwindow style: {e}")

    def _apply_theme(self):
        """Apply current theme settings to widgets, especially non-CTk ones."""
        self._update_root_background()  # Ensure root background is current
        self._apply_menu_colors()  # Apply colors to the menu bar <<< Added call

        # Update Listbox colors (if using tk.Listbox with CTk)
        if HAS_CTK:
            try:
                current_mode = self.current_theme_mode
                mode_index = 0 if current_mode == 'light' else 1

                listbox_bg = ctk.ThemeManager.theme["CTkTextbox"]["fg_color"][mode_index]
                listbox_fg = ctk.ThemeManager.theme["CTkLabel"]["text_color"][mode_index]
                select_bg = ctk.ThemeManager.theme["CTkButton"]["fg_color"][mode_index]
                select_fg = ctk.ThemeManager.theme["CTkButton"]["text_color"][mode_index]
                border_color = ctk.ThemeManager.theme["CTkFrame"]["border_color"][mode_index]
                highlight_color = select_bg

                # Apply to category listbox
                listbox = getattr(self, 'category_listbox', None)
                if listbox and listbox.winfo_exists():
                    listbox.config(bg=listbox_bg, fg=listbox_fg, selectbackground=select_bg,
                                   selectforeground=select_fg, highlightthickness=1,
                                   highlightbackground=border_color, highlightcolor=highlight_color)
                # Apply to entry listbox
                listbox = getattr(self, 'entry_listbox', None)
                if listbox and listbox.winfo_exists():
                    listbox.config(bg=listbox_bg, fg=listbox_fg, selectbackground=select_bg,
                                   selectforeground=select_fg, highlightthickness=1,
                                   highlightbackground=border_color, highlightcolor=highlight_color)
                # print("Updated Listbox colors for CTk theme.")
            except Exception as e:
                print(f"Warning: Failed to update Listbox colors for CTk: {e}")

        self.root.update_idletasks()

    # --- >> Function to apply colors to tk.Menu << ---
    def _apply_menu_colors(self):
        """应用当前主题颜色到菜单"""
        if not HAS_CTK:
            return  # 非CTk模式无需特殊处理

        try:
            # 获取当前主题和模式
            current_mode = ctk.get_appearance_mode().lower()
            mode_index = 0 if current_mode == 'light' else 1

            # 获取各种颜色
            fg_color = ctk.ThemeManager.theme["CTkFrame"]["fg_color"][mode_index]
            text_color = ctk.ThemeManager.theme["CTkLabel"]["text_color"][mode_index]
            hover_color = ctk.ThemeManager.theme["CTkButton"]["hover_color"][mode_index]

            # 应用到所有菜单
            for menu_name in ('category_menu', 'entry_menu'):
                menu = getattr(self, menu_name, None)
                if menu:
                    try:
                        menu.configure(
                            bg=fg_color,
                            fg=text_color,
                            activebackground=hover_color,
                            activeforeground=text_color,
                            # 移除可能导致问题的配置项
                            # disabledforeground=text_color_disabled
                        )
                    except tk.TclError as e:
                        print(f"菜单 {menu_name} 颜色应用错误: {e}")
        except Exception as e:
            print(f"应用菜单颜色时出错: {e}")

    def _create_ui(self):
        """Create the main UI layout using PanedWindow."""
        pane_style = "TPanedwindow" if not HAS_CTK else ""  # Use default style with CTk

        self.main_h_pane = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL, style=pane_style)
        self.main_h_pane.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.frame_left = self._create_left_pane(self.main_h_pane)
        self.main_h_pane.add(self.frame_left, weight=1)

        self.right_h_pane = ttk.PanedWindow(self.main_h_pane, orient=tk.HORIZONTAL, style=pane_style)
        self.main_h_pane.add(self.right_h_pane, weight=4)

        self.frame_middle = self._create_middle_pane(self.right_h_pane)
        self.right_h_pane.add(self.frame_middle, weight=2)

        self.frame_right = self._create_right_pane(self.right_h_pane)
        self.right_h_pane.add(self.frame_right, weight=3)

    # --- >> Updated _create_menu with self assignments << ---
    def _create_menu(self):
        """Create the application menu bar."""
        self.menubar = Menu(self.root)  # <<< Assign to self.menubar
        self.root.config(menu=self.menubar)

        # --- File Menu ---
        self.file_menu = Menu(self.menubar, tearoff=0)  # <<< Assign to self.file_menu
        self.menubar.add_cascade(label="文件", menu=self.file_menu)
        self.file_menu.add_command(label="新建分类...", command=self.on_new_category)
        self.file_menu.add_command(label="新建条目", command=self.on_new_entry)
        self.file_menu.add_command(label="刷新文件系统", command=self.on_refresh)
        self.file_menu.add_separator()
        # --- Trash Submenu ---
        self.trash_menu = Menu(self.file_menu, tearoff=0)  # <<< Assign to self.trash_menu
        self.file_menu.add_cascade(label="回收站", menu=self.trash_menu)
        self.trash_menu.add_command(label="查看回收站...", command=self.on_view_trash)
        self.trash_menu.add_command(label="清空回收站...", command=self.on_empty_trash)
        self.file_menu.add_separator()
        self.file_menu.add_command(label="退出", command=self.root.quit)

        # --- View Menu ---
        self.view_menu = Menu(self.menubar, tearoff=0)  # <<< Assign to self.view_menu
        self.menubar.add_cascade(label="视图", menu=self.view_menu)
        self.theme_menu = Menu(self.view_menu, tearoff=0)  # <<< Assign to self.theme_menu
        self.view_menu.add_cascade(label="主题", menu=self.theme_menu)
        if HAS_CTK:
            self.theme_menu.add_command(label="亮色", command=lambda: self.switch_theme("light"))
            self.theme_menu.add_command(label="暗色", command=lambda: self.switch_theme("dark"))
            self.theme_menu.add_command(label="跟随系统", command=lambda: self.switch_theme("system"))
        elif HAS_SVTTK:
            self.theme_menu.add_command(label="亮色", command=lambda: self.switch_theme("light"))
            self.theme_menu.add_command(label="暗色", command=lambda: self.switch_theme("dark"))
        else:
            self.theme_menu.add_command(label="默认", command=None, state=tk.DISABLED)

        # Apply initial menu colors AFTER all menus are created and assigned
        self._apply_menu_colors()

    # --- Data Loading and UI Update ---
    # (load_categories, load_entries, load_search_results, clear_editor, _update_info_label, _select_listbox_item_by_text - unchanged)
    def load_categories(self):
        """Load/reload categories into the listbox."""
        selected_category = self.current_category
        try:
            self.manager.categories = self.manager._load_categories()
        except Exception as e:
            messagebox.showerror("错误", f"加载分类列表时出错: {e}", parent=self.root)
            self.manager.categories = []

        selected_idx = None
        listbox = getattr(self, 'category_listbox', None)
        if listbox and listbox.winfo_exists() and selected_category:
            try:
                items = list(listbox.get(0, tk.END))
                if selected_category in items:
                    selected_idx = items.index(selected_category)
            except (ValueError, tk.TclError):
                selected_idx = None

        if listbox and listbox.winfo_exists():
            listbox.delete(0, tk.END)
            for category in self.manager.categories:
                listbox.insert(tk.END, category)

            restored = False
            if selected_category and selected_category in self.manager.categories:
                if self._select_listbox_item_by_text(listbox, selected_category):
                    self.current_category = selected_category  # Keep state consistent
                    restored = True
            elif selected_idx is not None and selected_idx < listbox.size():
                try:
                    listbox.selection_set(selected_idx)
                    listbox.activate(selected_idx)
                    self.current_category = listbox.get(selected_idx)
                    restored = True
                except tk.TclError:
                    pass

            if not restored:
                # If nothing restored, select first category if available
                if self.manager.categories:
                    first_cat = self.manager.categories[0]
                    if self._select_listbox_item_by_text(listbox, first_cat):
                        self.current_category = first_cat
                        self.load_entries(self.current_category)  # Load entries for auto-selected cat
                    else:  # Fallback: clear everything
                        self.current_category = None
                        self.load_entries(None);
                        self.clear_editor()
                else:  # No categories exist
                    self.current_category = None
                    self.load_entries(None);
                    self.clear_editor()
            # Ensure theme is applied after loading items
            self._apply_theme()

        # 加载完成后立即应用颜色
        self._beautify_listbox(self.category_listbox)

        # 如果已有条目列表，也美化它
        if hasattr(self, 'entry_listbox') and self.entry_listbox.winfo_exists():
            self._beautify_listbox(self.entry_listbox)

        return True

    def load_entries(self, category):
        """Load entries for the selected category."""
        listbox = getattr(self, 'entry_listbox', None)
        list_label = getattr(self, 'entry_list_label', None)
        if not listbox or not listbox.winfo_exists(): return

        listbox.delete(0, tk.END)
        self.entry_data_map.clear()
        self.is_search_active = False

        listbox_state_tk = tk.DISABLED  # For tk.Listbox enabling/disabling visual cues
        list_label_text = "条目列表"

        if category and category in self.manager.categories:
            try:
                entries = self.manager.list_entries(category)
                if entries:
                    listbox_state_tk = tk.NORMAL
                    for entry in entries:
                        listbox.insert(tk.END, entry["title"])
                        self.entry_data_map[entry["title"]] = entry["path"]
                else:
                    listbox.insert(tk.END, "(无条目)")
                self.clear_editor()  # Clear editor when category changes
            except Exception as e:
                messagebox.showerror("错误", f"加载分类 '{category}' 条目出错: {e}", parent=self.root)
                listbox.insert(tk.END, "(加载错误)")
                self.clear_editor()
        else:
            listbox.insert(tk.END, "(请先选择分类)")
            self.clear_editor()

        # Update label and Listbox state/appearance
        if list_label:
            try:
                list_label.configure(text=list_label_text)  # CTk way
            except:
                list_label.config(text=list_label_text)  # ttk way

        if not HAS_CTK:  # Only configure state for non-CTk listbox
            listbox.config(state=listbox_state_tk)

        # Re-apply theme to ensure listbox colors are correct after update
        self._apply_theme()

        # 在方法末尾添加，确保列表项加载后应用颜色
        self._beautify_listbox(self.entry_listbox)

    def load_search_results(self, results):
        """Load search results into the entry listbox."""
        listbox = getattr(self, 'entry_listbox', None)
        list_label = getattr(self, 'entry_list_label', None)
        if not listbox or not listbox.winfo_exists(): return

        listbox.delete(0, tk.END)
        self.entry_data_map.clear()
        self.is_search_active = True

        listbox_state_tk = tk.DISABLED
        list_label_text = "搜索结果"

        if results:
            listbox_state_tk = tk.NORMAL
            for result in results:
                display_text = f"[{result['category']}] {result['title']}"
                listbox.insert(tk.END, display_text)
                self.entry_data_map[display_text] = result['path']
        else:
            listbox.insert(tk.END, "无匹配结果")

        self.clear_editor()  # Clear editor when showing results

        if list_label:
            try:
                list_label.configure(text=list_label_text)
            except:
                list_label.config(text=list_label_text)

        if not HAS_CTK:
            listbox.config(state=listbox_state_tk)

        self._apply_theme()

    def clear_editor(self, keep_selection=False):
        """Clear editor fields and reset state."""
        self.title_var.set("")
        self.tags_var.set("")

        content_widget = getattr(self, 'content_text', None)
        if content_widget and content_widget.winfo_exists():
            # Use appropriate method for CTkTextbox or tk.Text
            start_index = "0.0" if isinstance(content_widget, ctk.CTkTextbox) else 1.0
            end_index = tk.END
            try:
                content_widget.delete(start_index, end_index)
            except tk.TclError as e:
                print(f"Debug: Error clearing content widget: {e}")

            # Reset undo stack (only for tk.Text)
            if isinstance(content_widget, tk.Text):
                try:
                    content_widget.edit_reset()
                except tk.TclError:
                    pass

        self.info_label_var.set("未加载条目")
        self.current_entry_path = None

        if not keep_selection:
            entry_listbox = getattr(self, 'entry_listbox', None)
            if entry_listbox and entry_listbox.winfo_exists():
                try:
                    entry_listbox.selection_clear(0, tk.END)
                except tk.TclError:
                    pass

    def _update_info_label(self, metadata):
        """Update info label with formatted dates."""
        created = metadata.get("created_at", "N/A")
        updated = metadata.get("updated_at", "N/A")
        created_str, updated_str = created, updated
        try:
            if isinstance(created, str) and len(created) > 18:
                if created.endswith('Z'): created = created[:-1] + '+00:00'
                # Handle potential fractional seconds before parsing
                created_dt = datetime.datetime.fromisoformat(created.split('.')[0])
                created_str = created_dt.strftime("%Y-%m-%d %H:%M")
            if isinstance(updated, str) and len(updated) > 18:
                if updated.endswith('Z'): updated = updated[:-1] + '+00:00'
                updated_dt = datetime.datetime.fromisoformat(updated.split('.')[0])
                updated_str = updated_dt.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            # Handle cases where fromisoformat fails on the string
            print(f"Debug: Could not parse date: created='{created}', updated='{updated}'")
        except Exception as e:
            print(f"Debug: Error parsing date for info label: {e}")

        self.info_label_var.set(f"创建: {created_str} | 更新: {updated_str}")

    def _select_listbox_item_by_text(self, listbox, text_to_find, select=True):
        """Find and optionally select a listbox item by exact text."""
        if not listbox or not listbox.winfo_exists(): return False
        listbox.update_idletasks()  # Ensure list is updated
        try:
            items = listbox.get(0, tk.END)
            idx = items.index(text_to_find)
            if select:
                listbox.selection_clear(0, tk.END)
                listbox.selection_set(idx)
                listbox.activate(idx)
            listbox.see(idx)
            return True
        except ValueError:  # Item not in list
            return False
        except tk.TclError:  # Widget might be destroyed
            return False

    # --- Event Handlers ---
    # (on_category_select, on_entry_select, on_new_category, on_rename_category, on_delete_selected_category, on_new_entry, on_edit_selected_entry, on_save, on_delete_selected_entries, on_move_selected_entries, on_rename_entry, on_search, on_clear_search, on_view_trash, on_empty_trash - unchanged)
    def on_category_select(self, event=None):
        """Handle category selection."""
        listbox = event.widget if event and hasattr(event, 'widget') else getattr(self, 'category_listbox', None)
        if not listbox or not listbox.winfo_exists(): return

        try:
            selection = listbox.curselection()
            if selection:
                index = int(selection[0])
                selected = listbox.get(index)
                print(f"Category selected: {selected}")

                old_category = self.current_category
                self.current_category = selected

                if old_category != self.current_category:
                    self.load_entries(self.current_category)
            else:
                # If selection is cleared, keep last category
                pass
        except Exception as e:
            messagebox.showerror("错误", f"选择分类时出错: {e}", parent=self.root)

        # 确保在选择后重新应用深色样式
        self.root.after(10, lambda: self._beautify_listbox(listbox))

    def on_entry_select(self, event=None):
        """Handle entry selection."""
        listbox = event.widget if event and hasattr(event, 'widget') else getattr(self, 'entry_listbox', None)
        if not listbox or not listbox.winfo_exists(): return

        try:
            selection = listbox.curselection()
            if selection:
                index = int(selection[0])
                selected_entry = listbox.get(index)

                if selected_entry and not selected_entry.startswith("("):
                    path = self.entry_data_map.get(selected_entry)
                    if path and path != self.current_entry_path:
                        print(f"Entry selected: {selected_entry}")
                        self.current_entry_path = path

                        try:
                            entry_data = self.manager.get_entry_by_path(path)
                            if entry_data:
                                # Update editor
                                editor = getattr(self, 'content_text', None)
                                if editor:
                                    self.clear_editor(keep_selection=True)
                                    if isinstance(editor, ctk.CTkTextbox):
                                        editor.insert("1.0", entry_data.get("content", ""))
                                    else:
                                        editor.insert(tk.END, entry_data.get("content", ""))

                                # Update tags/title
                                title_var = getattr(self, 'title_var', None)
                                tags_var = getattr(self, 'tags_var', None)
                                metadata = entry_data.get("metadata", {})

                                if title_var:
                                    title_var.set(metadata.get("title", ""))
                                if tags_var:
                                    tags_var.set(", ".join(metadata.get("tags", [])))

                                # Update info
                                self._update_info_label(metadata)
                        except Exception as e:
                            messagebox.showerror("读取错误", f"读取条目时发生错误: {e}", parent=self.root)
            else:
                # Selection cleared
                pass
        except Exception as e:
            print(f"Error in entry selection: {e}")

        # 确保在选择后重新应用深色样式
        self.root.after(10, lambda: self._beautify_listbox(listbox))

    def on_new_category(self):
        """Create a new category via dialog."""
        dialog_title = "新建分类"
        dialog_text = "请输入新分类名称:"
        new_category = None
        if HAS_CTK:
            dialog = ctk.CTkInputDialog(text=dialog_text, title=dialog_title)
            # Center the dialog over the parent window
            # dialog.geometry(f"+{self.root.winfo_rootx()+self.root.winfo_width()//2-dialog.winfo_reqwidth()//2}+{self.root.winfo_rooty()+self.root.winfo_height()//2-dialog.winfo_reqheight()//2}")
            new_category = dialog.get_input()
        else:
            new_category = simpledialog.askstring(dialog_title, dialog_text, parent=self.root)

        if new_category:
            try:
                clean_name = new_category.strip()
                added = self.manager.add_category(clean_name)
                if added:
                    print(f"Category '{clean_name}' added.")
                    self.load_categories()
                    self._select_listbox_item_by_text(self.category_listbox, clean_name)
                else:
                    messagebox.showinfo("信息", f"分类 '{clean_name}' 已存在。", parent=self.root)
                    self._select_listbox_item_by_text(self.category_listbox, clean_name)
                    if self.current_category != clean_name: self.on_category_select(None)  # Trigger load if needed
            except (ValueError, OSError) as e:
                messagebox.showerror("创建错误", f"无法创建分类:\n{str(e)}", parent=self.root)

    def on_rename_category(self):
        """Rename selected category via dialog."""
        listbox = getattr(self, 'category_listbox', None)
        if not listbox or not listbox.curselection():
            messagebox.showwarning("选择分类", "请先在列表中选择一个要重命名的分类。", parent=self.root)
            return

        try:
            selected_index = listbox.curselection()[0]
            current_name = listbox.get(selected_index)
        except (tk.TclError, IndexError):
            messagebox.showerror("错误", "无法获取选中的分类名称。", parent=self.root)
            return

        dialog_title = "重命名分类"
        dialog_text = f"请输入 '{current_name}' 的新名称:"
        new_name = None
        if HAS_CTK:
            dialog = ctk.CTkInputDialog(text=dialog_text, title=dialog_title)
            # Pre-fill the entry
            if hasattr(dialog, '_entry') and dialog._entry: dialog._entry.insert(0, current_name)
            new_name = dialog.get_input()
        else:
            new_name = simpledialog.askstring(dialog_title, dialog_text, initialvalue=current_name, parent=self.root)

        if new_name and new_name.strip() != current_name:
            clean_new_name = new_name.strip()
            try:
                renamed = self.manager.rename_category(current_name, clean_new_name)
                if renamed:
                    print(f"Category '{current_name}' renamed to '{clean_new_name}'.")
                    path_before = self.current_entry_path
                    # Update state var if renamed category was selected
                    if self.current_category == current_name: self.current_category = clean_new_name
                    self.load_categories()  # Reload list, tries to reselect self.current_category
                    self._select_listbox_item_by_text(self.category_listbox,
                                                      clean_new_name)  # Ensure selection visually

                    # Update editor path if the open entry was in the renamed category
                    if path_before:
                        old_path = Path(path_before)
                        # Ensure parent exists before checking name
                        if old_path.parent and old_path.parent.exists() and old_path.parent.name == current_name:
                            self.current_entry_path = str(self.manager.root_dir / clean_new_name / old_path.name)
                            print(f"Updated current entry path: {self.current_entry_path}")
            except (ValueError, OSError, FileExistsError) as e:
                messagebox.showerror("重命名错误", f"无法重命名分类:\n{str(e)}", parent=self.root)

    def on_delete_selected_category(self):
        """Move selected category to trash after confirmation."""
        listbox = getattr(self, 'category_listbox', None)
        if not listbox or not listbox.curselection():
            messagebox.showwarning("选择分类", "请先在左侧列表中选择一个要删除的分类。", parent=self.root)
            return
        try:
            selected_index = listbox.curselection()[0]
            selected_category = listbox.get(selected_index)
            if selected_category.startswith("("):  # Don't delete placeholders
                messagebox.showwarning("无效操作", "不能删除占位符项目。", parent=self.root)
                return
        except (tk.TclError, IndexError):
            messagebox.showerror("错误", "无法获取选中的分类。", parent=self.root)
            return

        if messagebox.askyesno("确认移至回收站",
                               f"确定要将分类 '{selected_category}' 及其所有内容移动到回收站吗？\n此操作会将分类下的所有条目文件一同移入回收站。",
                               icon='warning', parent=self.root):
            try:
                was_selected = (self.current_category == selected_category)
                removed = self.manager.remove_category(selected_category)
                if removed:
                    messagebox.showinfo("成功", f"分类 '{selected_category}' 已移到回收站。", parent=self.root)
                    # If the deleted category was selected, clear editor state as well
                    if was_selected:
                        self.current_category = None  # Reset current category state
                        self.clear_editor()  # Clear editor fields
                    self.load_categories()  # Reloads list, selects next/first or clears
            except (ValueError, OSError) as e:
                messagebox.showerror("删除错误", f"移动分类到回收站时出错:\n{str(e)}", parent=self.root)
                self.load_categories()  # Refresh list even on error

    def on_new_entry(self):
        """Prepare editor for a new entry in the current category."""
        if not self.current_category:
            messagebox.showwarning("选择分类", "请先选择一个分类以创建新条目。", parent=self.root)
            return

        self.clear_editor(keep_selection=False)  # Clear editor & deselect list
        self.title_var.set("新条目")
        self.info_label_var.set(f"新条目 (将在 '{self.current_category}' 中创建)")
        # Focus the content area
        content_widget = getattr(self, 'content_text', None)
        if content_widget and content_widget.winfo_exists() and hasattr(content_widget, 'focus_set'):
            content_widget.focus_set()
        print("Editor ready for new entry in:", self.current_category)

    def on_edit_selected_entry(self, event=None):
        """Handle double-click or context menu edit."""
        listbox = getattr(self, 'entry_listbox', None)
        if not listbox or not listbox.curselection(): return
        if len(listbox.curselection()) == 1:
            # Only trigger if not a placeholder
            try:
                idx = listbox.curselection()[0]
                item_text = listbox.get(idx)
                if not item_text.startswith("("):
                    self.on_entry_select(None)  # Just trigger the normal load logic
            except (tk.TclError, IndexError):
                pass  # Ignore errors here
        elif len(listbox.curselection()) > 1:
            messagebox.showinfo("编辑条目", "请选择单个条目进行编辑。", parent=self.root)

    def on_save(self):
        """Save current editor content (new or update)."""
        title = self.title_var.get().strip()
        if not title:
            messagebox.showwarning("需要标题", "标题不能为空。", parent=self.root)
            # Find title entry and focus it
            # This search is basic, might need improvement for complex layouts
            if hasattr(self, 'frame_right'):  # Check if right frame exists
                for widget in self.frame_right.winfo_children():
                    # Check frames within the right frame
                    if isinstance(widget, (ctk.CTkFrame, ttk.Frame)):
                        for subwidget in widget.winfo_children():
                            # Check frames within those subframes (like title_frame)
                            if isinstance(subwidget, (ctk.CTkFrame, ttk.Frame)):
                                for entry_widget in subwidget.winfo_children():
                                    if isinstance(entry_widget, (ctk.CTkEntry, ttk.Entry)):
                                        # Check if this entry uses the title_var
                                        try:
                                            if str(entry_widget.cget('textvariable')) == str(self.title_var):
                                                entry_widget.focus_set()
                                                return  # Found and focused
                                        except tk.TclError:
                                            pass  # Handle cases where textvariable isn't set directly
            return  # Fallback if focus setting failed

        content = ""
        content_widget = getattr(self, 'content_text', None)
        if content_widget and content_widget.winfo_exists():
            start_index = "0.0" if isinstance(content_widget, ctk.CTkTextbox) else 1.0
            try:
                content = content_widget.get(start_index, tk.END).strip()
            except:
                pass

        tags = [tag.strip() for tag in self.tags_var.get().split(",") if tag.strip()]
        category_to_save_in = None
        path_to_update = self.current_entry_path

        # Determine save context (new vs update, target category)
        if path_to_update:  # Potentially updating existing
            try:
                existing_path = Path(path_to_update)
                # Check if the path seems valid and within the root directory structure
                if existing_path.is_file() and self.manager.root_dir in existing_path.parents and existing_path.parent.name != "_trash":
                    category_to_save_in = existing_path.parent.name
                else:
                    raise ValueError("无效路径或指向回收站")  # Path outside root or in trash
            except Exception as e:
                print(f"Invalid existing path '{path_to_update}': {e}")
                if messagebox.askyesno("路径无效",
                                       f"当前编辑条目的文件路径似乎无效或已被移动。\n路径: {path_to_update}\n\n是否尝试在当前选中的分类 '{self.current_category}' 中保存为一个新条目？",
                                       parent=self.root):
                    if not self.current_category: messagebox.showerror("无法保存", "没有选中的分类来保存新条目。",
                                                                       parent=self.root); return
                    category_to_save_in = self.current_category
                    path_to_update = None  # Treat as a new save
                else:
                    return  # Cancel save
        else:  # Creating new entry
            if not self.current_category: messagebox.showwarning("无法保存", "请先选择一个分类以保存新条目。",
                                                                 parent=self.root); return
            category_to_save_in = self.current_category
            path_to_update = None

        if not category_to_save_in: messagebox.showerror("保存错误", "无法确定要保存到的分类。",
                                                         parent=self.root); return

        # --- Perform Save ---
        try:
            # print(f"Debug: Calling save_entry. Category='{category_to_save_in}', Title='{title}', ExistingPath='{path_to_update}'")
            saved_path_str = self.manager.save_entry(category_to_save_in, title, content, tags,
                                                     existing_path_str=path_to_update)
            print(f"Save successful: {saved_path_str}")

            # --- Update State and UI ---
            self.current_entry_path = saved_path_str
            final_category = Path(saved_path_str).parent.name
            final_title = title  # Title used for saving

            # Reload category list if save created a new one (check manager's list *after* save)
            if final_category not in self.manager.categories:
                print("Category list updated by save. Reloading.")
                self.load_categories()
                self._select_listbox_item_by_text(self.category_listbox, final_category)

            # Refresh entry list/search results and select the saved item
            if self.is_search_active:
                self.on_search()  # Re-run search
                search_display_text = f"[{final_category}] {final_title}"
                self._select_listbox_item_by_text(self.entry_listbox, search_display_text)
            elif self.current_category == final_category:
                self.load_entries(final_category)  # Reload current category list
                self._select_listbox_item_by_text(self.entry_listbox, final_title)
            else:  # Saved in a different category, don't switch view automatically
                print(f"Entry saved in '{final_category}', but viewing '{self.current_category}'.")
                pass

            # Update info label from the actually saved file's metadata
            try:
                final_data = self.manager.get_entry_by_path(saved_path_str, read_content=False)
                if final_data and final_data.get("metadata"):
                    self._update_info_label(final_data["metadata"])
                else:
                    self.info_label_var.set("保存成功 (信息刷新失败)")
            except Exception as read_e:
                print(f"Warning: Error reading metadata post-save: {read_e}")
                self.info_label_var.set("保存成功 (信息刷新错误)")

        except (ValueError, OSError, FileExistsError) as e:
            messagebox.showerror("保存错误", f"无法保存条目:\n{str(e)}", parent=self.root)
        except Exception as e:
            messagebox.showerror("意外错误", f"保存时发生未知错误:\n{str(e)}", parent=self.root)
            import traceback;
            traceback.print_exc()

    def on_delete_selected_entries(self):
        """Move selected entries to trash."""
        listbox = getattr(self, 'entry_listbox', None)
        if not listbox or not listbox.curselection():
            messagebox.showwarning("选择条目", "请先在列表中选择一个或多个要删除的条目。", parent=self.root)
            return

        items_to_delete, titles_to_delete, paths_being_deleted = [], [], set()
        selected_indices = listbox.curselection()

        for index in selected_indices:
            try:
                display_text = listbox.get(index)
                if display_text.startswith("("): continue  # Skip placeholders
            except (tk.TclError, IndexError):
                continue  # Skip if index is invalid

            entry_path = self.entry_data_map.get(display_text)
            path_valid = False
            if entry_path:
                try:
                    path_valid = Path(entry_path).is_file()
                except Exception:
                    pass

            if path_valid:
                items_to_delete.append({"title": display_text, "path": entry_path})
                titles_to_delete.append(f"'{display_text}'")
                paths_being_deleted.add(entry_path)
            else:
                print(f"Warning: Skipping delete for invalid item '{display_text}' (path: {entry_path})")

        if not items_to_delete:
            if len(selected_indices) > 0:  # User selected only placeholders
                messagebox.showwarning("无效选择", "选中的项目无法删除。", parent=self.root)
            return

        num = len(items_to_delete)
        title_str = "\n - " + "\n - ".join(titles_to_delete) if num <= 5 else f"\n({num}个条目)"
        if messagebox.askyesno("确认移至回收站", f"确定要将以下条目移到回收站吗？\n{title_str}", icon='warning',
                               parent=self.root):
            deleted_count, errors = 0, []
            for item in items_to_delete:
                try:
                    if self.manager.delete_entry(item["path"]): deleted_count += 1
                except Exception as e:
                    errors.append(f"'{item['title']}': {e}")

            # Refresh UI
            editor_cleared = False
            if self.current_entry_path in paths_being_deleted:
                self.clear_editor()
                editor_cleared = True

            if deleted_count > 0:
                if self.is_search_active:
                    self.on_search()
                elif self.current_category:
                    self.load_entries(self.current_category)
                else:
                    self.load_entries(None)  # Should be empty view if category was deleted

            if errors:
                messagebox.showerror("删除错误", "移动部分条目到回收站时出错:\n" + "\n".join(errors), parent=self.root)
            elif deleted_count > 0:
                # Only show success if no errors occurred or be more specific
                if not errors:
                    messagebox.showinfo("成功", f"{deleted_count} 个条目已移到回收站。", parent=self.root)
                else:
                    messagebox.showwarning("部分成功",
                                           f"{deleted_count} 个条目已移到回收站，但有 {len(errors)} 个发生错误。",
                                           parent=self.root)

    def on_move_selected_entries(self):
        """Move selected entries to another category."""
        listbox = getattr(self, 'entry_listbox', None)
        if not listbox or not listbox.curselection():
            messagebox.showwarning("选择条目", "请先选择一个或多个要移动的条目。", parent=self.root)
            return

        items_to_move, titles_to_move, source_categories, paths_being_moved = [], [], set(), set()
        selected_indices = listbox.curselection()

        for index in selected_indices:
            try:
                display_text = listbox.get(index)
                if display_text.startswith("("): continue
            except (tk.TclError, IndexError):
                continue

            entry_path_str = self.entry_data_map.get(display_text)
            path_valid = False
            entry_path_obj = None
            if entry_path_str:
                try:
                    entry_path_obj = Path(entry_path_str)
                    if entry_path_obj.is_file(): path_valid = True
                except Exception:
                    pass

            if path_valid:
                items_to_move.append({"title": display_text, "path": entry_path_str})
                titles_to_move.append(f"'{display_text}'")
                source_categories.add(entry_path_obj.parent.name)
                paths_being_moved.add(entry_path_str)
            else:
                print(f"Warning: Skipping move for invalid item '{display_text}' (path: {entry_path_str})")

        if not items_to_move:
            if len(selected_indices) > 0:
                messagebox.showwarning("无效选择", "选中的项目无法移动。", parent=self.root)
            return

        # Determine current category for dialog (use single source if applicable)
        dialog_current_category = list(source_categories)[0] if len(source_categories) == 1 else None
        # Pass available categories, excluding the 'current' one for the dialog's dropdown logic
        available_cats = self.manager.categories
        dialog = MoveEntryDialog(self.root, available_cats, dialog_current_category)
        target_category = dialog.result

        if target_category:
            if len(source_categories) == 1 and target_category == list(source_categories)[0]:
                messagebox.showinfo("无需移动", "目标分类与源分类相同。", parent=self.root);
                return

            moved_count, errors = 0, []
            was_new_category = target_category not in self.manager.categories

            for item in items_to_move:
                try:
                    new_path_str = self.manager.move_entry(item["path"], target_category)
                    if new_path_str: moved_count += 1
                except Exception as e:
                    errors.append(f"移动 '{item['title']}': {e}")

            # Refresh UI
            editor_path_updated = False
            editor_cleared = False
            if self.current_entry_path in paths_being_moved:
                old_path_obj = Path(self.current_entry_path)
                new_path_str = str(self.manager.root_dir / target_category / old_path_obj.name)
                if Path(new_path_str).is_file():
                    self.current_entry_path = new_path_str
                    print(f"Editor path updated to: {new_path_str}")
                    editor_path_updated = True
                else:
                    self.clear_editor()  # Clear if new path invalid
                    editor_cleared = True

            # Reload category list if a new one was actually added by the move process
            if was_new_category and target_category in self.manager.categories:
                self.load_categories()

            # Refresh entry list/search
            if moved_count > 0:
                if self.is_search_active:
                    self.on_search()
                elif self.current_category in source_categories:
                    self.load_entries(self.current_category)
                # Potentially switch to target category? Optional.
                # elif self.current_category != target_category:
                #      self._select_listbox_item_by_text(self.category_listbox, target_category)
                #      self.on_category_select() # Load the target category

            if errors:
                messagebox.showerror("移动错误", "移动过程中发生错误:\n" + "\n".join(errors), parent=self.root)
            elif moved_count > 0:
                if not errors:
                    messagebox.showinfo("成功", f"{moved_count} 个条目已移动到 '{target_category}'。", parent=self.root)
                else:
                    messagebox.showwarning("部分成功", f"{moved_count} 个条目已移动，但有 {len(errors)} 个发生错误。",
                                           parent=self.root)

    def on_rename_entry(self):
        """Rename selected single entry."""
        listbox = getattr(self, 'entry_listbox', None)
        if not listbox or len(listbox.curselection()) != 1:
            messagebox.showerror("选择错误", "请先在列表中选择单个条目进行重命名。", parent=self.root)
            return

        try:
            index = listbox.curselection()[0]
            current_display_text = listbox.get(index)
            if current_display_text.startswith("("):
                messagebox.showwarning("无效操作", "不能重命名占位符项目。", parent=self.root)
                return
        except (tk.TclError, IndexError):
            messagebox.showerror("错误", "无法获取选中的条目。", parent=self.root)
            return

        entry_path_str = self.entry_data_map.get(current_display_text)
        path_valid = False
        if entry_path_str:
            try:
                path_valid = Path(entry_path_str).is_file()
            except Exception:
                pass
        if not path_valid: messagebox.showerror("错误", "无法找到条目文件。", parent=self.root); return

        # Get metadata title for dialog prefill
        current_metadata_title = Path(entry_path_str).stem
        try:
            entry_data = self.manager.get_entry_by_path(entry_path_str, read_content=False)
            if entry_data and entry_data.get("metadata", {}).get("title"):
                current_metadata_title = entry_data["metadata"]["title"]
        except Exception as e:
            print(f"Warning: Read metadata failed for rename: {e}")

        dialog_title = "重命名条目"
        dialog_text = f"请输入 '{current_metadata_title}' 的新标题:"
        new_title = None
        if HAS_CTK:
            dialog = ctk.CTkInputDialog(text=dialog_text, title=dialog_title)
            if hasattr(dialog, '_entry'): dialog._entry.insert(0, current_metadata_title)
            new_title = dialog.get_input()
        else:
            new_title = simpledialog.askstring(dialog_title, dialog_text, initialvalue=current_metadata_title,
                                               parent=self.root)

        new_title = new_title.strip() if new_title else None
        if new_title and new_title != current_metadata_title:
            try:
                entry_data = self.manager.get_entry_by_path(entry_path_str, read_content=True)
                if not entry_data: raise ValueError("无法读取原始条目数据。")
                content = entry_data.get('content', '')
                tags = entry_data.get('metadata', {}).get('tags', [])
                entry_category = Path(entry_path_str).parent.name

                saved_path_str = self.manager.save_entry(entry_category, new_title, content, tags,
                                                         existing_path_str=entry_path_str)
                print(f"Rename via save successful: {saved_path_str}")

                # Update UI
                if self.current_entry_path == entry_path_str:
                    self.current_entry_path = saved_path_str
                    self.title_var.set(new_title)
                    try:  # Update info label
                        updated_data = self.manager.get_entry_by_path(saved_path_str, read_content=False)
                        if updated_data and updated_data.get("metadata"): self._update_info_label(
                            updated_data["metadata"])
                    except Exception:
                        pass

                # Refresh list/search
                if self.is_search_active:
                    self.on_search()
                    search_display_text = f"[{entry_category}] {new_title}"
                    self._select_listbox_item_by_text(self.entry_listbox, search_display_text)
                elif self.current_category == entry_category:
                    self.load_entries(entry_category)
                    self._select_listbox_item_by_text(self.entry_listbox, new_title)

            except (ValueError, OSError, FileExistsError) as e:
                messagebox.showerror("重命名错误", f"无法重命名条目:\n{str(e)}", parent=self.root)
            except Exception as e:
                messagebox.showerror("意外错误", f"重命名时出错:\n{str(e)}", parent=self.root)
                import traceback;
                traceback.print_exc()

    # --- Search Handlers ---
    def on_search(self, event=None):
        """Perform search and display results."""
        query = self.search_var.get().strip()
        if not query: self.on_clear_search(); return
        print(f"Searching for: '{query}'")
        try:
            results = self.manager.search(query)  # Search all categories
            self.load_search_results(results)
        except Exception as e:
            messagebox.showerror("搜索错误", f"搜索时发生错误:\n{e}", parent=self.root)

    def on_clear_search(self, event=None):  # Added event=None for binding
        """Clear search results and show current category."""
        if not self.is_search_active and not self.search_var.get(): return
        print("Clearing search.")
        self.search_var.set("")
        self.is_search_active = False
        # Remove focus from search entry
        if hasattr(self.root, 'focus_set'): self.root.focus_set()
        # Reset label and load category entries
        list_label = getattr(self, 'entry_list_label', None)
        if list_label:
            try:
                list_label.configure(text="条目列表")
            except:
                list_label.config(text="条目列表")
        self.load_entries(self.current_category)  # Clears editor too

    # --- Trash Handlers ---
    def on_view_trash(self):
        """Open the trash dialog."""
        try:
            trash_items_paths = self.manager.list_trash()
        except Exception as e:
            messagebox.showerror("错误", f"无法列出回收站内容:\n{e}", parent=self.root);
            return

        dialog = TrashDialog(self.root, trash_items_paths)  # Uses Toplevel/ttk
        items_to_process = dialog.selected_items
        action = dialog.result_action

        if not items_to_process or action is None: return  # Cancelled

        processed_count, errors, affected_categories = 0, [], set()
        action_verb = "恢复" if action == "restore" else "永久删除"

        print(f"Trash action: {action} on {len(items_to_process)} items.")
        for item_path in items_to_process:
            try:
                result = None
                if action == "restore":
                    result = self.manager.restore_trash_item(str(item_path))
                    if result:
                        restored_path = Path(result)
                        # Determine affected category/root
                        parent_dir = restored_path.parent
                        if parent_dir == self.manager.root_dir:
                            if restored_path.is_dir():  # Restored category to root
                                affected_categories.add(restored_path.name)
                            # else: file restored to root - doesn't affect category list directly
                        elif self.manager.root_dir in parent_dir.parents:  # Restored to a sub-category
                            affected_categories.add(parent_dir.name)

                elif action == "delete":
                    result = self.manager.permanently_delete_trash_item(str(item_path))

                if result: processed_count += 1

            except Exception as e:
                errors.append(f"{action_verb} '{item_path.name}': {e}")

        # Refresh UI
        if processed_count > 0:
            # Reload categories if restore *might* have added/changed them
            # Manager methods update self.manager.categories internally if needed.
            # Check if any *new* category name appeared in affected_categories.
            reload_cats = False
            if action == "restore" and affected_categories:
                reload_cats = any(cat not in self.manager.categories for cat in affected_categories if
                                  cat != self.manager.root_dir.name)
                # Or simply reload if any category was involved
                # reload_cats = True

            if reload_cats:
                print("Reloading categories after restore operation.")
                self.load_categories()

            # Refresh entry list/search
            if self.is_search_active:
                self.on_search()
            elif action == "restore" and self.current_category in affected_categories:
                # If the currently viewed category was the target of a restore
                self.load_entries(self.current_category)

        # Show results
        if errors:
            messagebox.showerror(f"{action_verb}错误", f"{action_verb}部分项目时出错:\n" + "\n".join(errors),
                                 parent=self.root)
        elif processed_count > 0:
            messagebox.showinfo("成功", f"{processed_count} 个项目已{action_verb}。", parent=self.root)

    def on_empty_trash(self):
        """Permanently delete all items in trash."""
        try:
            count = len(self.manager.list_trash())
            if count == 0: messagebox.showinfo("回收站为空", "回收站中无项目。", parent=self.root); return
        except Exception as e:
            messagebox.showerror("错误", f"无法检查回收站: {e}", parent=self.root);
            return

        if messagebox.askyesno("确认清空回收站",
                               f"确定要永久删除回收站中的全部 {count} 个项目吗？\n\n**警告：此操作无法撤销！**",
                               icon='warning', parent=self.root):
            try:
                deleted_count, errors = self.manager.empty_trash()
                if errors:
                    messagebox.showerror("清空错误",
                                         f"清空回收站时出错 ({len(errors)}项未删除):\n" + "\n".join(errors[:5]),
                                         parent=self.root)
                elif deleted_count > 0:
                    messagebox.showinfo("成功", f"回收站已清空 ({deleted_count}项已删除)。", parent=self.root)
                else:
                    messagebox.showwarning("清空回收站", "尝试清空，但未删除任何项目 (可能为空或出错)。",
                                           parent=self.root)
            except Exception as e:
                messagebox.showerror("清空错误", f"清空回收站时发生严重错误:\n{e}", parent=self.root)

    # --- Context Menu Handlers ---
    def show_category_menu(self, event):
        """Show context menu for categories."""
        listbox = getattr(self, 'category_listbox', None)
        menu = getattr(self, 'category_menu', None)  # Use the menu instance stored in __init__
        if not listbox or not listbox.winfo_exists() or not menu:
            print("Debug: Category listbox or menu not found for context menu.")
            return

        clicked_index = listbox.nearest(event.y)
        on_item = False
        is_placeholder = False

        if clicked_index >= 0:
            bbox = listbox.bbox(clicked_index)
            # Check if click was within the vertical bounds of the item
            if bbox and (bbox[1] <= event.y < bbox[1] + bbox[3]):
                # Check horizontal bounds too (optional, makes it more precise)
                # if (bbox[0] <= event.x < bbox[0] + bbox[2]):
                on_item = True
                try:
                    item_text = listbox.get(clicked_index)
                    if item_text.startswith("("): is_placeholder = True
                except (tk.TclError, IndexError):
                    on_item = False  # Error getting item, treat as not on item

                if on_item and not is_placeholder:
                    # Select the item under the cursor if it's not already selected
                    if not listbox.selection_includes(clicked_index):
                        listbox.selection_clear(0, tk.END)
                        listbox.selection_set(clicked_index)
                        listbox.activate(clicked_index)
                        self.on_category_select(None)  # Trigger load for the clicked category

        # --- Build Menu ---
        menu.delete(0, tk.END)  # Clear previous items
        menu.add_command(label="新建分类...", command=self.on_new_category)

        selection = listbox.curselection()
        # Only add rename/delete if exactly one *valid* item is selected AND the click was on that item
        if len(selection) == 1 and on_item and not is_placeholder and selection[0] == clicked_index:
            try:
                selected_category = listbox.get(selection[0])
                menu.add_separator()
                menu.add_command(label=f"重命名 '{selected_category}'...", command=self.on_rename_category)
                menu.add_command(label=f"删除 '{selected_category}' (回收站)", command=self.on_delete_selected_category)
            except tk.TclError:
                pass  # Item might have disappeared

        # Apply colors just before popping up
        self._apply_menu_colors()

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def show_entry_menu(self, event):
        """Show context menu for entries."""
        listbox = getattr(self, 'entry_listbox', None)
        menu = getattr(self, 'entry_menu', None)  # Use the menu instance stored in __init__
        if not listbox or not listbox.winfo_exists() or not menu:
            print("Debug: Entry listbox or menu not found for context menu.")
            return

        clicked_index = listbox.nearest(event.y)
        on_item, actual_item_clicked = False, False
        if clicked_index >= 0:
            bbox = listbox.bbox(clicked_index)
            if bbox and (bbox[1] <= event.y < bbox[1] + bbox[3]):
                # if (bbox[0] <= event.x < bbox[0] + bbox[2]): # Optional horizontal check
                on_item = True
                try:
                    item_text = listbox.get(clicked_index)
                    if not item_text.startswith("("): actual_item_clicked = True
                except (tk.TclError, IndexError):
                    on_item = False

                selection = listbox.curselection()
                # If clicking on a valid item NOT in selection, select it exclusively
                if actual_item_clicked and (clicked_index not in selection):
                    listbox.selection_clear(0, tk.END)
                    listbox.selection_set(clicked_index)
                    listbox.activate(clicked_index)
                    self.on_entry_select(None)  # Load single selection

        # --- Build Menu ---
        menu.delete(0, tk.END)
        selection = listbox.curselection()  # Get potentially updated selection
        num_selected = len(selection)

        # Add "New Entry" only if a category is currently selected in the left pane
        if self.current_category:
            menu.add_command(label="新建条目", command=self.on_new_entry)
            menu.add_separator()

        # Add context items only if the click was on an item row
        if num_selected > 0 and on_item:
            valid_titles = []
            has_placeholder = False
            for idx in selection:
                try:
                    txt = listbox.get(idx)
                    if txt.startswith("("):
                        has_placeholder = True;
                        break
                    else:
                        valid_titles.append(txt)
                except (tk.TclError, IndexError):
                    has_placeholder = True;
                    break

            if not has_placeholder and valid_titles:
                # Single valid item selected AND it's the one clicked on
                if num_selected == 1 and actual_item_clicked and selection[0] == clicked_index:
                    title = valid_titles[0]
                    menu.add_command(label=f"编辑 '{title}'", command=self.on_edit_selected_entry)
                    menu.add_command(label=f"重命名 '{title}'...", command=self.on_rename_entry)
                    menu.add_separator()
                    menu.add_command(label=f"删除 '{title}' (回收站)", command=self.on_delete_selected_entries)
                    menu.add_command(label=f"移动 '{title}' 到分类...", command=self.on_move_selected_entries)
                # Multiple valid items selected (action applies to all selected)
                elif num_selected > 0:
                    menu.add_command(label=f"删除 {len(valid_titles)} 个条目 (回收站)",
                                     command=self.on_delete_selected_entries)
                    menu.add_command(label=f"移动 {len(valid_titles)} 个条目到分类...",
                                     command=self.on_move_selected_entries)

        # Apply colors just before popping up
        self._apply_menu_colors()

        if menu.index(tk.END) is not None:  # Only show if menu has items
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()

    # --- Theme Switching ---
    def switch_theme(self, theme):
        """Switch the application theme (CTk or sv-ttk)."""
        print(f"Switching theme to: {theme}")
        new_mode = theme.lower()

        if HAS_CTK:
            if new_mode in ["light", "dark", "system"]:
                ctk.set_appearance_mode(new_mode)
                # Update internal state AFTER setting it
                self.current_theme_mode = ctk.get_appearance_mode().lower()
                # Re-apply all theme-dependent settings
                self._apply_theme()  # Updates root, listboxes, AND menus

                # 更新所有列表框颜色
                if hasattr(self, 'category_listbox') and self.category_listbox.winfo_exists():
                    self._beautify_listbox(self.category_listbox)
                if hasattr(self, 'entry_listbox') and self.entry_listbox.winfo_exists():
                    self._beautify_listbox(self.entry_listbox)
            else:
                print(f"Warning: Unknown CTk theme '{theme}'")
        elif HAS_SVTTK:
            try:
                if new_mode in ["light", "dark"]:
                    sv_ttk.set_theme(new_mode)
                    self.current_theme_mode = new_mode
                    self._apply_theme()  # Update root BG for sv-ttk, try menus
                    self._setup_style()  # Re-apply ttk styles
                    self.root.update_idletasks()
                else:
                    print(f"Warning: Unknown sv-ttk theme '{theme}'")
            except Exception as e:
                messagebox.showwarning("主题错误", f"切换sv-ttk主题'{theme}'失败: {e}", parent=self.root)
        else:
            print("No theme engine available to switch theme.")

        # 切换主题后立即应用到所有UI元素
        self._apply_theme()
        self._ensure_listbox_styling()  # 确保列表控件样式立即更新

        # 美化所有存在的弹出窗口
        for window in self.root.winfo_children():
            if isinstance(window, (tk.Toplevel, ctk.CTkToplevel)):
                for widget in window.winfo_children():
                    self._enhance_listboxes_recursively(widget)

    def on_refresh(self):
        """Refresh data from filesystem."""
        print("Refreshing from filesystem...")
        cat_before = self.current_category
        path_before = self.current_entry_path

        try:
            self.load_categories()  # Reloads categories, tries to keep selection

            # If category still exists, ensure entries are loaded
            if cat_before and cat_before == self.current_category:
                self.load_entries(cat_before)  # Ensure entries for current cat are loaded

                # Try to reselect and reload the previously open entry
                if path_before:
                    path_obj = Path(path_before)
                    entry_found_and_reloaded = False
                    # Check if file still exists and is in the *correct* (current) category
                    if path_obj.exists() and path_obj.is_file() and path_obj.parent.name == cat_before:
                        # Get title for selection
                        entry_data = self.manager.get_entry_by_path(path_before, read_content=False)
                        title = path_obj.stem
                        if entry_data and entry_data.get("metadata", {}).get("title"): title = entry_data["metadata"][
                            "title"]

                        if self._select_listbox_item_by_text(self.entry_listbox, title):
                            self.on_entry_select(None)  # Reload content into editor
                            entry_found_and_reloaded = True
                            print(f"Refreshed and reloaded: {title}")

                    if not entry_found_and_reloaded:
                        # print("Previous entry not found/reloaded after refresh. Clearing editor.")
                        # Only clear editor if the file path was supposed to be valid
                        if self.current_entry_path == path_before:
                            self.clear_editor()
            # If category changed or disappeared, load_categories handled the UI state

            messagebox.showinfo("刷新完成", "已从文件系统刷新。", parent=self.root)

        except Exception as e:
            messagebox.showerror("刷新错误", f"刷新时发生错误:\n{e}", parent=self.root)
            import traceback;
            traceback.print_exc()

    def _create_left_pane(self, parent):
        """创建分类列表面板"""
        if HAS_CTK:
            frame = ctk.CTkFrame(parent, corner_radius=0, border_width=0)

            # --- 顶部操作栏 ---
            top_button_frame = ctk.CTkFrame(frame, fg_color="transparent")
            top_button_frame.pack(fill=tk.X, padx=10, pady=(10, 5))

            # 主题切换按钮
            mode = "dark" if ctk.get_appearance_mode().lower() == "dark" else "light"
            colors = self.soft_colors[mode]

            theme_button = ctk.CTkButton(
                top_button_frame,
                text="主题",
                width=60,
                font=("Microsoft YaHei UI", 15),
                command=self._show_theme_dialog,
                fg_color=colors["button_blue"],
                hover_color=colors["button_blue_hover"],
                text_color=colors["list_select_fg"]
            )
            theme_button.pack(side=tk.LEFT, padx=(0, 5))

            # 添加字体按钮
            font_button = ctk.CTkButton(
                top_button_frame,
                text="字体",
                width=60,
                font=(self.current_font, 15),
                command=self.show_font_dialog,
                fg_color=colors["button_blue"],
                hover_color=colors["button_blue_hover"],
                text_color=colors["list_select_fg"]
            )
            font_button.pack(side=tk.LEFT, padx=(0, 5))

            # 回收站按钮
            trash_button = ctk.CTkButton(
                top_button_frame,
                text="回收站",
                width=70,
                font=("Microsoft YaHei UI", 15),
                command=self.on_view_trash,
                fg_color=colors["button_blue"],
                hover_color=colors["button_blue_hover"],
                text_color=colors["list_select_fg"]
            )
            trash_button.pack(side=tk.LEFT, padx=(0, 5))

            # 清空回收站按钮 - 使用柔和红色
            empty_trash = ctk.CTkButton(
                top_button_frame,
                text="清空回收站",
                width=90,
                font=("Microsoft YaHei UI", 15),
                fg_color=colors["button_red"],
                hover_color=colors["button_red_hover"],
                text_color=colors["list_select_fg"],
                command=self.on_empty_trash
            )
            empty_trash.pack(side=tk.LEFT)

            # 退出按钮 - 使用柔和红色
            exit_button = ctk.CTkButton(
                top_button_frame,
                text="退出",
                width=50,
                font=("Microsoft YaHei UI", 15),
                fg_color=colors["button_red"],
                hover_color=colors["button_red_hover"],
                text_color=colors["list_select_fg"],
                command=self.root.quit
            )
            exit_button.pack(side=tk.RIGHT)

            ctk.CTkLabel(frame, text="分类列表", font=("Microsoft YaHei UI", 16, "bold")).pack(pady=(10, 10), padx=10,
                                                                                               anchor=tk.W)

            list_frame = ctk.CTkFrame(frame, fg_color="transparent")
            list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 5))

            self.category_listbox = tk.Listbox(list_frame, exportselection=False, relief=tk.FLAT,
                                               borderwidth=0, font=("Microsoft YaHei UI", 15), activestyle='none')

            cat_scrollbar = ctk.CTkScrollbar(list_frame, command=self.category_listbox.yview)
            self.category_listbox.config(yscrollcommand=cat_scrollbar.set)

            cat_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            self.category_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

            self.category_listbox.bind("<<ListboxSelect>>", self.on_category_select)
            self.category_listbox.bind("<Button-3>", self.show_category_menu)  # Bind right-click

            cat_button_frame = ctk.CTkFrame(frame, fg_color="transparent")
            cat_button_frame.pack(fill=tk.X, padx=10, pady=(5, 10))

            ctk.CTkButton(
                cat_button_frame,
                text="新建分类",
                width=90,
                command=self.on_new_category,
                font=("Microsoft YaHei UI", 15),
                fg_color=colors["button_blue"],
                hover_color=colors["button_blue_hover"],
                text_color=colors["list_select_fg"]
            ).pack(side=tk.LEFT, padx=(0, 5))

            # --- >> Added Delete Category Button << ---
            # Use a distinct color for delete button if possible
            ctk.CTkButton(cat_button_frame, text="删除分类", width=90, command=self.on_delete_selected_category,
                          font=("Microsoft YaHei UI", 15), fg_color=colors["button_red"],
                          hover_color=colors["button_red_hover"],
                          text_color=colors["list_select_fg"]).pack(side=tk.LEFT, padx=(5, 5))

            ctk.CTkButton(
                cat_button_frame,
                text="刷新",
                width=60,
                command=self.on_refresh,
                font=("Microsoft YaHei UI", 15),
                fg_color=colors["button_blue"],
                hover_color=colors["button_blue_hover"],
                text_color=colors["list_select_fg"]
            ).pack(side=tk.RIGHT, padx=(5, 0))

            return frame

        else:  # ttk fallback
            frame = ttk.Frame(parent, padding=5)

            # 添加顶部按钮框架
            top_button_frame = ttk.Frame(frame)
            top_button_frame.pack(fill=tk.X, pady=(0, 5))

            ttk.Button(top_button_frame, text="主题", width=8,
                       command=self._show_theme_dialog).pack(side=tk.LEFT, padx=(0, 5))
            ttk.Button(top_button_frame, text="回收站", width=10,
                       command=self.on_view_trash).pack(side=tk.LEFT, padx=(0, 5))
            ttk.Button(top_button_frame, text="清空回收站", width=12,
                       command=self.on_empty_trash).pack(side=tk.LEFT)
            ttk.Button(top_button_frame, text="退出", width=8,
                       command=self.root.quit).pack(side=tk.RIGHT)

            ttk.Label(frame, text="分类列表", font=("Segoe UI", 11, "bold")).pack(pady=(0, 5), anchor=tk.W)
            list_frame = ttk.Frame(frame)
            list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 5))
            cat_scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL)
            self.category_listbox = tk.Listbox(list_frame, yscrollcommand=cat_scrollbar.set, exportselection=False,
                                               borderwidth=1, relief=tk.FLAT)
            cat_scrollbar.config(command=self.category_listbox.yview)
            cat_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            self.category_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            self.category_listbox.bind("<<ListboxSelect>>", self.on_category_select)
            self.category_listbox.bind("<Button-3>", self.show_category_menu)  # Bind right-click

            cat_button_frame = ttk.Frame(frame)
            cat_button_frame.pack(fill=tk.X, pady=(5, 0))
            ttk.Button(cat_button_frame, text="新建分类", command=self.on_new_category).pack(side=tk.LEFT, padx=(0, 5))
            ttk.Button(cat_button_frame, text="删除分类", command=self.on_delete_selected_category).pack(side=tk.LEFT,
                                                                                                         padx=(5, 5))
            ttk.Button(cat_button_frame, text="刷新", command=self.on_refresh).pack(side=tk.RIGHT)
            return frame

    # --- >> _create_middle_pane and _create_right_pane unchanged from previous version << ---
    def _create_middle_pane(self, parent):
        """创建条目列表/搜索结果面板"""
        if HAS_CTK:
            frame = ctk.CTkFrame(parent, corner_radius=0, border_width=0)  # 融入 PanedWindow

            # --- 搜索栏框架 ---
            search_frame = ctk.CTkFrame(frame, fg_color="transparent")
            search_frame.pack(fill=tk.X, pady=(10, 5), padx=10)

            # 增大"搜索:"标签字号
            ctk.CTkLabel(search_frame, text="搜索:", font=("Microsoft YaHei UI", 14)).pack(side=tk.LEFT,
                                                                                           padx=(0, 8))  # 增大字号和右边距

            self.search_var = tk.StringVar()
            search_entry = ctk.CTkEntry(search_frame, textvariable=self.search_var, font=("Microsoft YaHei UI", 15),
                                        height=30)  # 微调高度
            search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
            search_entry.bind("<Return>", self.on_search)
            search_entry.bind("<Escape>", self.on_clear_search)  # 绑定 Escape 键清除搜索

            # 获取当前主题的柔和颜色
            mode = "dark" if ctk.get_appearance_mode().lower() == "dark" else "light"
            colors = self.soft_colors[mode]

            # 将"搜索"按钮文字改为"查找"，并应用柔和颜色
            ctk.CTkButton(search_frame, text="查找", width=60, height=30, command=self.on_search,
                          font=("Microsoft YaHei UI", 15),
                          fg_color=colors["button_blue"],
                          hover_color=colors["button_blue_hover"],
                          text_color=colors["list_select_fg"]).pack(side=tk.LEFT, padx=(0, 5))

            ctk.CTkButton(search_frame, text="清除", width=60, height=30, command=self.on_clear_search,
                          font=("Microsoft YaHei UI", 15),
                          fg_color=colors["button_blue"],
                          hover_color=colors["button_blue_hover"],
                          text_color=colors["list_select_fg"]).pack(side=tk.LEFT)

            # --- 列表标签 ---
            self.entry_list_label = ctk.CTkLabel(frame, text="条目列表", font=("Microsoft YaHei UI", 16, "bold"))
            self.entry_list_label.pack(pady=(10, 5), padx=10, anchor=tk.W)

            # --- 条目列表框框架 ---
            list_frame = ctk.CTkFrame(frame, fg_color="transparent")
            list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 5))

            # 使用标准 tk.Listbox 但优化样式
            self.entry_listbox = tk.Listbox(
                list_frame,
                exportselection=False,
                relief=tk.FLAT,
                borderwidth=0,
                font=("Microsoft YaHei UI", 15),
                activestyle='none'  # 去除选中虚线
            )

            entry_scrollbar = ctk.CTkScrollbar(list_frame, command=self.entry_listbox.yview)
            self.entry_listbox.config(yscrollcommand=entry_scrollbar.set)

            entry_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            self.entry_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

            self.entry_listbox.bind("<<ListboxSelect>>", self.on_entry_select)
            self.entry_listbox.bind("<Double-1>", self.on_edit_selected_entry)
            self.entry_listbox.bind("<Button-3>", self.show_entry_menu)  # 右键菜单

            # --- 按钮框架 ---
            button_frame = ctk.CTkFrame(frame, fg_color="transparent")
            button_frame.pack(fill=tk.X, padx=10, pady=(5, 10))

            ctk.CTkButton(
                button_frame,
                text="新建",
                width=60,
                command=self.on_new_entry,
                font=("Microsoft YaHei UI", 15),
                fg_color=colors["button_blue"],
                hover_color=colors["button_blue_hover"],
                text_color=colors["list_select_fg"]
            ).pack(side=tk.LEFT, padx=(0, 5))

            ctk.CTkButton(
                button_frame,
                text="重命名",
                width=70,
                command=self.on_rename_entry,
                font=("Microsoft YaHei UI", 15),
                fg_color=colors["button_blue"],
                hover_color=colors["button_blue_hover"],
                text_color=colors["list_select_fg"]
            ).pack(side=tk.LEFT, padx=(0, 5))

            # 使用柔和红色
            ctk.CTkButton(
                button_frame,
                text="删除",
                width=60,
                font=("Microsoft YaHei UI", 15),
                fg_color=colors["button_red"],
                hover_color=colors["button_red_hover"],
                text_color=colors["list_select_fg"],
                command=self.on_delete_selected_entries
            ).pack(side=tk.LEFT)

            return frame
        else:
            # ttk回退代码保持不变
            frame = ttk.Frame(parent, padding=5)
            search_frame = ttk.Frame(frame)
            search_frame.pack(fill=tk.X, pady=(0, 5))
            ttk.Label(search_frame, text="搜索:").pack(side=tk.LEFT, padx=(0, 5))
            self.search_var = tk.StringVar()
            ttk.Entry(search_frame, textvariable=self.search_var).pack(side=tk.LEFT, fill=tk.X, expand=True,
                                                                       padx=(0, 5))
            ttk.Button(search_frame, text="查找", width=6, command=self.on_search).pack(side=tk.LEFT, padx=(0, 5))
            ttk.Button(search_frame, text="清除", width=6, command=self.on_clear_search).pack(side=tk.LEFT)
            self.entry_list_label = ttk.Label(frame, text="条目列表", font=("", 11, "bold"))
            self.entry_list_label.pack(pady=(0, 5), anchor=tk.W)
            list_frame = ttk.Frame(frame)
            list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 5))
            entry_scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL)
            self.entry_listbox = tk.Listbox(list_frame, yscrollcommand=entry_scrollbar.set, exportselection=False,
                                            borderwidth=1, relief=tk.FLAT)
            entry_scrollbar.config(command=self.entry_listbox.yview)
            entry_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            self.entry_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            self.entry_listbox.bind("<<ListboxSelect>>", self.on_entry_select)
            self.entry_listbox.bind("<Double-1>", self.on_edit_selected_entry)
            self.entry_listbox.bind("<Button-3>", self.show_entry_menu)
            button_frame = ttk.Frame(frame)
            button_frame.pack(fill=tk.X, pady=(5, 0))
            ttk.Button(button_frame, text="新建", command=self.on_new_entry).pack(side=tk.LEFT, padx=(0, 5))
            ttk.Button(button_frame, text="重命名", command=self.on_rename_entry).pack(side=tk.LEFT, padx=(0, 5))
            ttk.Button(button_frame, text="删除", command=self.on_delete_selected_entries).pack(side=tk.LEFT)
            return frame

    def _create_right_pane(self, parent):
        """创建编辑器面板"""
        if HAS_CTK:
            frame = ctk.CTkFrame(parent, corner_radius=0, border_width=0)  # 融入 PanedWindow

            # --- 顶部编辑器框架 (标题、标签、信息) ---
            editor_top_frame = ctk.CTkFrame(frame, fg_color="transparent")
            editor_top_frame.pack(fill=tk.X, padx=10, pady=(10, 5))

            # 标题输入行
            title_frame = ctk.CTkFrame(editor_top_frame, fg_color="transparent")
            title_frame.pack(fill=tk.X, pady=(0, 8))  # 增加下方间距
            ctk.CTkLabel(title_frame, text="标题:", width=50, font=("Microsoft YaHei UI", 13)).pack(side=tk.LEFT,
                                                                                                    padx=(0, 8))
            self.title_var = tk.StringVar()
            title_entry = ctk.CTkEntry(title_frame, textvariable=self.title_var, font=("Microsoft YaHei UI", 13),
                                       height=32)  # 微调高度
            title_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

            # 标签输入行
            tags_frame = ctk.CTkFrame(editor_top_frame, fg_color="transparent")
            tags_frame.pack(fill=tk.X, pady=(0, 8))
            ctk.CTkLabel(tags_frame, text="标签:", width=50, font=("Microsoft YaHei UI", 15)).pack(side=tk.LEFT,
                                                                                                   padx=(0, 8))
            self.tags_var = tk.StringVar()
            tags_entry = ctk.CTkEntry(tags_frame, textvariable=self.tags_var, font=("Microsoft YaHei UI", 15),
                                      height=30)
            tags_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
            ctk.CTkLabel(tags_frame, text="(逗号分隔)", font=("Microsoft YaHei UI", 10, "italic"),
                         text_color="gray").pack(side=tk.LEFT, padx=(8, 0))

            # 信息标签 (创建/更新日期)
            self.info_label_var = tk.StringVar(value="未加载条目")
            info_label = ctk.CTkLabel(editor_top_frame, textvariable=self.info_label_var,
                                      font=("Microsoft YaHei UI", 10), text_color="gray")
            info_label.pack(anchor=tk.W, pady=(5, 5))

            # --- 内容文本区域框架 ---
            content_frame = ctk.CTkFrame(frame, fg_color="transparent")
            content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(5, 5))

            # 使用 CTkTextbox 作为内容编辑器，设置为深色背景
            self.content_text = ctk.CTkTextbox(
                content_frame,
                wrap="word",  # 自动换行
                font=("Microsoft YaHei UI", 13),  # 稍大字体
                border_width=1,  # 设置边框宽度
                fg_color="#2b2b2b",  # 与分类和条目列表一致的深灰色背景
                text_color="white",  # 白色文字以提高可读性
            )
            self.content_text.pack(fill=tk.BOTH, expand=True)

            # --- 保存按钮框架 ---
            save_frame = ctk.CTkFrame(frame, fg_color="transparent")
            save_frame.pack(fill=tk.X, padx=10, pady=(5, 10))

            # 获取当前主题的柔和颜色
            mode = "dark" if ctk.get_appearance_mode().lower() == "dark" else "light"
            colors = self.soft_colors[mode]

            # 保存按钮，使用柔和绿色
            ctk.CTkButton(
                save_frame,
                text="保存",
                command=self.on_save,
                font=("Microsoft YaHei UI", 14, "bold"),
                height=40,
                fg_color=colors["button_green"],
                hover_color=colors["button_green_hover"],
                text_color=colors["list_select_fg"]
            ).pack(fill=tk.X)

            return frame

        else:  # 回退到 ttk 实现
            frame = ttk.Frame(parent, padding=5)
            editor_top_frame = ttk.Frame(frame)
            editor_top_frame.pack(fill=tk.X, pady=(0, 5))
            # Title row
            title_frame = ttk.Frame(editor_top_frame)
            title_frame.pack(fill=tk.X, pady=(0, 3))
            ttk.Label(title_frame, text="标题:", width=6).pack(side=tk.LEFT, padx=(0, 5))
            self.title_var = tk.StringVar()
            ttk.Entry(title_frame, textvariable=self.title_var).pack(side=tk.LEFT, fill=tk.X, expand=True)
            # Tags row
            tags_frame = ttk.Frame(editor_top_frame)
            tags_frame.pack(fill=tk.X, pady=(0, 3))
            ttk.Label(tags_frame, text="标签:", width=6).pack(side=tk.LEFT, padx=(0, 5))
            self.tags_var = tk.StringVar()
            ttk.Entry(tags_frame, textvariable=self.tags_var).pack(side=tk.LEFT, fill=tk.X, expand=True)
            ttk.Label(tags_frame, text="(逗号分隔)", font=("", 8, "italic")).pack(side=tk.LEFT, padx=(5, 0))
            # Info Label
            self.info_label_var = tk.StringVar(value="未加载条目")
            info_label = ttk.Label(editor_top_frame, textvariable=self.info_label_var, font=("", 8), foreground="gray")
            info_label.pack(anchor=tk.W, pady=(3, 0))

            # Content Area Frame
            content_frame = ttk.Frame(frame)
            content_frame.pack(fill=tk.BOTH, expand=True, pady=(5, 5))
            editor_scrollbar = ttk.Scrollbar(content_frame, orient=tk.VERTICAL)
            # 使用 tk.Text 以支持 undo 功能
            self.content_text = tk.Text(content_frame, wrap="word", relief=tk.FLAT, borderwidth=1, undo=True,
                                        yscrollcommand=editor_scrollbar.set)
            editor_scrollbar.config(command=self.content_text.yview)
            editor_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            self.content_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

            # Save Button
            ttk.Button(frame, text="保存", command=self.on_save).pack(pady=(0, 5), padx=0, fill=tk.X)

            return frame

    # --- 添加主题切换对话框方法 ---
    def _show_theme_dialog(self):
        """显示主题选择对话框"""
        if HAS_CTK:
            theme_dialog = ctk.CTkToplevel(self.root)
            theme_dialog.title("选择主题")
            theme_dialog.geometry("300x200")
            theme_dialog.transient(self.root)
            theme_dialog.grab_set()

            # 获取当前主题颜色
            mode = "dark" if ctk.get_appearance_mode().lower() == "dark" else "light"
            colors = self.soft_colors[mode]

            ctk.CTkLabel(theme_dialog, text="选择界面主题",
                         font=("Microsoft YaHei UI", 16, "bold")).pack(pady=(20, 25))

            button_frame = ctk.CTkFrame(theme_dialog, fg_color="transparent")
            button_frame.pack(fill=tk.X, padx=20, pady=10)

            ctk.CTkButton(button_frame, text="亮色", width=80, height=35,
                          font=("Microsoft YaHei UI", 15),
                          fg_color=colors["button_blue"],
                          hover_color=colors["button_blue_hover"],
                          text_color=colors["list_select_fg"],
                          command=lambda: [self.switch_theme("light"), theme_dialog.destroy()]
                          ).pack(side=tk.LEFT, padx=(0, 10))

            ctk.CTkButton(button_frame, text="暗色", width=80, height=35,
                          font=("Microsoft YaHei UI", 15),
                          fg_color=colors["button_blue"],
                          hover_color=colors["button_blue_hover"],
                          text_color=colors["list_select_fg"],
                          command=lambda: [self.switch_theme("dark"), theme_dialog.destroy()]
                          ).pack(side=tk.LEFT, padx=(0, 10))

            ctk.CTkButton(button_frame, text="跟随系统", width=100, height=35,
                          font=("Microsoft YaHei UI", 15),
                          fg_color=colors["button_blue"],
                          hover_color=colors["button_blue_hover"],
                          text_color=colors["list_select_fg"],
                          command=lambda: [self.switch_theme("system"), theme_dialog.destroy()]
                          ).pack(side=tk.LEFT)
        elif HAS_SVTTK:
            theme_dialog = Toplevel(self.root)
            theme_dialog.title("选择主题")
            theme_dialog.geometry("250x150")
            theme_dialog.transient(self.root)
            theme_dialog.grab_set()

            ttk.Label(theme_dialog, text="选择界面主题",
                      font=("Segoe UI", 12, "bold")).pack(pady=(10, 15))

            button_frame = ttk.Frame(theme_dialog)
            button_frame.pack(fill=tk.X, padx=20, pady=10)

            ttk.Button(button_frame, text="亮色", width=10,
                       command=lambda: [self.switch_theme("light"), theme_dialog.destroy()]
                       ).pack(side=tk.LEFT, padx=(0, 10))

            ttk.Button(button_frame, text="暗色", width=10,
                       command=lambda: [self.switch_theme("dark"), theme_dialog.destroy()]
                       ).pack(side=tk.LEFT)
        else:
            messagebox.showinfo("主题", "当前版本不支持主题切换", parent=self.root)

    # 添加字体设置方法
    def _apply_font_settings(self):
        """应用当前字体设置到整个界面"""
        if not hasattr(self, 'current_font') or not self.current_font:
            self.current_font = "Microsoft YaHei UI"

        if not hasattr(self, 'font_size') or not self.font_size:
            self.font_size = 15

        print(f"正在应用字体: {self.current_font}, 大小: {self.font_size}")

        # 更新所有已创建控件的字体
        updated_count = self._update_widgets_font(self.root)
        print(f"已更新 {updated_count} 个控件的字体")

        # 不再使用不存在的set_default_font方法
        if HAS_CTK:
            try:
                # 尝试更新CTk默认字体配置(如果存在此方法)
                if hasattr(ctk, 'set_default_font'):
                    ctk.set_default_font((self.current_font, self.font_size))
                else:
                    # 替代方法：通过ThemeManager修改默认字体(如果支持)
                    if hasattr(ctk, 'ThemeManager'):
                        try:
                            # 这是一个尝试，可能CustomTkinter不支持这种方式
                            default_font = (self.current_font, self.font_size)
                            # 更新主题中的默认字体字典
                            for widget in ["CTkLabel", "CTkButton", "CTkEntry", "CTkOptionMenu"]:
                                if widget in ctk.ThemeManager.theme:
                                    if "font" in ctk.ThemeManager.theme[widget]:
                                        ctk.ThemeManager.theme[widget]["font"] = default_font
                        except Exception as e:
                            print(f"尝试更新CTk主题字体失败: {e}")
            except Exception as e:
                print(f"设置CTk默认字体失败: {e}")
        else:
            # ttk字体更新保持不变
            try:
                style = ttk.Style()
                style.configure("TLabel", font=(self.current_font, self.font_size))
                style.configure("TButton", font=(self.current_font, self.font_size))
                style.configure("TEntry", font=(self.current_font, self.font_size))
                style.configure("TFrame", font=(self.current_font, self.font_size))
                print("已更新ttk样式字体")
            except Exception as e:
                print(f"更新ttk样式时出错: {e}")

        # 强制刷新界面
        self.root.update_idletasks()
        print("已强制刷新界面")
        return updated_count

    def _update_widgets_font(self, parent):
        """递归更新所有控件的字体"""
        updated_count = 0

        # 定义不支持字体属性的CTk控件类型列表
        unsupported_ctk_widgets = [
            'CTkFrame', 'CTkCanvas', 'CTkScrollbar',
            'CTkProgressBar', 'CTkTabview', 'CTkSegmentedButton'
        ]

        # 定义支持字体的CTk控件类型列表(白名单方式更安全)
        supported_ctk_widgets = [
            'CTkLabel', 'CTkButton', 'CTkEntry', 'CTkCheckBox',
            'CTkRadioButton', 'CTkComboBox', 'CTkOptionMenu',
            'CTkTextbox', 'CTkSwitch'
        ]

        for child in parent.winfo_children():
            try:
                # 检查控件类型
                widget_class = child.__class__.__name__

                # 处理CTk控件
                if HAS_CTK and widget_class.startswith('CTk'):
                    # 跳过已知不支持字体的控件类型
                    if widget_class in unsupported_ctk_widgets:
                        pass
                    # 只处理已知支持字体的控件
                    elif widget_class in supported_ctk_widgets:
                        try:
                            child.configure(font=(self.current_font, self.font_size))
                            updated_count += 1
                        except Exception as e:
                            # 降低日志级别，避免大量输出
                            if "font" in str(e).lower():
                                # 这是预期中的"不支持font"错误
                                pass
                            else:
                                # 其他未预期的错误
                                print(f"更新{widget_class}字体时出错: {e}")
                    else:
                        # 对于未知的CTk控件，尝试更新但捕获并忽略错误
                        try:
                            child.configure(font=(self.current_font, self.font_size))
                            updated_count += 1
                        except:
                            pass
                else:
                    # 标准Tkinter控件处理
                    try:
                        # 检查此控件是否有font属性
                        current_font = child.cget('font')
                        if current_font:
                            # 提取字体大小和样式
                            if isinstance(current_font, str):
                                # 解析字符串字体描述
                                parts = current_font.split()
                                size = self.font_size  # 使用配置的字体大小
                                weight = "normal"
                                for part in parts:
                                    if part in ["bold", "italic"]:
                                        weight = part

                                # 设置新字体
                                child.configure(font=(self.current_font, size, weight))
                                updated_count += 1
                            elif isinstance(current_font, tuple):
                                # 已经是元组形式的字体
                                size = current_font[1] if len(current_font) > 1 else self.font_size
                                weight = current_font[2] if len(current_font) > 2 else "normal"
                                child.configure(font=(self.current_font, size, weight))
                                updated_count += 1
                    except (tk.TclError, AttributeError):
                        # 忽略无字体属性的控件
                        pass

            except Exception as e:
                # 只记录真正的未知错误
                print(f"处理控件字体时发生未知错误: {e}")

            # 递归处理子控件
            if child.winfo_children():
                sub_updated = self._update_widgets_font(child)
                updated_count += sub_updated

        return updated_count

    # --- 修复字体选择对话框按钮颜色 ---
    def show_font_dialog(self):
        """显示字体选择对话框"""
        if HAS_CTK:
            # 定义固定的对话框字体和大小 - 不受用户选择影响
            DIALOG_FONT = "Microsoft YaHei UI"
            DIALOG_FONT_SIZE = 13
            DIALOG_TITLE_SIZE = 16

            font_dialog = ctk.CTkToplevel(self.root)
            font_dialog.title("选择字体")
            font_dialog.geometry("550x600")  # 增大高度以容纳更多控件
            font_dialog.transient(self.root)
            font_dialog.grab_set()

            # 获取当前主题的柔和颜色
            mode = "dark" if ctk.get_appearance_mode().lower() == "dark" else "light"
            colors = self.soft_colors[mode]

            # 上部分 - 字体选择
            top_frame = ctk.CTkFrame(font_dialog)
            top_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)

            ctk.CTkLabel(top_frame, text="选择字体",
                         font=(DIALOG_FONT, DIALOG_TITLE_SIZE, "bold")).pack(pady=(0, 15))

            # 字体来源选择
            source_frame = ctk.CTkFrame(top_frame, fg_color="transparent")
            source_frame.pack(fill=tk.X, pady=(0, 15))

            # 字体来源标签
            ctk.CTkLabel(source_frame, text="字体来源:",
                         font=(DIALOG_FONT, DIALOG_FONT_SIZE)).pack(side=tk.LEFT, padx=(0, 10))

            # 使用变量跟踪字体来源选择
            source_var = tk.BooleanVar(value=self.font_manager.use_custom_fonts)

            # 创建单选按钮
            system_radio = ctk.CTkRadioButton(
                source_frame,
                text="系统字体",
                variable=source_var,
                value=False,
                font=(DIALOG_FONT, DIALOG_FONT_SIZE),
                command=lambda: self._update_font_source(font_dialog, False)
            )
            system_radio.pack(side=tk.LEFT, padx=(0, 15))

            custom_radio = ctk.CTkRadioButton(
                source_frame,
                text="自定义字体文件夹",
                variable=source_var,
                value=True,
                font=(DIALOG_FONT, DIALOG_FONT_SIZE),
                command=lambda: self._update_font_source(font_dialog, True)
            )
            custom_radio.pack(side=tk.LEFT)

            # 字体文件夹管理按钮
            folder_frame = ctk.CTkFrame(top_frame, fg_color="transparent")
            folder_frame.pack(fill=tk.X, pady=(0, 15))

            # 显示当前目录路径
            folder_path_var = tk.StringVar(value=str(self.font_manager.custom_fonts_dir))
            folder_path = ctk.CTkEntry(
                folder_frame,
                textvariable=folder_path_var,
                font=(DIALOG_FONT, DIALOG_FONT_SIZE),
                state="readonly"
            )
            folder_path.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

            # 打开/管理文件夹按钮 - 应用柔和颜色
            open_folder_btn = ctk.CTkButton(
                folder_frame,
                text="打开文件夹",
                font=(DIALOG_FONT, DIALOG_FONT_SIZE),
                width=120,
                fg_color=colors["button_blue"],
                hover_color=colors["button_blue_hover"],
                text_color=colors["list_select_fg"],
                command=lambda: self._open_font_folder(folder_path_var)
            )
            open_folder_btn.pack(side=tk.LEFT)

            # 字体列表框架
            list_frame = ctk.CTkFrame(top_frame)
            list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 15))

            # 使用标准Listbox但自定义样式
            self.font_listbox = tk.Listbox(
                list_frame,
                font=(DIALOG_FONT, DIALOG_FONT_SIZE),
                exportselection=False,
                relief=tk.FLAT,
                borderwidth=1,
                bd=10  # 加内边距，但不改变数据
            )

            # 设置深色背景和选择颜色
            select_bg = "#464646"  # 深灰色背景
            select_fg = "white"
            list_bg = "#3a3a3a"  # 改为稍浅的灰色背景，使白色文字更易读

            self.font_listbox.config(
                selectbackground=select_bg,
                selectforeground=select_fg,
                bg=list_bg,
                fg="#e0e0e0",  # 使用更亮的灰白色文字，提高可读性
                bd=10  # 添加内边距
            )

            scrollbar = ctk.CTkScrollbar(list_frame, command=self.font_listbox.yview)
            self.font_listbox.config(yscrollcommand=scrollbar.set)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            self.font_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

            # 填充字体列表
            self._load_fonts_to_listbox()

            # 字体大小选择
            size_frame = ctk.CTkFrame(top_frame, fg_color="transparent")
            size_frame.pack(fill=tk.X, pady=(0, 15))
            ctk.CTkLabel(size_frame, text="字体大小:",
                         font=(DIALOG_FONT, DIALOG_FONT_SIZE)).pack(side=tk.LEFT, padx=(0, 10))

            size_var = tk.IntVar(value=self.font_size)
            size_options = [8, 9, 10, 11, 12, 13, 14, 15, 16, 18, 20, 22, 24]

            size_menu = ctk.CTkOptionMenu(
                size_frame,
                values=[str(s) for s in size_options],
                variable=size_var,
                dynamic_resizing=False,
                font=(DIALOG_FONT, DIALOG_FONT_SIZE)
            )
            size_menu.set(str(self.font_size))
            size_menu.pack(side=tk.LEFT)

            # 预览区域
            preview_frame = ctk.CTkFrame(top_frame)
            preview_frame.pack(fill=tk.X, pady=(0, 10))
            ctk.CTkLabel(preview_frame, text="预览:",
                         font=(DIALOG_FONT, DIALOG_FONT_SIZE)).pack(anchor=tk.W, padx=10, pady=(10, 5))

            # 使用固定高度的预览区域
            preview_text = ctk.CTkLabel(
                preview_frame,
                text="字体预览: 汉字abc123文字示例",
                font=(self.current_font, self.font_size),
                height=50,
                corner_radius=6,
                fg_color=("#E0E0E0", "#404040")  # 确保在暗模式下有足够对比度
            )
            preview_text.pack(fill=tk.X, padx=10, pady=(0, 10))

            # 更新预览的函数
            def update_preview(*args):
                selected_indices = self.font_listbox.curselection()
                if selected_indices:
                    selected_font = self.font_listbox.get(selected_indices[0])
                    try:
                        size = int(size_menu.get())
                        preview_text.configure(font=(selected_font, size))
                    except (ValueError, tk.TclError) as e:
                        print(f"预览更新错误: {e}")

            # 绑定事件
            self.font_listbox.bind("<<ListboxSelect>>", update_preview)
            size_menu.configure(command=update_preview)

            # 底部按钮 - 独立显示，确保可见
            button_frame = ctk.CTkFrame(font_dialog, fg_color="transparent")
            button_frame.pack(fill=tk.X, padx=15, pady=15)

            def apply_font():
                selected_indices = self.font_listbox.curselection()
                if selected_indices:
                    new_font = self.font_listbox.get(selected_indices[0])
                    try:
                        new_size = int(size_menu.get())

                        print(f"用户选择了字体: {new_font}, 大小: {new_size}")

                        # 更新实例变量
                        self.current_font = new_font
                        self.font_size = new_size

                        # 更新FontManager中的设置
                        self.font_manager.current_font = self.current_font
                        self.font_manager.font_size = self.font_size
                        self.font_manager.use_custom_fonts = source_var.get()

                        # 如果当前文件夹路径不是默认路径，更新它
                        current_path = Path(folder_path_var.get())
                        if current_path != self.font_manager.custom_fonts_dir:
                            self.font_manager.custom_fonts_dir = current_path

                        # 保存设置到配置文件
                        self.font_manager.save_settings()

                        # 应用字体设置
                        self._apply_font_settings()

                        # 强制刷新主窗口
                        self.root.update_idletasks()

                        # 关闭对话框前等待短暂时间使视觉变化更明显
                        font_dialog.after(100, font_dialog.destroy)

                        # 显示成功消息
                        messagebox.showinfo("字体设置",
                                            f"字体设置已更新并应用到界面。\n"
                                            f"字体: {new_font}\n"
                                            f"大小: {new_size}\n"
                                            f"来源: {'自定义字体文件夹' if source_var.get() else '系统字体'}",
                                            parent=self.root)
                    except ValueError as e:
                        messagebox.showerror("输入错误", f"字体大小设置错误: {e}", parent=font_dialog)
                    except Exception as e:
                        messagebox.showerror("应用错误", f"应用字体设置时出错: {e}", parent=font_dialog)

            # 使用更明显的按钮样式，应用柔和颜色
            apply_button = ctk.CTkButton(
                button_frame,
                text="应用字体",
                command=apply_font,
                height=40,  # 增加按钮高度
                font=(DIALOG_FONT, DIALOG_FONT_SIZE, "bold"),  # 固定字体
                fg_color=colors["button_green"],
                hover_color=colors["button_green_hover"],
                text_color=colors["list_select_fg"]
            )
            apply_button.pack(side=tk.LEFT, padx=(0, 10), fill=tk.X, expand=True)

            cancel_button = ctk.CTkButton(
                button_frame,
                text="取消",
                command=font_dialog.destroy,
                height=40,
                font=(DIALOG_FONT, DIALOG_FONT_SIZE),
                fg_color=colors["button_red"],
                hover_color=colors["button_red_hover"],
                text_color=colors["list_select_fg"]
            )
            cancel_button.pack(side=tk.LEFT, fill=tk.X, expand=True)

            # 更新控件状态
            self._update_font_dialog_states(font_dialog, source_var.get())

        else:
            # 保留原有的Tkinter实现...
            pass

    def _load_fonts_to_listbox(self):
        """加载可用字体到列表框"""
        if hasattr(self, 'font_listbox') and self.font_listbox.winfo_exists():
            self.font_listbox.delete(0, tk.END)  # 清空列表

            # 获取当前应该显示的字体列表 (系统或自定义)
            all_fonts = self.font_manager.get_all_fonts()

            # 检查是否为空列表或特殊提示
            if not all_fonts or (len(all_fonts) == 1 and all_fonts[0].startswith("<")):
                # 处理没有字体的情况 - 显示提示信息
                self.font_listbox.insert(tk.END, all_fonts[0] if all_fonts else "<无可用字体>")
                return

            # 正常情况：添加所有字体
            for font in all_fonts:
                self.font_listbox.insert(tk.END, font)

            # 选中当前字体（如果在列表中）
            if self.current_font in all_fonts:
                index = all_fonts.index(self.current_font)
                self.font_listbox.selection_set(index)
                self.font_listbox.see(index)
            # 如果当前字体不在新列表中，选择第一项
            elif all_fonts:
                self.font_listbox.selection_set(0)

    def _update_font_source(self, dialog, use_custom):
        """更新字体来源并刷新字体列表"""
        print(f"切换字体来源: {'自定义文件夹' if use_custom else '系统字体'}")

        # 更新字体管理器设置
        self.font_manager.use_custom_fonts = use_custom

        # 如果切换到自定义字体，确保已加载自定义文件夹中的字体
        if use_custom:
            custom_dir = self.font_manager.custom_fonts_dir
            print(f"从文件夹加载字体: {custom_dir}")
            loaded = self.font_manager.load_custom_fonts_from_directory(str(custom_dir))
            if not loaded:
                print(f"警告: 文件夹 {custom_dir} 中未找到字体文件")
                messagebox.showwarning(
                    "空文件夹",
                    f"文件夹 '{custom_dir}' 中未找到字体文件。\n\n请将字体文件(.ttf, .otf等)复制到此文件夹中。",
                    parent=dialog
                )

        # 更新列表
        self._load_fonts_to_listbox()

        # 更新对话框控件状态
        self._update_font_dialog_states(dialog, use_custom)

    def _update_font_dialog_states(self, dialog, use_custom):
        """根据字体来源设置更新对话框控件状态"""
        # 查找文件夹相关控件并更新状态
        for child in dialog.winfo_children():
            if isinstance(child, ctk.CTkFrame):
                for frame_child in child.winfo_children():
                    if isinstance(frame_child, ctk.CTkFrame):
                        for button in frame_child.winfo_children():
                            if isinstance(button, ctk.CTkButton) and button.cget("text") == "打开文件夹":
                                # 启用/禁用打开文件夹按钮
                                button.configure(state="normal" if use_custom else "disabled")

    def _open_font_folder(self, path_var):
        """打开或创建字体文件夹"""
        try:
            # 获取当前路径
            current_path = Path(path_var.get())

            # 确保路径存在
            if not current_path.exists():
                current_path.mkdir(parents=True, exist_ok=True)
                print(f"创建字体文件夹: {current_path}")

            # 尝试用系统文件管理器打开文件夹
            if platform.system() == "Windows":
                os.startfile(current_path)
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(["open", str(current_path)])
            else:  # Linux
                subprocess.run(["xdg-open", str(current_path)])

            # 更新路径变量和字体管理器
            self.font_manager.custom_fonts_dir = current_path
            path_var.set(str(current_path))

            # 如果启用了自定义字体，重新加载
            if self.font_manager.use_custom_fonts:
                self.font_manager.load_custom_fonts_from_directory(str(current_path))
                self._load_fonts_to_listbox()

        except Exception as e:
            messagebox.showerror("文件夹操作错误", f"无法操作字体文件夹: {e}")

    def _load_custom_fonts_dialog(self, parent_dialog):
        """打开对话框选择字体文件夹"""
        from tkinter import filedialog

        font_dir = filedialog.askdirectory(
            title="选择包含字体文件的文件夹",
            parent=parent_dialog,
            initialdir=str(self.font_manager.custom_fonts_dir)  # 从当前字体文件夹开始
        )

        if font_dir:
            # 更新路径变量 - 查找并更新文件夹路径显示
            for child in parent_dialog.winfo_children():
                if isinstance(child, ctk.CTkFrame):
                    for frame in child.winfo_children():
                        if isinstance(frame, ctk.CTkFrame):
                            for entry in frame.winfo_children():
                                if isinstance(entry, ctk.CTkEntry) and hasattr(entry, 'cget'):
                                    try:
                                        # 如果这是路径显示框，更新它
                                        if 'textvariable' in entry.configure():
                                            entry.configure(textvariable=tk.StringVar(value=font_dir))
                                            break
                                    except:
                                        pass

            # 加载新的字体文件
            success = self.font_manager.load_custom_fonts_from_directory(font_dir)
            if success:
                # 自动切换到自定义字体模式
                self.font_manager.use_custom_fonts = True

                # 更新字体列表
                self._load_fonts_to_listbox()

                # 更新对话框控件状态 - 查找并选中自定义字体单选按钮
                for child in parent_dialog.winfo_children():
                    if isinstance(child, ctk.CTkFrame):
                        for frame in child.winfo_children():
                            if isinstance(frame, ctk.CTkFrame):
                                for radio in frame.winfo_children():
                                    if isinstance(radio, ctk.CTkRadioButton) and radio.cget(
                                            "text") == "自定义字体文件夹":
                                        radio.select()
                                        # 更新其他控件状态
                                        self._update_font_dialog_states(parent_dialog, True)
                                        break

                # 保存字体文件夹设置
                self.font_manager.custom_fonts_dir = Path(font_dir)
                self.font_manager.save_settings(font_dir)

                # 显示成功消息
                messagebox.showinfo(
                    "成功",
                    f"已加载 {len(self.font_manager.custom_fonts)} 个自定义字体",
                    parent=parent_dialog
                )
            else:
                messagebox.showwarning("警告", "在选定的文件夹中未找到字体文件", parent=parent_dialog)

    # 在程序退出时保存设置
    def on_close(self):
        """程序关闭时的处理"""
        # 保存字体设置
        if hasattr(self, 'font_manager'):
            self.font_manager.save_settings()
        # 退出程序
        self.root.quit()

    # --- 在 NovelManagerGUI 类中添加新方法 ---
    def _customize_listbox_display(self):
        """自定义列表框显示效果，增强美观度"""
        pass  # 不再执行任何操作，以免破坏功能

    # 添加新方法进行UI增强
    def _apply_ui_enhancements(self):
        """应用全局UI增强效果"""
        if HAS_CTK:
            # 设置自定义颜色变量和圆角
            ctk.set_default_color_theme("blue")  # 或创建自定义主题

            # 立即美化所有标准Listbox的视觉效果
            for widget in self.root.winfo_children():
                self._enhance_listboxes_recursively(widget)

            # 确保应用后立即可见
            self.root.update_idletasks()

    def _enhance_listboxes_recursively(self, parent):
        """递归增强所有Listbox控件的视觉效果"""
        for widget in parent.winfo_children():
            if isinstance(widget, tk.Listbox):
                self._beautify_listbox(widget)
            elif hasattr(widget, 'winfo_children'):
                self._enhance_listboxes_recursively(widget)

    def _beautify_listbox(self, listbox):
        """美化单个Listbox控件的视觉效果"""
        try:
            # 无论亮暗模式，始终使用深灰色背景和固定的选中颜色
            bg_color = "#2b2b2b"  # 深灰色背景
            select_bg = "#3f4e5d"  # 稍亮的蓝灰色作为选中背景
            select_fg = "white"  # 白色文字作为选中文本颜色

            # 应用统一的颜色样式
            listbox.config(
                selectbackground=select_bg,
                selectforeground=select_fg,
                bg=bg_color,
                fg="white",  # 设置文本颜色为白色以匹配深色背景
                bd=10,  # 内边距值保持不变
                relief=tk.FLAT
            )

            # 立即应用变更
            listbox.update_idletasks()
        except Exception as e:
            print(f"美化Listbox时出错: {e}")

    # 添加新方法确保列表样式立即应用
    def _ensure_listbox_styling(self):
        """确保列表框样式在启动时立即应用"""
        if hasattr(self, 'category_listbox') and self.category_listbox.winfo_exists():
            self._beautify_listbox(self.category_listbox)
        if hasattr(self, 'entry_listbox') and self.entry_listbox.winfo_exists():
            self._beautify_listbox(self.entry_listbox)


# --- Main Execution ---
if __name__ == "__main__":
    # 优先使用 CustomTkinter 的根窗口
    root = ctk.CTk() if HAS_CTK else tk.Tk()

    # 确保 NovelManager 及其目录在 GUI 完全启动前已初始化
    try:
        manager = NovelManager()  # 初始化管理器一次，创建目录
    except Exception as e:
        # 在显示错误消息前确保根窗口存在
        if not root or not root.winfo_exists():
            # 如果根窗口创建失败（不太可能，但以防万一），用临时的 tk.Tk 来显示错误
            temp_root = tk.Tk()
            temp_root.withdraw()  # Hide the temporary window
            messagebox.showerror("初始化错误", f"无法初始化数据存储:\n{e}", parent=temp_root)
            temp_root.destroy()
        else:
            messagebox.showerror("初始化错误", f"无法初始化数据存储:\n{e}", parent=root)

        # 确保在退出前销毁可能已创建的窗口
        if root and root.winfo_exists():
            root.destroy()
        exit()

    app = NovelManagerGUI(root, manager)  # 将根窗口传递给 GUI 类

    # 添加窗口关闭事件处理
    root.protocol("WM_DELETE_WINDOW", app.on_close)

    root.mainloop()

# --- END OF FILE 小说助手_完整修复版.py ---
