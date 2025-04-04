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

# Import the theme library - place this early
try:
    import sv_ttk
except ImportError:
    print("Warning: sv-ttk theme library not found. Using default Tkinter theme.")
    sv_ttk = None  # Set to None if not found


# --- Custom Dialog for Moving Entries ---
class MoveEntryDialog(Toplevel):
    def __init__(self, parent, existing_categories, current_category):
        super().__init__(parent)
        self.title("移动条目到分类")
        self.geometry("350x150")
        self.transient(parent)  # Keep dialog on top of parent
        self.grab_set()  # Modal behavior

        self.result = None
        # Exclude current category from dropdown if moving FROM a single category
        # If moving items from multiple categories, show all possible targets.
        self.existing_categories = sorted([cat for cat in existing_categories if cat != current_category])
        # Ensure all categories are available if current_category is None (e.g., moving search results)
        if current_category is None:
            self.existing_categories = sorted(existing_categories)

        # --- Widgets ---
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main_frame, text="选择现有分类或输入新分类:").grid(row=0, column=0, columnspan=2, pady=(0, 10),
                                                                     sticky='w')

        # Combobox for existing categories
        ttk.Label(main_frame, text="选择分类:").grid(row=1, column=0, padx=(0, 5), sticky='w')
        self.category_combo = ttk.Combobox(main_frame, values=self.existing_categories, state="readonly", width=30)
        self.category_combo.grid(row=1, column=1, sticky='ew')
        self.category_combo.bind("<<ComboboxSelected>>", self.on_combo_select)

        # Entry for new category
        ttk.Label(main_frame, text="或新建分类:").grid(row=2, column=0, padx=(0, 5), pady=(5, 0), sticky='w')
        self.new_category_entry = ttk.Entry(main_frame)
        self.new_category_entry.grid(row=2, column=1, pady=(5, 0), sticky='ew')
        self.new_category_entry.bind("<KeyRelease>", self.on_entry_type)  # Clear combobox if typing

        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=3, column=0, columnspan=2, pady=(15, 0))

        ok_button = ttk.Button(button_frame, text="确定", command=self.on_ok)
        ok_button.pack(side=tk.LEFT, padx=5)
        cancel_button = ttk.Button(button_frame, text="取消", command=self.on_cancel)
        cancel_button.pack(side=tk.LEFT, padx=5)

        main_frame.columnconfigure(1, weight=1)  # Make input fields expand

        # Set focus initially
        if self.existing_categories:
            self.category_combo.focus_set()
        else:
            self.new_category_entry.focus_set()

        self.wait_window(self)  # Wait until dialog is closed

    def on_combo_select(self, event=None):
        """Clear the entry field when a category is selected from the combobox."""
        self.new_category_entry.delete(0, tk.END)

    def on_entry_type(self, event=None):
        """Clear the combobox selection when typing in the entry field."""
        if self.new_category_entry.get():
            self.category_combo.set('')  # Clear selection

    def on_ok(self):
        selected_category = self.category_combo.get()
        new_category_name = self.new_category_entry.get().strip()

        if new_category_name:
            # User entered a new category name
            if new_category_name == "_trash":  # Prevent naming category '_trash'
                messagebox.showerror("错误", "分类名称 '_trash' 是保留名称。", parent=self)
                return
            # MODIFICATION: More comprehensive invalid char check for filenames/dirs
            # Matches common invalid chars on Windows and POSIX-like systems
            if re.search(r'[<>:"/\\|?*]', new_category_name) or any(ord(c) < 32 for c in new_category_name):
                messagebox.showerror("错误", "分类名称包含无效字符或控制字符。", parent=self)
                return
            self.result = new_category_name
        elif selected_category:
            # User selected an existing category
            self.result = selected_category
        else:
            messagebox.showwarning("选择分类", "请选择一个现有分类或输入一个新的分类名称。", parent=self)
            return

        self.destroy()

    def on_cancel(self):
        self.result = None
        self.destroy()


# --- Custom Dialog for Viewing Trash ---
class TrashDialog(Toplevel):
    def __init__(self, parent, trash_items):
        super().__init__(parent)
        self.title("回收站内容")
        self.geometry("500x400")
        self.transient(parent)
        self.grab_set()

        self.selected_items = []  # Store paths of selected items
        self.result_action = None  # MODIFICATION: To track if delete or restore was chosen

        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main_frame, text="回收站中的项目 (文件或分类):").pack(anchor=tk.W, pady=(0, 5))

        list_frame = ttk.Frame(main_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL)
        self.listbox = Listbox(list_frame, yscrollcommand=scrollbar.set, selectmode=tk.EXTENDED, exportselection=False)
        scrollbar.config(command=self.listbox.yview)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.item_map = {}  # Map display name to actual Path object
        for item_path in sorted(trash_items, key=lambda p: p.name):
            display_name = item_path.name
            self.listbox.insert(tk.END, display_name)
            self.item_map[display_name] = item_path

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X)

        restore_button = ttk.Button(button_frame, text="恢复选中项", command=self.on_restore)
        restore_button.pack(side=tk.LEFT, padx=5)

        # MODIFICATION: Changed button text for clarity
        delete_button = ttk.Button(button_frame, text="永久删除选中项", command=self.on_delete_selected)
        delete_button.pack(side=tk.LEFT, padx=5)

        close_button = ttk.Button(button_frame, text="关闭", command=self.on_cancel)  # Use on_cancel
        close_button.pack(side=tk.RIGHT, padx=5)

        self.protocol("WM_DELETE_WINDOW", self.on_cancel)  # Handle window close button

        self.wait_window(self)

    def on_restore(self):
        selected_indices = self.listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("选择项目", "请先选择要恢复的项目。", parent=self)
            return

        self.selected_items = []
        for index in selected_indices:
            display_name = self.listbox.get(index)
            self.selected_items.append(self.item_map[display_name])

        # MODIFICATION: Set result action
        self.result_action = "restore"
        self.destroy()  # Close the dialog, result is in self.selected_items

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
            self.selected_items = items_to_delete_paths  # Signal these should be deleted
            # MODIFICATION: Set result action
            self.result_action = "delete"
            self.destroy()

    def on_cancel(self):
        self.selected_items = []  # Ensure no items are returned if cancelled
        self.result_action = None  # MODIFICATION: Ensure action is reset
        self.destroy()


# --- Backend Logic (NovelManager) ---
class NovelManager:
    def __init__(self, root_dir="novel_data"):
        """Initialize novel manager using pathlib."""
        self.root_dir = Path(root_dir).resolve()  # Use resolved absolute path
        self.trash_dir = self.root_dir / "_trash"
        self._ensure_directories()
        self.categories = self._load_categories()

    def _ensure_directories(self):
        """Ensure base and trash directories exist."""
        self.root_dir.mkdir(exist_ok=True)
        self.trash_dir.mkdir(exist_ok=True)

    def _load_categories(self):
        """Load categories from directories, excluding trash, and return sorted."""
        cats = [d.name for d in self.root_dir.iterdir()
                if d.is_dir() and d.name != "_trash"]
        cats.sort()
        return cats

    def _get_safe_filename(self, title):
        """Create a safe filename from a title, replacing invalid chars and spaces."""
        # MODIFICATION: Stricter cleaning for filenames
        # Replace common invalid characters with underscore
        safe_title = re.sub(r'[<>:"/\\|?*]', "_", title)
        # Replace sequences of whitespace with a single underscore
        safe_title = re.sub(r'\s+', '_', safe_title)
        # Remove leading/trailing underscores/dots/spaces that might result or be problematic
        safe_title = safe_title.strip('_. ')
        # Prevent names that are reserved on Windows (CON, PRN, AUX, NUL, COM1-9, LPT1-9)
        if safe_title.upper() in ("CON", "PRN", "AUX", "NUL") or \
                re.match(r"^(COM|LPT)\d$", safe_title.upper()):
            safe_title = "_" + safe_title  # Prepend underscore

        # Ensure filename is not empty after cleaning
        return safe_title if safe_title else "untitled"

    def _get_entry_path(self, category, title):
        """Get the Path object for a given category and title."""
        safe_filename = self._get_safe_filename(title) + ".md"
        category_path = self.root_dir / category
        # No need to mkdir here, save_entry will handle it
        return category_path / safe_filename

    def save_entry(self, category, title, content, tags=None, existing_path_str=None):
        """Save or update an entry. Handles rename/move via existing_path_str."""
        if not title:
            raise ValueError("标题不能为空")

        # MODIFICATION: Add category if it doesn't exist physically
        category_path = self.root_dir / category
        if not category_path.is_dir():
            try:
                self.add_category(category)  # Try to add it
            except (ValueError, OSError) as e:
                # Propagate error if category name is invalid or creation fails
                raise ValueError(f"无效或无法创建分类 '{category}': {e}")
        elif category not in self.categories:
            # Dir exists but not in list (e.g. external creation), add it
            self.categories.append(category)
            self.categories.sort()

        tags = tags or []
        now_iso = datetime.datetime.now().isoformat()  # Use ISO format for consistency
        new_file_path = self._get_entry_path(category, title)

        metadata = {
            "title": title,  # Store the user-facing title here
            "created_at": now_iso,  # Default to now
            "updated_at": now_iso,
            "tags": tags
        }

        existing_path = Path(existing_path_str) if existing_path_str else None
        original_created_at = now_iso

        # Check if updating an existing entry
        if existing_path and existing_path.exists() and existing_path.is_file():
            try:
                # Read existing metadata to preserve creation time
                existing_data = self.get_entry_by_path(existing_path, read_content=False)
                if existing_data and "metadata" in existing_data:
                    original_created_at = existing_data["metadata"].get("created_at", now_iso)
            except Exception as e:
                print(f"Warning: Could not read metadata from {existing_path} to preserve creation time: {e}")
                # Proceed with current time as creation time if reading fails
            # Check if title actually changed for rename handling
            old_title_from_meta = existing_data.get("metadata", {}).get("title",
                                                                        existing_path.stem) if existing_data else existing_path.stem
            is_rename = (title != old_title_from_meta)
            is_move = (new_file_path.parent != existing_path.parent)

        else:  # This is a new entry
            existing_path = None  # Ensure it's None if not updating
            is_rename = False
            is_move = False

        # Always use the preserved or current creation time
        metadata["created_at"] = original_created_at
        # Update 'updated_at' regardless
        metadata["updated_at"] = now_iso

        # Prepare file content with metadata header
        # Ensure the actual title is in metadata, filename is just for storage
        metadata["title"] = title
        file_content = f"---\n{json.dumps(metadata, ensure_ascii=False, indent=2)}\n---\n\n{content}"

        try:
            # Write to the new path
            new_file_path.parent.mkdir(parents=True, exist_ok=True)  # Ensure target dir exists
            # MODIFICATION: Prevent overwriting a *different* file if safe filename clashes
            # (Unlikely with good _get_safe_filename, but safer)
            # Only check if it's not the same logical file being updated (path might change due to title rename)
            if new_file_path.exists() and new_file_path != existing_path:
                raise FileExistsError(f"目标文件名 '{new_file_path.name}' 在分类 '{category}' 中已存在。")

            new_file_path.write_text(file_content, encoding="utf-8")

            # If it was an update and the path changed (rename or implicit move via save), delete the old file
            if existing_path and existing_path.exists() and existing_path != new_file_path:
                try:
                    existing_path.unlink()  # Delete old file *after* successful save of new one
                except OSError as del_e:
                    print(f"Warning: Could not delete old file '{existing_path}' after rename/move: {del_e}")

            return str(new_file_path)  # Return the path of the saved/updated file
        except OSError as e:
            raise OSError(f"无法写入文件 '{new_file_path}': {e}")

    def delete_entry(self, entry_path_str):
        """Move an entry file to the trash directory with metadata update."""
        path = Path(entry_path_str)
        if not path.exists() or not path.is_file() or self.trash_dir in path.parents:
            print(f"Skipping delete: Path invalid or already in trash {path}")
            # MODIFICATION: Raise error for clarity instead of returning False silently
            raise FileNotFoundError(f"无法删除：文件不存在、无效或已在回收站 '{entry_path_str}'")

        try:
            # 1. Read existing data (if possible) to add original category/delete time
            original_category = path.parent.name
            now_iso = datetime.datetime.now().isoformat()
            metadata = {"title": path.stem}  # Fallback metadata
            content = ""
            try:
                entry_data = self.get_entry_by_path(path, read_content=True)
                if entry_data:
                    metadata = entry_data.get("metadata", metadata)
                    content = entry_data.get("content", "")
            except Exception as read_e:
                print(f"Warning: Could not read data from {path} before trashing: {read_e}")
                # Still proceed with trashing

            # 2. Add trash-specific metadata
            metadata["_original_category"] = original_category
            metadata["_deleted_at"] = now_iso
            metadata["title"] = metadata.get("title", path.stem)  # Ensure title exists

            # 3. Prepare updated file content
            file_content = f"---\n{json.dumps(metadata, ensure_ascii=False, indent=2)}\n---\n\n{content}"

            # 4. Define unique trash filename
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            # Use original title from metadata if available for filename base, else use file stem
            base_name = self._get_safe_filename(metadata.get("title", path.stem))
            # MODIFICATION: Ensure suffix is preserved (e.g., if not .md in future)
            trash_filename = f"{ts}_{base_name}{path.suffix or '.md'}"
            target_trash_path = self.trash_dir / trash_filename
            # Simple collision check (though timestamp makes it unlikely)
            counter = 0
            while target_trash_path.exists():
                counter += 1
                trash_filename = f"{ts}_{base_name}_{counter}{path.suffix or '.md'}"
                target_trash_path = self.trash_dir / trash_filename

            # 5. Write the updated content to the original file *first* (atomic replace might be better, but this is simpler)
            #   REMOVED this step - just move the file, metadata is read before move. Writing first adds risk.
            # try:
            #     path.write_text(file_content, encoding="utf-8")
            # except OSError as write_e:
            #      print(f"Error: Could not update metadata in {path} before moving to trash: {write_e}. Aborting trash operation.")
            #      raise OSError(f"无法更新文件元数据以移入回收站 '{path}': {write_e}")

            # 6. Move the file to trash
            shutil.move(str(path), str(target_trash_path))
            print(f"Moved entry to trash: {target_trash_path}")
            return True  # Indicate successful move to trash

        except (OSError, Exception) as e:
            # Catch any exception during the process
            raise OSError(f"无法移动文件 '{path}' 到回收站: {e}")

    def move_entry(self, entry_path_str, target_category):
        """Move an entry file to a different category (within root_dir)."""
        entry_path = Path(entry_path_str)
        if not entry_path.exists() or not entry_path.is_file():
            raise FileNotFoundError(f"源文件不存在: {entry_path_str}")
        if self.trash_dir in entry_path.parents:
            raise ValueError("不能从此方法移出回收站中的文件。")

        if target_category == "_trash":
            raise ValueError("不能使用 'move' 直接将条目移动到回收站。请使用 'delete'。")

        target_category_path = self.root_dir / target_category
        # MODIFICATION: Create category if it doesn't exist during move
        if not target_category_path.exists():
            try:
                self.add_category(target_category)  # Also adds to self.categories
            except (ValueError, OSError) as e:
                raise OSError(f"无法创建目标分类 '{target_category}' 以进行移动: {e}")
        elif target_category not in self.categories:
            # Dir exists but not in list, add it
            self.categories.append(target_category)
            self.categories.sort()

        new_path = target_category_path / entry_path.name  # Keep the original filename

        # Check for conflict in target directory
        if new_path.exists():
            # Maybe allow overwrite or rename? For now, raise error.
            raise FileExistsError(f"目标位置已存在同名文件: {new_path}")

        try:
            shutil.move(str(entry_path), str(new_path))  # Use shutil.move for robustness
            return str(new_path)
        except Exception as e:  # Catch potential errors from shutil.move
            raise OSError(f"无法移动文件 '{entry_path}' 到 '{new_path}': {e}")

    def search(self, query, categories=None):
        """Search content across specified categories (or all). Case-insensitive."""
        results = []
        search_query = query.lower().strip()
        if not search_query:
            return results

        search_categories = categories if categories is not None else self.categories

        for category in search_categories:
            category_path = self.root_dir / category
            if not category_path.is_dir():  # Check if it's a directory
                continue

            # MODIFICATION: Search *.md files only by default, could be made configurable
            for file_path in category_path.glob("*.md"):
                try:
                    # Read metadata first (for title) without full content if possible
                    entry_data = self.get_entry_by_path(file_path, read_content=False)  # Read only metadata first
                    title = file_path.stem  # Fallback title
                    if entry_data and entry_data.get("metadata") and entry_data["metadata"].get("title"):
                        title = entry_data["metadata"]["title"]

                    # Check title match
                    title_match = search_query in title.lower()

                    # If title matches, add result immediately
                    if title_match:
                        results.append({
                            "category": category,
                            "title": title,
                            "path": str(file_path)
                        })
                        continue  # Move to next file

                    # If title didn't match, read content and check
                    # Reread with content this time
                    entry_data_full = self.get_entry_by_path(file_path, read_content=True)
                    content = entry_data_full.get("content", "") if entry_data_full else ""

                    if search_query in content.lower():
                        results.append({
                            "category": category,
                            "title": title,
                            "path": str(file_path)
                        })

                except Exception as e:
                    print(f"Error reading or processing file {file_path} during search: {e}")
                    continue  # Skip file on error

        # MODIFICATION: Sort search results for consistency (by category then title)
        results.sort(key=lambda x: (x["category"].lower(), x["title"].lower()))
        return results

    def get_entry_by_path(self, file_path_str, read_content=True):
        """Get entry data (metadata and optionally content) from a specific file path."""
        path = Path(file_path_str)
        if not path.exists() or not path.is_file():
            print(f"get_entry_by_path: File not found {path}")
            return None

        try:
            full_content = path.read_text(encoding="utf-8")
        except OSError as e:
            print(f"Error reading file {path}: {e}")
            return None
        except Exception as e:  # Catch other potential errors like UnicodeDecodeError
            print(f"Error processing file {path}: {e}")
            return None  # Or handle encoding issues more gracefully if needed

        # Default metadata with title from filename stem (before extension)
        metadata = {"title": path.stem}
        content_text = full_content  # Default content if no metadata block

        # Robustly parse metadata block
        if full_content.startswith("---"):
            # Match ---, optional whitespace, newline, content, newline, ---, optional whitespace, newline
            match = re.match(r"^---\s*?\n(.*?)\n^---\s*?\n?(.*)", full_content, re.MULTILINE | re.DOTALL)
            if match:
                metadata_str = match.group(1).strip()
                content_text = match.group(2).strip()  # The rest is content
                try:
                    loaded_meta = json.loads(metadata_str)
                    if isinstance(loaded_meta, dict):
                        # Ensure title from metadata is used, fallback to filename stem if empty or missing
                        if "title" not in loaded_meta or not loaded_meta["title"]:
                            loaded_meta["title"] = path.stem  # Use stem if title in JSON is missing/empty
                        metadata = loaded_meta  # Use loaded metadata
                    else:
                        print(f"Warning: Metadata block in {path} is not a JSON object.")
                        # Keep default metadata (title=stem) if JSON isn't a dict
                except json.JSONDecodeError as json_e:
                    print(f"Warning: Invalid JSON metadata in {path}: {json_e}")
                    # Keep default metadata (title=stem) if JSON parsing fails
            else:
                # Found '---' at start, but not the closing '---', treat all as content? Or log warning?
                print(f"Warning: Malformed metadata block (missing closing '---') in {path}. Treating all as content.")
                content_text = full_content  # Revert to full content

        entry_data = {
            "metadata": metadata,
            "path": str(path)
        }
        if read_content:
            entry_data["content"] = content_text

        return entry_data

    def list_entries(self, category):
        """List titles and paths of entries in a category, sorted by title."""
        entries = []
        category_path = self.root_dir / category
        if not category_path.is_dir():  # Check if it's a directory
            return entries  # Category doesn't exist or is not a directory

        # MODIFICATION: Glob for *.md files
        for file_path in category_path.glob("*.md"):
            entry_data = self.get_entry_by_path(file_path, read_content=False)  # Only need metadata
            title = file_path.stem  # Default title from filename stem
            if entry_data and entry_data.get("metadata") and entry_data["metadata"].get("title"):
                title = entry_data["metadata"]["title"]  # Use title from metadata

            entries.append({"title": title, "path": str(file_path)})

        # Sort entries alphabetically by title (case-insensitive)
        entries.sort(key=lambda x: x["title"].lower())
        return entries

    def add_category(self, new_category):
        """Add a new category (directory) and update the internal list."""
        clean_category = new_category.strip()
        if not clean_category:
            raise ValueError("分类名称不能为空。")
        if clean_category == "_trash":
            raise ValueError("分类名称 '_trash' 是保留名称。")
        # MODIFICATION: Stricter check for invalid chars in category name
        if re.search(r'[<>:"/\\|?*]', clean_category) or any(ord(c) < 32 for c in clean_category):
            raise ValueError(f"分类名称 '{clean_category}' 包含无效字符或控制字符。")

        if clean_category not in self.categories:
            try:
                (self.root_dir / clean_category).mkdir(exist_ok=True)  # Create directory
                self.categories.append(clean_category)
                self.categories.sort()  # Keep sorted
                return True
            except OSError as e:
                raise OSError(f"无法创建分类目录 '{clean_category}': {e}")
        else:
            # Category already exists in list, ensure directory exists too
            (self.root_dir / clean_category).mkdir(exist_ok=True)
            return False  # Indicate it already existed

    def remove_category(self, category):
        """Move a category directory and its contents to the trash."""
        if category in self.categories:
            category_path = self.root_dir / category
            if category_path.is_dir():  # Ensure it's a directory
                try:
                    # Define trash path, handle collisions
                    target_trash_path = self.trash_dir / category_path.name
                    counter = 0
                    # MODIFICATION: Handle collision with file or dir in trash
                    while target_trash_path.exists():  # Handle name collision
                        counter += 1
                        target_trash_path = self.trash_dir / f"{category_path.name}_{counter}"

                    shutil.move(str(category_path), str(target_trash_path))  # Move directory
                    self.categories.remove(category)  # Update internal list
                    print(f"Moved category to trash: {target_trash_path}")
                    return True
                except Exception as e:  # Catch potential shutil errors
                    raise OSError(f"无法移动分类目录 '{category_path}' 到回收站: {e}")
            else:
                # Directory doesn't exist, but it's in the list? Remove from list.
                print(f"Warning: Category '{category}' found in list but directory missing. Removing from list.")
                self.categories.remove(category)
                return True  # Considered successful removal from list
        else:
            # MODIFICATION: Raise error if category not in list
            raise ValueError(f"分类 '{category}' 不在已知列表中。")

    def rename_category(self, current_name, new_name):
        """Rename a category directory and update the internal list."""
        clean_new_name = new_name.strip()
        if not clean_new_name:
            raise ValueError("新分类名称不能为空。")
        if clean_new_name == current_name:
            return True  # No change needed
        if clean_new_name == "_trash":
            raise ValueError("新分类名称 '_trash' 是保留名称。")
        if clean_new_name in self.categories:
            raise ValueError(f"目标分类名称 '{clean_new_name}' 已存在。")
        # MODIFICATION: Stricter check for invalid chars
        if re.search(r'[<>:"/\\|?*]', clean_new_name) or any(ord(c) < 32 for c in clean_new_name):
            raise ValueError(f"新分类名称 '{clean_new_name}' 包含无效字符或控制字符。")
        if current_name not in self.categories:
            raise ValueError(f"源分类 '{current_name}' 不存在。")

        old_path = self.root_dir / current_name
        new_path = self.root_dir / clean_new_name

        # Check if directory physically exists before trying to rename
        if not old_path.is_dir():
            print(f"Warning: Directory for category '{current_name}' not found. Renaming in list only.")
            # Just rename in the list if directory is missing
            self.categories[self.categories.index(current_name)] = clean_new_name
            self.categories.sort()
            return True

        # Check if target path exists (should be covered by 'in self.categories' check, but belt-and-suspenders)
        if new_path.exists():
            raise FileExistsError(f"目标分类目录 '{clean_new_name}' 已物理存在。")

        try:
            shutil.move(str(old_path), str(new_path))  # Use shutil.move for rename
            self.categories[self.categories.index(current_name)] = clean_new_name  # Update category list
            self.categories.sort()  # Keep sorted
            return True
        except Exception as e:
            raise OSError(f"无法重命名分类 '{current_name}' 为 '{clean_new_name}': {e}")

    # --- Trash Management Methods ---

    def list_trash(self):
        """List all items (files and directories) directly inside the trash directory."""
        if not self.trash_dir.exists():
            return []
        # Use list comprehension for cleaner syntax
        # MODIFICATION: Filter out potentially problematic files like .DS_Store
        return sorted([p for p in self.trash_dir.iterdir() if p.name != ".DS_Store"], key=lambda p: p.name)

    def restore_trash_item(self, trash_path_str):
        """Restore a single item (file or directory) from the trash."""
        trash_path = Path(trash_path_str)
        if not trash_path.exists() or self.trash_dir not in trash_path.parents:
            raise FileNotFoundError(f"回收站项目不存在或路径无效: {trash_path}")

        target_path = None  # Initialize target path

        if trash_path.is_file() and trash_path.suffix == ".md":
            # Try to restore file to original category based on metadata
            entry_data = self.get_entry_by_path(trash_path, read_content=False)  # Read meta first
            original_category = None
            if entry_data and "metadata" in entry_data:
                original_category = entry_data["metadata"].get("_original_category")

            # MODIFICATION: Cleaner logic for determining target category
            if original_category and original_category != "_trash":
                target_category_path = self.root_dir / original_category
                # Create category dir if it doesn't exist & add to list
                if not target_category_path.exists():
                    print(f"Info: Creating missing category '{original_category}' during restore.")
                    try:
                        self.add_category(original_category)  # Creates dir and adds to list
                    except Exception as e:
                        print(f"Warning: Failed to recreate category '{original_category}': {e}. Restoring to root.")
                        target_category_path = self.root_dir  # Fallback to root
                elif original_category not in self.categories:
                    # Add to list if dir exists but wasn't listed
                    self.categories.append(original_category)
                    self.categories.sort()

            else:
                # If no original category metadata, restore to root
                print(f"Warning: Original category not found for {trash_path.name}. Restoring to root.")
                target_category_path = self.root_dir

            # Attempt to reconstruct original filename (strip timestamp and potential counter)
            # Regex matches YYYYMMDD_HHMMSS_ (timestamp) and optionally _<counter>_ before the main name
            original_filename_match = re.match(r"^\d{8}_\d{6}(?:_\d+)?_(.*)", trash_path.name)
            if original_filename_match:
                base_filename = original_filename_match.group(1)
                target_path = target_category_path / base_filename
            else:
                # Fallback: use current name (might include timestamp) if regex fails
                print(f"Warning: Could not parse original filename from {trash_path.name}. Using full name.")
                target_path = target_category_path / trash_path.name


        elif trash_path.is_dir():
            # Restore directory to the root level
            category_name = trash_path.name
            # MODIFICATION: Strip potential counter suffix (_1, _2 etc) from dir name
            category_name = re.sub(r'_\d+$', '', category_name)
            target_path = self.root_dir / category_name  # Use potentially cleaned name

            # Add category back to list if it doesn't exist (use original trash_path.name for check)
            if trash_path.name not in self.categories and category_name not in self.categories:
                # Only add if neither the original nor cleaned name is present
                if not (self.root_dir / category_name).exists():  # Check if cleaned name dir exists
                    self.categories.append(category_name)  # Add cleaned name to list
                    self.categories.sort()
                else:
                    print(f"Info: Directory '{category_name}' already exists, adding to category list if needed.")
                    if category_name not in self.categories:
                        self.categories.append(category_name)
                        self.categories.sort()


        else:
            # Not a .md file or directory, restore to root? Or raise error?
            print(f"Warning: Unsupported item type in trash: {trash_path.name}. Restoring to root.")
            target_path = self.root_dir / trash_path.name

        # Handle potential name collisions at the target location
        if target_path:
            counter = 0
            original_target_path = target_path
            while target_path.exists():
                counter += 1
                if original_target_path.is_dir():
                    # Append counter to directory name
                    target_path = original_target_path.parent / f"{original_target_path.name}_{counter}"
                else:  # File
                    # Append counter before suffix
                    target_path = original_target_path.parent / f"{original_target_path.stem}_{counter}{original_target_path.suffix}"

            # Perform the move
            try:
                shutil.move(str(trash_path), str(target_path))
                print(f"Restored '{trash_path.name}' to '{target_path}'")

                # Clean up metadata in the restored file (remove trash-specific keys)
                if target_path.is_file() and target_path.suffix == ".md":
                    self._cleanup_restored_metadata(target_path)

                return str(target_path)
            except Exception as e:
                raise OSError(f"无法恢复项目 '{trash_path.name}' 到 '{target_path}': {e}")
        else:
            raise ValueError(f"无法确定项目 '{trash_path.name}' 的恢复位置。")

    def _cleanup_restored_metadata(self, file_path):
        """Remove internal trash metadata keys from a restored file."""
        try:
            entry_data = self.get_entry_by_path(file_path, read_content=True)
            # MODIFICATION: Ensure metadata exists before trying to pop
            if entry_data and isinstance(entry_data.get("metadata"), dict):
                metadata = entry_data["metadata"]
                # Use pop with default None to avoid KeyError if keys don't exist
                metadata.pop("_original_category", None)
                metadata.pop("_deleted_at", None)
                content = entry_data.get("content", "")

                # Re-save the file with cleaned metadata
                file_content = f"---\n{json.dumps(metadata, ensure_ascii=False, indent=2)}\n---\n\n{content}"
                file_path.write_text(file_content, encoding="utf-8")
            elif entry_data:
                print(f"Info: No metadata dictionary found in {file_path} during cleanup.")

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
                shutil.rmtree(trash_path)  # Use rmtree for directories
                print(f"Permanently deleted directory: {trash_path}")
            else:
                # Handle other potential file types like symlinks if necessary
                trash_path.unlink()  # Default attempt
                print(f"Permanently deleted item: {trash_path}")
            return True
        except Exception as e:
            raise OSError(f"无法永久删除回收站项目 '{trash_path.name}': {e}")

    def empty_trash(self):
        """Permanently delete all items in the trash directory."""
        deleted_count = 0
        errors = []
        trash_items = self.list_trash()  # Get current items

        if not trash_items:
            return 0, []  # Nothing to delete

        for item_path in trash_items:
            try:
                self.permanently_delete_trash_item(str(item_path))  # Reuse single item deletion
                deleted_count += 1
            except Exception as e:
                errors.append(f"无法删除 '{item_path.name}': {e}")

        print(
            f"Emptied trash. Attempted deletion for {len(trash_items)} items. Successfully deleted {deleted_count} items.")
        if errors:
            print("Errors occurred during empty trash:", errors)
        return deleted_count, errors


# --- Frontend GUI (NovelManagerGUI) ---
class NovelManagerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("网文创作助手 V2.1 (带回收站和搜索)")
        # MODIFICATION: Adjusted default size
        self.root.geometry("1200x800")

        self.manager = NovelManager()

        # State variables
        self.current_category = None
        self.current_entry_path = None  # Path of the entry currently loaded in the editor
        self.entry_data_map = {}  # Maps display title in listbox to actual path
        self.is_search_active = False  # Flag to track if entry list shows search results

        self._setup_style()
        self._create_menu()
        self._create_ui()  # MODIFICATION: This now creates the PanedWindow layout

        # Load initial data
        self.load_categories()

        # Apply theme if sv_ttk is available
        if sv_ttk:
            try:
                # MODIFICATION: Use default light/dark based on system preference if possible
                if root.tk.call("tk", "windowingsystem") == "aqua":  # macOS
                    try:
                        root.tk.call('source', os.path.join(sv_ttk.sv_ttk_path, 'sv_ttk_checker.tcl'))
                        theme = root.tk.call('::sv_ttk::get_theme')
                        self.switch_theme(theme)
                        print(f"Detected macOS theme: {theme}")
                    except tk.TclError:
                        self.switch_theme("light")  # Fallback for macOS
                        print("Could not detect macOS theme, defaulting to light.")
                else:
                    # Default to dark on other systems for now
                    self.switch_theme("dark")
            except Exception as e:
                print(f"Error setting initial theme: {e}")
                self.switch_theme("dark")  # Fallback

    def _setup_style(self):
        """Setup styles using sv-ttk if available."""
        if sv_ttk:
            # sv_ttk applies theme globally. Specific styling via ttk.Style is possible but use sparingly.
            style = ttk.Style()
            # MODIFICATION: Increase sash thickness for better grabbing
            try:
                # Check if TPanedwindow style exists before configuring
                if "TPanedwindow" in style.layout("."):  # A way to check if base style exists
                    style.configure("TPanedwindow", sashwidth=6, sashrelief=tk.RAISED, sashthickness=8)
                # Alternatively, configure specific pane style if needed:
                # style.configure("custom.TPanedwindow", sashwidth=6, sashrelief=tk.RAISED, sashthickness=8)
                # And apply style='custom.TPanedwindow' when creating PanedWindow
            except tk.TclError as e:
                print(f"Warning: Could not configure Panedwindow style - {e}")

            # Make Listbox background match theme slightly better (optional)
            # style.map("TListbox", background=[('!disabled', style.lookup('TFrame', 'background'))])

        # Configure Listbox selection background (works without svttk too)
        style = ttk.Style()  # Get style object again
        style.map("TListbox",
                  selectbackground=[('focus', style.lookup('TEntry', 'selectbackground'))],
                  selectforeground=[('focus', style.lookup('TEntry', 'selectforeground'))]
                  )

    def _create_menu(self):
        """Create the application menu."""
        menubar = Menu(self.root)
        self.root.config(menu=menubar)

        # --- File Menu ---
        file_menu = Menu(menubar, tearoff=0)
        menubar.add_cascade(label="文件", menu=file_menu)
        file_menu.add_command(label="新建分类...", command=self.on_new_category)
        # MODIFICATION: Changed label for clarity
        file_menu.add_command(label="新建条目 (在选中分类中)", command=self.on_new_entry)
        # Adicionar opção de atualização
        file_menu.add_command(label="刷新文件系统", command=self.on_refresh)
        file_menu.add_separator()
        # Trash Submenu
        trash_menu = Menu(file_menu, tearoff=0)
        file_menu.add_cascade(label="回收站", menu=trash_menu)
        trash_menu.add_command(label="查看回收站...", command=self.on_view_trash)
        trash_menu.add_command(label="清空回收站...", command=self.on_empty_trash)

        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self.root.quit)

        # --- View Menu ---
        view_menu = Menu(menubar, tearoff=0)
        menubar.add_cascade(label="视图", menu=view_menu)
        # Theme Submenu (only if sv_ttk loaded)
        if sv_ttk:
            theme_menu = Menu(view_menu, tearoff=0)
            view_menu.add_cascade(label="主题", menu=theme_menu)
            theme_menu.add_command(label="深色", command=lambda: self.switch_theme("dark"))
            theme_menu.add_command(label="浅色", command=lambda: self.switch_theme("light"))
        # Add other view options here if needed (e.g., font size)

    # MODIFICATION: Main UI creation using PanedWindows for 3 columns
    def _create_ui(self):
        """Create the main user interface using PanedWindows."""
        # Overall structure: Horizontal PanedWindow (Left Pane | Right Main Pane)
        self.main_h_pane = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)  # style="custom.TPanedwindow" if needed
        self.main_h_pane.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)  # Reduced padding

        # --- Left Pane (Categories) ---
        self.frame_left = self._create_left_pane(self.main_h_pane)
        self.main_h_pane.add(self.frame_left, weight=1)  # Smaller initial weight

        # --- Right Main Pane (will contain Middle and Right panes) ---
        # Nested Horizontal PanedWindow: (Middle Pane | Right Pane)
        self.right_h_pane = ttk.PanedWindow(self.main_h_pane,
                                            orient=tk.HORIZONTAL)  # style="custom.TPanedwindow" if needed
        self.main_h_pane.add(self.right_h_pane, weight=5)  # Larger initial weight for the right side combined

        # --- Middle Pane (Entries/Search) ---
        self.frame_middle = self._create_middle_pane(self.right_h_pane)
        self.right_h_pane.add(self.frame_middle, weight=2)  # Medium weight within the right side

        # --- Right Pane (Editor) ---
        self.frame_right = self._create_right_pane(self.right_h_pane)
        self.right_h_pane.add(self.frame_right, weight=4)  # Larger weight for editor within the right side

    # MODIFICATION: Updated Left Pane creation with buttons
    def _create_left_pane(self, parent):
        """Creates the category list pane."""
        frame = ttk.Frame(parent, padding=5)  # Add padding to the frame itself

        ttk.Label(frame, text="分类列表", font=("Segoe UI", 11, "bold")).pack(pady=(0, 5), anchor=tk.W)  # Adjusted font

        # Listbox with Scrollbar
        list_frame = ttk.Frame(frame)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 5))

        cat_scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL)
        # MODIFICATION: Use ttk.Listbox if possible, but standard Tk Listbox works well here
        self.category_listbox = tk.Listbox(list_frame, exportselection=False, relief=tk.FLAT,
                                           yscrollcommand=cat_scrollbar.set, borderwidth=1)  # Added border
        cat_scrollbar.config(command=self.category_listbox.yview)

        cat_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.category_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.category_listbox.bind("<<ListboxSelect>>", self.on_category_select)
        self.category_listbox.bind("<Button-3>", self.show_category_menu)  # Right-click

        # MODIFICATION: Category Buttons Frame
        cat_button_frame = ttk.Frame(frame)
        cat_button_frame.pack(fill=tk.X, pady=(5, 0))
        ttk.Button(cat_button_frame, text="新建分类", command=self.on_new_category).pack(side=tk.LEFT, padx=(0, 5))
        # Adicionar botão de atualização
        ttk.Button(cat_button_frame, text="刷新", command=self.on_refresh, width=5).pack(side=tk.RIGHT)
        # Delete button removed here, context menu is better for specific item deletion
        # ttk.Button(cat_button_frame, text="删除选中", command=self.on_delete_selected_category).pack(side=tk.LEFT)

        # Right-click context menu for categories
        self.category_menu = Menu(self.root, tearoff=0)

        # Allow frame contents (listbox, buttons) to resize correctly
        frame.rowconfigure(1, weight=1)  # Let list_frame expand
        frame.columnconfigure(0, weight=1)

        return frame

    # MODIFICATION: Updated Middle Pane creation with buttons
    def _create_middle_pane(self, parent):
        """Creates the entry list / search result pane."""
        frame = ttk.Frame(parent, padding=5)

        # --- Search Bar ---
        search_frame = ttk.Frame(frame)
        search_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(search_frame, text="搜索:").pack(side=tk.LEFT, padx=(0, 5))
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        search_entry.bind("<Return>", self.on_search)  # Allow Enter key to search
        # MODIFICATION: Smaller search buttons
        ttk.Button(search_frame, text="搜", command=self.on_search, width=3).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(search_frame, text="清", command=self.on_clear_search, width=3).pack(side=tk.LEFT)

        # --- List Label (changes based on context) ---
        self.entry_list_label = ttk.Label(frame, text="条目列表", font=("Segoe UI", 11, "bold"))  # Adjusted font
        self.entry_list_label.pack(pady=(0, 5), anchor=tk.W)

        # --- Entry Listbox ---
        list_frame = ttk.Frame(frame)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 5))

        entry_scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL)
        # MODIFICATION: Use tk.Listbox, added border, enabled extended selection
        self.entry_listbox = tk.Listbox(list_frame, exportselection=False, selectmode=tk.EXTENDED, relief=tk.FLAT,
                                        yscrollcommand=entry_scrollbar.set, borderwidth=1)
        entry_scrollbar.config(command=self.entry_listbox.yview)

        entry_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.entry_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.entry_listbox.bind("<<ListboxSelect>>", self.on_entry_select)
        self.entry_listbox.bind("<Button-3>", self.show_entry_menu)  # Right-click
        # MODIFICATION: Double click to edit
        self.entry_listbox.bind("<Double-Button-1>", self.on_edit_selected_entry)

        # MODIFICATION: Entry Buttons Frame
        entry_buttons_frame = ttk.Frame(frame)
        entry_buttons_frame.pack(fill=tk.X, pady=(5, 0))
        ttk.Button(entry_buttons_frame, text="新建条目", command=self.on_new_entry).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(entry_buttons_frame, text="删除选中", command=self.on_delete_selected_entries).pack(side=tk.LEFT,
                                                                                                       padx=(0, 5))
        ttk.Button(entry_buttons_frame, text="移动选中", command=self.on_move_selected_entries).pack(side=tk.LEFT)

        # Right-click context menu for entries
        self.entry_menu = Menu(self.root, tearoff=0)

        # Allow frame contents (search, listbox, buttons) to resize correctly
        frame.rowconfigure(2, weight=1)  # Let list_frame expand
        frame.columnconfigure(0, weight=1)

        return frame

    # MODIFICATION: Updated Right Pane (Editor) with vertical split
    def _create_right_pane(self, parent):
        """Creates the editor pane with Title/Tags/Info and Content."""
        frame = ttk.Frame(parent, padding=5)
        # Removed top "编辑区" label, implied by context

        # Use a PanedWindow for vertical split within the editor
        # style="custom.TPanedwindow" if needed
        editor_v_pane = ttk.PanedWindow(frame, orient=tk.VERTICAL)
        editor_v_pane.pack(fill=tk.BOTH, expand=True, pady=(0, 5))  # Add padding below v_pane

        # --- Top Editor Part (Title, Tags, Info) ---
        # Increased padding slightly for better separation
        editor_top_frame = ttk.Frame(editor_v_pane, padding=(5, 5, 5, 10))
        editor_v_pane.add(editor_top_frame, weight=0)  # Give top part fixed height initially

        # Title Entry
        title_frame = ttk.Frame(editor_top_frame)
        title_frame.pack(fill=tk.X, pady=(0, 2))  # Reduced padding
        ttk.Label(title_frame, text="标题:", width=5, anchor=tk.W).pack(side=tk.LEFT, padx=(0, 5))  # Fixed width
        self.title_var = tk.StringVar()
        ttk.Entry(title_frame, textvariable=self.title_var, font=("Segoe UI", 10)).pack(side=tk.LEFT, fill=tk.X,
                                                                                        expand=True)

        # Tags Entry
        tags_frame = ttk.Frame(editor_top_frame)
        tags_frame.pack(fill=tk.X, pady=(2, 5))
        ttk.Label(tags_frame, text="标签:", width=5, anchor=tk.W).pack(side=tk.LEFT, padx=(0, 5))  # Fixed width
        self.tags_var = tk.StringVar()
        ttk.Entry(tags_frame, textvariable=self.tags_var, font=("Segoe UI", 10)).pack(side=tk.LEFT, fill=tk.X,
                                                                                      expand=True)
        ttk.Label(tags_frame, text="(逗号分隔)", font=("Segoe UI", 8, "italic")).pack(side=tk.LEFT,
                                                                                      padx=(5, 0))  # Adjusted font

        # Info Label (Created/Updated dates)
        self.info_label_var = tk.StringVar(value="未加载条目")
        info_label = ttk.Label(editor_top_frame, textvariable=self.info_label_var, font=("Segoe UI", 8),
                               foreground="grey")  # Adjusted font
        info_label.pack(anchor=tk.W, pady=(5, 0))

        # --- Bottom Editor Part (Content) ---
        editor_bottom_frame = ttk.Frame(editor_v_pane, padding=(5, 5, 5, 0))  # Padding around content
        editor_v_pane.add(editor_bottom_frame, weight=1)  # Give content area expansion weight

        # Removed "内容:" label, it's obvious
        # ttk.Label(editor_bottom_frame, text="内容:").pack(anchor=tk.W, pady=(0, 2))

        # Use bd=1 and relief=tk.SUNKEN (or FLAT with theme) for subtle border
        # Increased font size slightly
        self.content_text = scrolledtext.ScrolledText(
            editor_bottom_frame, height=15, width=70, wrap=tk.WORD, undo=True,
            relief=tk.SUNKEN, bd=1,  # Give it a slight border
            font=("Segoe UI", 10)  # Set content font
        )
        self.content_text.pack(fill=tk.BOTH, expand=True)  # Fill the bottom frame

        # Save Button (Placed below the vertical pane now)
        ttk.Button(frame, text="保存", command=self.on_save).pack(pady=5, fill=tk.X)

        # Allow frame contents (v_pane, save button) to resize
        frame.rowconfigure(0, weight=1)  # Let editor_v_pane expand
        frame.columnconfigure(0, weight=1)

        return frame

    # --- Data Loading and UI Update ---

    def load_categories(self):
        """Load/reload categories into the listbox and maintain selection."""
        selected_category = self.current_category
        try:
            self.manager.categories = self.manager._load_categories()  # Reload from disk
        except Exception as e:
            messagebox.showerror("错误", f"加载分类列表时出错: {e}", parent=self.root)
            self.manager.categories = []  # Reset if load fails

        # Store selection index before clearing
        selected_idx = None
        if selected_category:
            try:
                # Find index before list is cleared
                items = list(self.category_listbox.get(0, tk.END))
                selected_idx = items.index(selected_category)
            except ValueError:
                selected_idx = None  # Category disappeared

        self.category_listbox.delete(0, tk.END)
        for category in self.manager.categories:
            self.category_listbox.insert(tk.END, category)

        # Try to restore selection by text first, then by index
        restored = False
        if selected_category and selected_category in self.manager.categories:
            if self._select_listbox_item_by_text(self.category_listbox, selected_category):
                self.current_category = selected_category  # Ensure it's set
                restored = True
        # Fallback to index if text selection failed but index was valid
        if not restored and selected_idx is not None and selected_idx < self.category_listbox.size():
            try:
                self.category_listbox.selection_set(selected_idx)
                self.category_listbox.activate(selected_idx)
                self.current_category = self.category_listbox.get(selected_idx)
                self.on_category_select(None)  # Trigger load for this category
                restored = True
            except tk.TclError:
                pass  # Ignore potential error setting selection

        if not restored:
            # If selection couldn't be restored, select first or clear
            if self.manager.categories:
                self.category_listbox.selection_set(0)
                self.on_category_select(None)  # Trigger load
            else:
                self.current_category = None
                self.load_entries(None)  # Clear entry list
                self.clear_editor()

    def load_entries(self, category):
        """Load entries for the selected category into the listbox."""
        self.entry_listbox.delete(0, tk.END)
        self.entry_data_map.clear()
        self.is_search_active = False  # Loading category entries means search is off
        self.entry_list_label.config(text="条目列表")  # Reset label
        self.entry_listbox.config(state=tk.NORMAL)  # Ensure enabled

        if category and category in self.manager.categories:
            try:
                entries = self.manager.list_entries(category)
                for entry in entries:
                    display_title = entry["title"]  # Use title from metadata/list_entries
                    self.entry_listbox.insert(tk.END, display_title)
                    self.entry_data_map[display_title] = entry["path"]

                # MODIFICATION: Do not auto-select first entry, clear editor instead
                if not entries:
                    self.entry_listbox.config(state=tk.DISABLED)
                    self.clear_editor()
                else:
                    # Clear editor when category loaded, wait for user selection
                    self.clear_editor()

            except Exception as e:
                messagebox.showerror("错误", f"加载分类 '{category}' 的条目时出错: {e}", parent=self.root)
                self.clear_editor()

        else:  # No category selected or category is invalid
            self.entry_listbox.insert(tk.END, "(请先选择分类)")
            self.entry_listbox.config(state=tk.DISABLED)
            self.clear_editor()

    def load_search_results(self, results):
        """Load search results into the entry listbox."""
        self.entry_listbox.delete(0, tk.END)
        self.entry_data_map.clear()
        self.is_search_active = True
        self.entry_list_label.config(text="搜索结果")  # Update label
        self.entry_listbox.config(state=tk.NORMAL)  # Ensure enabled

        if results:
            for result in results:
                # Format: [Category] Title
                display_text = f"[{result['category']}] {result['title']}"
                self.entry_listbox.insert(tk.END, display_text)
                # Map the display text to the path for loading
                self.entry_data_map[display_text] = result['path']
            # MODIFICATION: Clear editor when showing search results, wait for selection
            self.clear_editor()
        else:
            self.entry_listbox.insert(tk.END, "无匹配结果")
            self.entry_listbox.config(state=tk.DISABLED)  # Disable list if no results
            self.clear_editor()

    def clear_editor(self, keep_selection=False):
        """Clear all fields in the editor pane and reset state."""
        self.title_var.set("")
        self.tags_var.set("")
        # MODIFICATION: Check if widget exists before accessing
        if self.content_text.winfo_exists():
            self.content_text.delete(1.0, tk.END)
            try:
                # Reset undo stack only if widget exists
                self.content_text.edit_reset()
            except tk.TclError:
                pass  # Ignore error if widget is being destroyed

        self.info_label_var.set("未加载条目")
        self.current_entry_path = None  # Crucial: editor is not linked to a file path now

        # MODIFICATION: Clear listbox selection unless keep_selection is True
        if not keep_selection:
            if self.entry_listbox.winfo_exists():  # Check if widget exists
                try:
                    self.entry_listbox.selection_clear(0, tk.END)
                except tk.TclError:  # Handle potential errors if listbox is in weird state
                    pass

    def _update_info_label(self, metadata):
        """Update the small info label with dates."""
        created = metadata.get("created_at", "N/A")
        updated = metadata.get("updated_at", "N/A")
        # Try to parse ISO dates for nicer formatting
        created_str = created
        updated_str = updated
        try:
            # Only format if it looks like a valid ISO string
            if isinstance(created, str) and len(created) > 18:
                created_dt = datetime.datetime.fromisoformat(created.split('.')[0])  # Handle potential microseconds
                created_str = created_dt.strftime("%Y-%m-%d %H:%M")
            if isinstance(updated, str) and len(updated) > 18:
                updated_dt = datetime.datetime.fromisoformat(updated.split('.')[0])
                updated_str = updated_dt.strftime("%Y-%m-%d %H:%M")
        except (ValueError, TypeError) as e:
            print(f"Debug: Error parsing date for info label: {e}")
            # Fallback to raw string already assigned

        self.info_label_var.set(f"创建: {created_str} | 更新: {updated_str}")

    def _select_listbox_item_by_text(self, listbox, text_to_find, select=True):
        """Finds and optionally selects an item in a listbox by its exact text. Returns True if found."""
        listbox.update_idletasks()  # Ensure listbox is up-to-date
        items = listbox.get(0, tk.END)
        try:
            idx = items.index(text_to_find)
            if select:
                listbox.selection_clear(0, tk.END)
                listbox.selection_set(idx)
                listbox.activate(idx)
            listbox.see(idx)  # Scroll to the item
            return True  # Item found
        except ValueError:
            print(f"Debug: Item '{text_to_find}' not found in listbox.")
            return False  # Item not found

    # --- Event Handlers ---

    def on_category_select(self, event=None):
        """Handle category selection change."""
        # MODIFICATION: Check widget existence
        if not self.category_listbox.winfo_exists() or not self.category_listbox.curselection():
            # If no selection or widget destroyed, maybe clear entries?
            # self.load_entries(None)
            # self.clear_editor()
            return  # Avoid processing empty selections or during destruction

        try:
            index = self.category_listbox.curselection()[0]
            selected_category = self.category_listbox.get(index)  # Get text directly
        except (tk.TclError, IndexError):
            print("Debug: Error getting category selection (widget might be closing).")
            return  # Exit if selection is invalid

        # Only reload if category actually changed or if search was active
        if selected_category != self.current_category or self.is_search_active:
            print(f"Category selected: {selected_category}")
            self.current_category = selected_category
            self.load_entries(self.current_category)  # Load entries for this category
            # clear_editor() is called within load_entries now
            self.is_search_active = False  # Selecting a category turns off search mode

    def on_entry_select(self, event=None):
        """Handle entry selection: load data into the editor. Supports single selection view."""
        # MODIFICATION: Check widget existence
        if not self.entry_listbox.winfo_exists():
            return

        selected_indices = self.entry_listbox.curselection()

        if len(selected_indices) == 1:
            index = selected_indices[0]
            try:
                selected_display_text = self.entry_listbox.get(index)
            except tk.TclError:
                print("Debug: Error getting entry selection (widget might be closing).")
                return  # Exit if cannot get text

            # Handle case where listbox might contain placeholder text (e.g., "empty", "no results")
            if selected_display_text.startswith("(") or self.entry_listbox.cget("state") == tk.DISABLED:
                self.clear_editor(keep_selection=True)  # Keep placeholder selected but clear editor
                return

            entry_path = self.entry_data_map.get(selected_display_text)

            # MODIFICATION: More robust check for path and file existence
            valid_path = False
            if entry_path:
                try:
                    path_obj = Path(entry_path)
                    if path_obj.is_file():  # Check if it's a file specifically
                        valid_path = True
                except Exception as e:
                    print(f"Error checking path '{entry_path}': {e}")

            if valid_path:
                print(f"Loading entry: {entry_path}")
                try:
                    entry_data = self.manager.get_entry_by_path(entry_path, read_content=True)  # Read full data
                    if entry_data:
                        self.current_entry_path = entry_data["path"]  # Store the loaded path
                        metadata = entry_data.get("metadata", {})
                        content = entry_data.get("content", "")

                        self.title_var.set(
                            metadata.get("title", Path(entry_path).stem))  # Use metadata title, fallback to stem
                        self.tags_var.set(", ".join(metadata.get("tags", [])))
                        self.content_text.delete(1.0, tk.END)
                        self.content_text.insert(tk.END, content)
                        self._update_info_label(metadata)
                        self.content_text.edit_reset()  # Reset undo history
                    else:
                        # This case means get_entry_by_path returned None (e.g., read error)
                        messagebox.showerror("错误", f"无法读取条目数据:\n{entry_path}", parent=self.root)
                        self.clear_editor()
                except Exception as e:
                    messagebox.showerror("错误", f"加载条目时发生意外错误:\n{entry_path}\n{e}", parent=self.root)
                    self.clear_editor()
            else:
                messagebox.showerror("错误", f"条目文件丢失或映射无效: {selected_display_text}\n预期路径: {entry_path}",
                                     parent=self.root)
                # Attempt to remove the stale entry from listbox and map
                if selected_display_text in self.entry_data_map:
                    del self.entry_data_map[selected_display_text]
                try:
                    # Find index again in case it shifted
                    items = self.entry_listbox.get(0, tk.END)
                    stale_index = items.index(selected_display_text)
                    self.entry_listbox.delete(stale_index)
                except (ValueError, tk.TclError):
                    pass  # Ignore if deletion fails
                self.clear_editor()

        elif len(selected_indices) > 1:
            # Multiple items selected, clear the editor but keep listbox selection
            print(f"{len(selected_indices)} entries selected. Clearing editor.")
            self.clear_editor(keep_selection=True)
        else:
            # No items selected (or selection cleared), clear the editor
            print("No entry selected. Clearing editor.")
            self.clear_editor()

    def on_new_category(self):
        """Create a new category via dialog."""
        new_category = simpledialog.askstring("新建分类", "请输入新分类名称:", parent=self.root)
        if new_category:
            try:
                clean_name = new_category.strip()
                added = self.manager.add_category(clean_name)
                if added:
                    print(f"Category '{clean_name}' added.")
                    self.load_categories()  # Reload categories
                    # Select the newly added category
                    self._select_listbox_item_by_text(self.category_listbox, clean_name)
                    # Selection triggers on_category_select -> load_entries
                else:
                    # Category already exists, maybe select it?
                    messagebox.showinfo("信息", f"分类 '{clean_name}' 已存在。", parent=self.root)
                    self._select_listbox_item_by_text(self.category_listbox, clean_name)
                    # Selection should trigger load if not already selected
                    if self.current_category != clean_name:
                        self.on_category_select(None)
            except (ValueError, OSError) as e:
                messagebox.showerror("错误", f"无法创建分类:\n{str(e)}", parent=self.root)

    def on_rename_category(self):
        """Rename the selected category (triggered by context menu)."""
        if not self.category_listbox.curselection():
            # This check might be redundant if called only from context menu on selection
            messagebox.showwarning("选择分类", "请先右键点击一个要重命名的分类。", parent=self.root)
            return

        try:
            selected_index = self.category_listbox.curselection()[0]
            current_name = self.category_listbox.get(selected_index)
        except (tk.TclError, IndexError):
            messagebox.showerror("错误", "无法获取选中的分类。", parent=self.root)
            return

        new_name = simpledialog.askstring("重命名分类", f"请输入 '{current_name}' 的新名称:", initialvalue=current_name,
                                          parent=self.root)

        if new_name and new_name.strip() != current_name:
            clean_new_name = new_name.strip()
            try:
                renamed = self.manager.rename_category(current_name, clean_new_name)
                if renamed:
                    print(f"Category '{current_name}' renamed to '{clean_new_name}'.")
                    # Store current entry path before reload might clear it implicitly
                    path_before_reload = self.current_entry_path

                    # Update current_category *state* variable if it was the one renamed
                    if self.current_category == current_name:
                        self.current_category = clean_new_name

                    # Reload list and re-select the renamed item by its *new* name
                    self.load_categories()  # Reloads and attempts to reselect based on self.current_category
                    # Explicitly select again just in case load_categories logic didn't catch it
                    self._select_listbox_item_by_text(self.category_listbox, clean_new_name)

                    # Crucially, if the currently edited entry was in the renamed category,
                    # update its path state variable
                    if path_before_reload:
                        old_path = Path(path_before_reload)
                        if old_path.parent.name == current_name:  # Check if it was in the old category
                            new_path_str = str(self.manager.root_dir / clean_new_name / old_path.name)
                            self.current_entry_path = new_path_str
                            print(f"Updated current entry path to: {self.current_entry_path}")

                # Errors are raised by manager method
            except (ValueError, OSError, FileExistsError) as e:
                messagebox.showerror("重命名错误", f"无法重命名分类:\n{str(e)}", parent=self.root)

    def on_delete_selected_category(self):
        """Move the selected category to trash (triggered by context menu)."""
        if not self.category_listbox.curselection():
            messagebox.showwarning("选择分类", "请先右键点击一个要删除的分类。", parent=self.root)
            return

        try:
            selected_index = self.category_listbox.curselection()[0]
            selected_category = self.category_listbox.get(selected_index)
        except (tk.TclError, IndexError):
            messagebox.showerror("错误", "无法获取选中的分类。", parent=self.root)
            return

        if messagebox.askyesno("确认移至回收站",
                               f"确定要将分类 '{selected_category}' 及其所有内容移动到回收站吗？",
                               icon='warning', parent=self.root):
            try:
                # Store selection info before potential modification
                was_selected_category = (self.current_category == selected_category)

                removed = self.manager.remove_category(selected_category)  # This now moves to trash
                if removed:
                    print(f"Category '{selected_category}' moved to trash.")
                    messagebox.showinfo("成功", f"分类 '{selected_category}' 已移动到回收站。", parent=self.root)

                    # Reload category list FIRST
                    self.load_categories()  # Refresh list (will try to reselect previous or select first)

                    # If the deleted category was the selected one, the editor and entry list should be cleared
                    # load_categories handles selecting a new category or clearing if none left
                    if was_selected_category:
                        # load_categories should have selected a new category if available,
                        # or cleared things if no categories left. If a new category
                        # was selected, its entries were loaded (and editor cleared).
                        print("Deleted category was the current one. UI should have updated.")
                        pass  # Rely on load_categories logic

                # else: remove_category raises ValueError if category not found in list

            except (ValueError, OSError) as e:
                messagebox.showerror("删除错误", f"移动分类到回收站时出错:\n{str(e)}", parent=self.root)
                self.load_categories()  # Reload list even on error to reflect potential partial changes

    def on_new_entry(self):
        """Prepare the editor for creating a new entry in the current category."""
        if not self.current_category:
            messagebox.showwarning("选择分类", "请先在左侧选择一个分类以创建新条目。", parent=self.root)
            return

        # MODIFICATION: Clear editor AND deselect any entry in the list
        self.clear_editor(keep_selection=False)  # keep_selection=False ensures list selection is cleared

        self.title_var.set("新条目")  # Default title suggestion
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        # MODIFICATION: Simplified info label for new entry
        self.info_label_var.set(f"新条目 (将在 '{self.current_category}' 中创建)")
        self.content_text.focus_set()  # Focus content area
        print("Editor cleared for new entry in category:", self.current_category)

    # MODIFICATION: Handler for double-click and context menu "Edit"
    def on_edit_selected_entry(self, event=None):
        """Load the currently selected single entry into the editor."""
        # Ensure only one item is selected (double-click implies single)
        selected_indices = self.entry_listbox.curselection()
        if len(selected_indices) == 1:
            # Just trigger the standard selection logic which loads the editor
            self.on_entry_select(None)
        elif len(selected_indices) > 1:
            messagebox.showinfo("编辑条目", "请选择单个条目进行编辑。", parent=self.root)
        else:  # No item selected
            # This case shouldn't happen on double-click/context menu, but handle defensively
            pass

    # MODIFICATION: Refined save logic
    def on_save(self):
        """Save the current content in the editor (handles new entry creation or update)."""
        title = self.title_var.get().strip()
        if not title:
            messagebox.showwarning("需要标题", "标题不能为空。", parent=self.root)
            return

        content = self.content_text.get(1.0, tk.END).strip()  # Ensure \n at end is removed
        tags = [tag.strip() for tag in self.tags_var.get().split(",") if tag.strip()]

        category_to_save_in = None
        path_to_update = self.current_entry_path  # Path of entry being edited, if any

        if path_to_update:
            # Editing an existing entry. Save back to its original category.
            try:
                existing_path = Path(path_to_update)
                # Basic validation: Check if path looks like it's within our root structure
                if self.manager.root_dir in existing_path.parents and existing_path.parent.name != "_trash":
                    category_to_save_in = existing_path.parent.name
                else:
                    # Path seems weird (e.g., points outside root, or to trash), treat as potentially invalid
                    raise ValueError(f"现有路径无效或指向意外位置: {path_to_update}")

            except Exception as e:
                # If path is invalid, ask user how to proceed
                print(f"Error validating existing path '{path_to_update}': {e}")
                if messagebox.askyesno("保存路径无效",
                                       f"当前编辑条目的路径无效或已被移动。\n路径: {path_to_update}\n\n是否尝试在当前选中的分类 '{self.current_category}' 中保存为一个新条目？",
                                       parent=self.root):
                    if not self.current_category:
                        messagebox.showerror("无法保存", "没有选中的分类来保存新条目。", parent=self.root)
                        return
                    category_to_save_in = self.current_category
                    path_to_update = None  # Treat as a new save
                    print(f"Proceeding to save as NEW entry in: {category_to_save_in}")
                else:
                    print("Save cancelled by user due to invalid path.")
                    return  # User chose not to save

        else:
            # Creating a new entry (current_entry_path is None). Save to the currently selected category.
            if not self.current_category:
                messagebox.showwarning("无法保存", "请先选择一个分类以保存新条目。", parent=self.root)
                return
            category_to_save_in = self.current_category
            path_to_update = None  # Explicitly None for new entry
            print(f"Proceeding to save as NEW entry in: {category_to_save_in}")

        # Final check before saving
        if not category_to_save_in:
            messagebox.showerror("保存错误", "无法确定要保存到的分类。", parent=self.root)
            return

        try:
            print(
                f"Debug: Calling save_entry. Category='{category_to_save_in}', Title='{title}', ExistingPath='{path_to_update}'")
            saved_path_str = self.manager.save_entry(
                category_to_save_in,
                title,
                content,
                tags,
                existing_path_str=path_to_update  # Pass current path for update/rename logic
            )
            print(f"Debug: Save successful. Returned path='{saved_path_str}'")

            # --- Update State and UI *after* successful save ---
            self.current_entry_path = saved_path_str  # CRITICAL: Update state to the saved path
            new_path_obj = Path(saved_path_str)
            final_category = new_path_obj.parent.name
            final_title = title  # The title we just saved

            # Reload entries for the category where the save happened.
            # This handles adds, renames showing up, and ensures map is correct.
            # Check if the category list itself needs update (e.g., save created it)
            if final_category not in self.manager.categories:
                print("Warning: Saved to a category not previously in the list? Reloading categories.")
                self.load_categories()  # Reload category list as well
                # Try to select the category it was saved into
                self._select_listbox_item_by_text(self.category_listbox, final_category)

            # Now, specifically reload entries for the target category
            # Only reload if it's the currently viewed category OR if search is active
            if self.is_search_active:
                self.on_search()  # Re-run search to potentially include the new/updated item
                # Try to select the item in search results (might be tricky)
                search_display_text = f"[{final_category}] {final_title}"
                self._select_listbox_item_by_text(self.entry_listbox, search_display_text)

            elif self.current_category == final_category:
                self.load_entries(final_category)  # Reload the current category's list
                # Find and select the saved entry in the list using the *final* title.
                self._select_listbox_item_by_text(self.entry_listbox, final_title)
            else:
                # Saved in a different category than currently viewed, maybe select that category?
                # For now, just assume the save was successful, don't switch category view automatically.
                print(
                    f"Saved entry in '{final_category}', but currently viewing '{self.current_category}'. List not refreshed.")
                pass

            # Update the editor's info label using data from the saved file
            try:
                final_data = self.manager.get_entry_by_path(saved_path_str, read_content=False)
                if final_data and final_data.get("metadata"):
                    self._update_info_label(final_data["metadata"])
                else:
                    print(f"Warning: Could not re-read metadata after saving {saved_path_str}")
                    self.info_label_var.set("保存成功 (元数据刷新失败)")
            except Exception as read_e:
                print(f"Warning: Error reading metadata after save: {read_e}")
                self.info_label_var.set("保存成功 (元数据刷新错误)")


        except (ValueError, OSError, FileExistsError) as e:
            messagebox.showerror("保存错误", f"无法保存条目:\n{str(e)}", parent=self.root)
        except Exception as e:
            # Catch unexpected errors during save
            messagebox.showerror("意外错误", f"保存时发生未知错误:\n{str(e)}", parent=self.root)
            import traceback
            traceback.print_exc()  # Print stack trace for debugging

    def on_delete_selected_entries(self):
        """Move selected entries to the trash."""
        selected_indices = self.entry_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("选择条目", "请先在列表中选择一个或多个要删除的条目。", parent=self.root)
            return

        items_to_delete = []
        titles_to_delete = []
        paths_being_deleted = set()  # Store paths for checking editor state later

        for index in selected_indices:
            display_text = self.entry_listbox.get(index)
            # Skip placeholder items
            if display_text.startswith("("): continue

            entry_path = self.entry_data_map.get(display_text)
            # MODIFICATION: Use Path(entry_path).is_file() for stricter check
            path_valid = False
            if entry_path:
                try:
                    if Path(entry_path).is_file():
                        path_valid = True
                except Exception:
                    pass  # Ignore errors checking path here

            if path_valid:
                items_to_delete.append({"title": display_text, "path": entry_path})
                titles_to_delete.append(f"'{display_text}'")
                paths_being_deleted.add(entry_path)
            else:
                messagebox.showwarning("跳过删除", f"无法找到条目 '{display_text}' 的文件或映射，已跳过。",
                                       parent=self.root)

        if not items_to_delete:
            print("No valid entries selected for deletion.")
            return  # Nothing valid to delete

        num_items = len(items_to_delete)
        title_list_str = "\n - " + "\n - ".join(titles_to_delete) if num_items <= 5 else f"\n({num_items}个条目)"

        if messagebox.askyesno("确认移至回收站",
                               f"确定要将以下条目移动到回收站吗？\n{title_list_str}",
                               icon='warning', parent=self.root):  # Changed icon to warning
            deleted_count = 0
            errors = []

            for item in items_to_delete:
                try:
                    # Use the manager's delete_entry which now moves to trash
                    moved = self.manager.delete_entry(item["path"])
                    if moved:
                        deleted_count += 1
                    # delete_entry raises exceptions on failure

                except (OSError, ValueError, FileNotFoundError) as e:
                    errors.append(f"移动 '{item['title']}' 到回收站时出错: {e}")
                except Exception as e:
                    errors.append(f"移动 '{item['title']}' 到回收站时发生意外错误: {e}")

            # --- Refresh UI after processing all items ---
            print(f"Attempted to delete {len(items_to_delete)} entries, {deleted_count} succeeded.")

            # Check if the item currently in the editor was among those deleted
            editor_cleared = False
            if self.current_entry_path in paths_being_deleted:
                print(f"Editor item {self.current_entry_path} was deleted. Clearing editor.")
                self.clear_editor()  # Clears state and UI
                editor_cleared = True

            # Reload the list for the currently viewed category/search
            if deleted_count > 0:
                if self.is_search_active:
                    # Re-run the search to update results
                    print("Refreshing search results after deletion.")
                    self.on_search()
                elif self.current_category:
                    # Reload the current category's list
                    print(f"Refreshing entry list for category '{self.current_category}' after deletion.")
                    self.load_entries(self.current_category)
                else:
                    # No category selected, clear list state
                    self.load_entries(None)

            if errors:
                messagebox.showerror("删除错误", "移动一个或多个条目到回收站时发生错误:\n" + "\n".join(errors),
                                     parent=self.root)
            elif deleted_count > 0:
                messagebox.showinfo("成功", f"{deleted_count} 个条目已移动到回收站。", parent=self.root)

    def on_move_selected_entries(self):
        """Move selected entries to a different category using custom dialog."""
        selected_indices = self.entry_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("选择条目", "请先选择一个或多个要移动的条目。", parent=self.root)
            return

        items_to_move = []
        titles_to_move = []
        source_categories = set()
        paths_being_moved = set()

        for index in selected_indices:
            display_text = self.entry_listbox.get(index)
            # Skip placeholder items
            if display_text.startswith("("): continue

            entry_path_str = self.entry_data_map.get(display_text)
            # MODIFICATION: Use Path(entry_path).is_file() for stricter check
            path_valid = False
            entry_path_obj = None
            if entry_path_str:
                try:
                    entry_path_obj = Path(entry_path_str)
                    if entry_path_obj.is_file():
                        path_valid = True
                except Exception:
                    pass

            if path_valid:
                items_to_move.append({"title": display_text, "path": entry_path_str})
                titles_to_move.append(f"'{display_text}'")
                source_categories.add(entry_path_obj.parent.name)
                paths_being_moved.add(entry_path_str)
            else:
                messagebox.showwarning("跳过移动", f"无法找到条目 '{display_text}' 的文件或映射，已跳过。",
                                       parent=self.root)

        if not items_to_move:
            print("No valid entries selected for move.")
            return  # No valid items to move

        # Determine the 'current' category for the dialog (use the single source category if applicable)
        dialog_current_category = list(source_categories)[0] if len(source_categories) == 1 else None

        # Show the custom dialog
        dialog = MoveEntryDialog(self.root, self.manager.categories, dialog_current_category)
        target_category = dialog.result  # This blocks until dialog is closed

        if target_category:  # User pressed OK and provided a target
            # MODIFICATION: Check if target is the *only* source category
            if len(source_categories) == 1 and target_category == list(source_categories)[0]:
                messagebox.showinfo("移动条目", "目标分类与源分类相同，无需移动。", parent=self.root)
                return

            moved_count = 0
            errors = []
            is_new_category = False  # Track if the move *created* the category

            # Manager's move_entry now handles category creation if needed
            # Pre-checking and creating here is slightly redundant but safe.
            if target_category not in self.manager.categories:
                # Check if dir exists physically even if not in list
                if not (self.manager.root_dir / target_category).is_dir():
                    is_new_category = True  # It will be created by move_entry

            for item in items_to_move:
                try:
                    # move_entry handles creation and list update now
                    new_path_str = self.manager.move_entry(item["path"], target_category)
                    if new_path_str:
                        moved_count += 1
                    # else: move_entry raises exceptions on failure now

                except (FileNotFoundError, FileExistsError, OSError, ValueError) as e:
                    errors.append(f"移动 '{item['title']}' 到 '{target_category}' 时出错:\n {e}")
                except Exception as e:
                    errors.append(f"移动 '{item['title']}' 时发生意外错误: {e}")

            # --- Refresh UI after all moves attempted ---
            print(f"Attempted to move {len(items_to_move)} entries to '{target_category}', {moved_count} succeeded.")

            # Check if the item currently in the editor was moved
            editor_reset = False
            if self.current_entry_path in paths_being_moved:
                print(f"Editor item {self.current_entry_path} was moved. Updating path and potentially reloading.")
                # Find the new path (assuming filename didn't change)
                old_path_obj = Path(self.current_entry_path)
                new_path_str = str(self.manager.root_dir / target_category / old_path_obj.name)
                # Verify the new path exists before setting it
                if Path(new_path_str).is_file():
                    self.current_entry_path = new_path_str
                    print(f"Editor path updated to: {new_path_str}")
                    # No need to clear editor, just path changed
                else:
                    print("Moved item was in editor, but new path not found? Clearing editor.")
                    self.clear_editor()  # Fallback: clear editor if new path is wrong
                    editor_reset = True

            # Refresh category list ONLY if a new one was actually added by the process
            # Check the manager's list *after* the moves
            if target_category not in self.manager.categories:
                # This shouldn't happen if move_entry worked correctly, but double-check
                print("Warning: Target category missing from list after move. Reloading categories.")
                self.load_categories()
            elif is_new_category:
                # If we expected to create it, reload the list to show it
                print("New category created during move. Reloading category list.")
                self.load_categories()

            # Reload entry list for the *currently viewed* source category/search
            if moved_count > 0:
                if self.is_search_active:
                    print("Refreshing search results after move.")
                    self.on_search()  # Re-run search
                elif self.current_category in source_categories:
                    # Reload if the currently viewed category was a source
                    print(f"Refreshing entry list for source category '{self.current_category}' after move.")
                    self.load_entries(self.current_category)

            if errors:
                messagebox.showerror("移动错误", "移动过程中发生一个或多个错误:\n" + "\n".join(errors),
                                     parent=self.root)
            elif moved_count > 0:
                messagebox.showinfo("成功", f"{moved_count} 个条目已移动到分类 '{target_category}'。", parent=self.root)

    def on_rename_entry(self):
        """Rename the selected single entry (triggered by context menu)."""
        selected_indices = self.entry_listbox.curselection()
        if len(selected_indices) != 1:
            # Should not happen from context menu logic, but check anyway
            messagebox.showerror("重命名错误", "重命名需要选择单个条目。", parent=self.root)
            return

        try:
            index = selected_indices[0]
            current_display_text = self.entry_listbox.get(index)
        except (tk.TclError, IndexError):
            messagebox.showerror("错误", "无法获取选中的条目。", parent=self.root)
            return

        # Skip placeholder items
        if current_display_text.startswith("("): return

        entry_path_str = self.entry_data_map.get(current_display_text)

        # MODIFICATION: Use Path(entry_path).is_file() for stricter check
        path_valid = False
        if entry_path_str:
            try:
                if Path(entry_path_str).is_file():
                    path_valid = True
            except Exception:
                pass

        if not path_valid:
            messagebox.showerror("错误", f"无法找到条目 '{current_display_text}' 的文件。", parent=self.root)
            # Optionally remove the bad entry here
            return

        # Get the *actual* title from metadata for the initial value
        try:
            entry_data = self.manager.get_entry_by_path(entry_path_str, read_content=False)
            # Use title from metadata, fallback to display text or stem if metadata fails
            current_metadata_title = current_display_text  # Default
            if entry_data and entry_data.get("metadata") and entry_data["metadata"].get("title"):
                current_metadata_title = entry_data["metadata"]["title"]
            elif entry_path_str:  # Fallback to stem if metadata missing title
                current_metadata_title = Path(entry_path_str).stem

        except Exception as e:
            messagebox.showerror("错误", f"读取条目元数据时出错: {e}", parent=self.root)
            return

        new_title = simpledialog.askstring("重命名条目", f"请输入 '{current_metadata_title}' 的新标题:",
                                           initialvalue=current_metadata_title, parent=self.root)
        new_title = new_title.strip() if new_title else None

        if new_title and new_title != current_metadata_title:
            try:
                # Get full data needed for save_entry (which handles the rename)
                entry_data = self.manager.get_entry_by_path(entry_path_str, read_content=True)  # Need content too
                if not entry_data:
                    raise ValueError("无法读取原始条目数据进行重命名。")

                content = entry_data.get('content', '')
                tags = entry_data.get('metadata', {}).get('tags', [])
                entry_category = Path(entry_path_str).parent.name  # Get category from path

                # Use save_entry: provide new title, original content/tags, and *original* path
                print(
                    f"Calling save_entry for rename. Category='{entry_category}', NewTitle='{new_title}', ExistingPath='{entry_path_str}'")
                saved_path_str = self.manager.save_entry(
                    entry_category,
                    new_title,
                    content,
                    tags,
                    existing_path_str=entry_path_str  # Critical: signals a rename/update
                )
                print(f"Rename via save successful. New path: {saved_path_str}")

                # --- Update UI ---
                # If this was the edited entry, update path and title var
                if self.current_entry_path == entry_path_str:
                    self.current_entry_path = saved_path_str
                    self.title_var.set(new_title)  # Update editor title field directly
                    # Re-read metadata to update info label
                    try:
                        updated_data = self.manager.get_entry_by_path(saved_path_str, read_content=False)
                        if updated_data and updated_data.get("metadata"):
                            self._update_info_label(updated_data["metadata"])
                    except Exception as read_e:
                        print(f"Warning: Error reading metadata after rename: {read_e}")

                # Reload entries for the affected category to show the updated title
                if self.is_search_active:
                    print("Refreshing search results after rename.")
                    self.on_search()  # Re-run search if results are shown
                    # Try to select the renamed item in search results
                    search_display_text = f"[{entry_category}] {new_title}"
                    self._select_listbox_item_by_text(self.entry_listbox, search_display_text)
                elif self.current_category == entry_category:
                    print(f"Refreshing entry list for category '{entry_category}' after rename.")
                    self.load_entries(entry_category)  # Reload category list
                    # Re-select the newly named item
                    self._select_listbox_item_by_text(self.entry_listbox, new_title)


            except (ValueError, OSError, FileExistsError) as e:
                messagebox.showerror("重命名错误", f"无法重命名条目:\n{str(e)}", parent=self.root)
            except Exception as e:
                messagebox.showerror("意外错误", f"重命名时发生未知错误:\n{str(e)}", parent=self.root)
                import traceback
                traceback.print_exc()

    # --- Search Handlers ---
    def on_search(self, event=None):
        """Perform search based on the search bar content."""
        query = self.search_var.get()
        if not query.strip():
            # If query is empty, clear search and show current category
            self.on_clear_search()
            return

        print(f"Searching for: '{query}'")
        # Decide which categories to search (all for now)
        categories_to_search = None  # Search all categories

        try:
            results = self.manager.search(query, categories=categories_to_search)
            print(f"Found {len(results)} search results.")
            self.load_search_results(results)  # Clears editor internally
        except Exception as e:
            messagebox.showerror("搜索错误", f"搜索时发生错误:\n{e}", parent=self.root)
            print(f"Search error: {e}")

    def on_clear_search(self):
        """Clear search results and show entries for the selected category."""
        if not self.is_search_active and not self.search_var.get():
            return  # Do nothing if search wasn't active and box is empty

        print("Clearing search results.")
        self.search_var.set("")  # Clear search box
        self.is_search_active = False
        self.entry_list_label.config(text="条目列表")  # Reset label
        self.entry_listbox.config(state=tk.NORMAL)  # Ensure listbox is enabled

        # Reload entries for the currently selected category
        self.load_entries(self.current_category)  # Clears editor internally

    # --- Trash Handlers ---
    def on_view_trash(self):
        """Open the trash dialog to view/restore items."""
        try:
            trash_items_paths = self.manager.list_trash()
            print(f"Found {len(trash_items_paths)} items in trash.")
        except Exception as e:
            messagebox.showerror("错误", f"无法列出回收站内容:\n{e}", parent=self.root)
            return

        dialog = TrashDialog(self.root, trash_items_paths)
        # Dialog waits here...

        items_to_process = dialog.selected_items  # These are Path objects
        action = dialog.result_action  # "restore", "delete", or None

        if not items_to_process or action is None:
            print("Trash dialog closed or cancelled.")
            return  # Nothing selected or cancelled

        processed_count = 0
        errors = []
        affected_categories = set()  # Track categories needing refresh after restore

        if action == "restore":
            print(f"Attempting to restore {len(items_to_process)} items.")
            for item_path in items_to_process:
                try:
                    restored_path_str = self.manager.restore_trash_item(str(item_path))
                    if restored_path_str:
                        processed_count += 1
                        # Determine affected category for UI refresh
                        restored_path = Path(restored_path_str)
                        if restored_path.is_dir():
                            affected_categories.add(restored_path.name)  # Restored category name
                        elif restored_path.is_file():
                            # Make sure parent isn't root before adding
                            if restored_path.parent != self.manager.root_dir:
                                affected_categories.add(restored_path.parent.name)  # Parent dir name
                        else:
                            print(f"Warning: Restored item is neither file nor dir? {restored_path}")

                except (FileNotFoundError, ValueError, OSError) as e:
                    errors.append(f"恢复 '{item_path.name}' 时出错: {e}")
                except Exception as e:
                    errors.append(f"恢复 '{item_path.name}' 时发生意外错误: {e}")

            if processed_count > 0:
                messagebox.showinfo("恢复成功", f"{processed_count} 个项目已从回收站恢复。", parent=self.root)

        elif action == "delete":
            print(f"Attempting to permanently delete {len(items_to_process)} items from trash.")
            for item_path in items_to_process:
                try:
                    deleted = self.manager.permanently_delete_trash_item(str(item_path))
                    if deleted:
                        processed_count += 1
                except (FileNotFoundError, OSError) as e:
                    errors.append(f"永久删除 '{item_path.name}' 时出错: {e}")
                except Exception as e:
                    errors.append(f"永久删除 '{item_path.name}' 时发生意外错误: {e}")

            if processed_count > 0:
                messagebox.showinfo("删除成功", f"{processed_count} 个项目已从回收站永久删除。", parent=self.root)

        # --- Refresh UI based on actions ---
        if processed_count > 0:
            # Reload categories if any directory was restored OR if affected_categories has items
            if affected_categories:
                print("Reloading categories after trash restore operation affecting categories.")
                self.load_categories()  # Reload category list fully

            # Reload entries if the current view was affected by restore
            if not self.is_search_active and self.current_category in affected_categories:
                print(f"Reloading entries for restored-to category '{self.current_category}'.")
                self.load_entries(self.current_category)
            elif self.is_search_active:
                # Re-run search if search was active, as restored items might now match
                print("Re-running search after trash restore operation.")
                self.on_search()

        if errors:
            messagebox.showerror("回收站操作错误", "处理回收站项目时发生一个或多个错误:\n" + "\n".join(errors),
                                 parent=self.root)

    def on_empty_trash(self):
        """Permanently delete all items in the trash."""
        try:
            trash_items_count = len(self.manager.list_trash())
            if trash_items_count == 0:
                messagebox.showinfo("回收站为空", "回收站中没有项目可以清空。", parent=self.root)
                return
        except Exception as e:
            messagebox.showerror("错误", f"无法检查回收站状态:\n{e}", parent=self.root)
            return

        if messagebox.askyesno("确认清空回收站",
                               f"确定要永久删除回收站中的所有 {trash_items_count} 个项目吗？\n\n**警告：此操作无法撤销！**",
                               icon='warning', parent=self.root):
            try:
                print("Emptying trash...")
                deleted_count, errors = self.manager.empty_trash()
                print(f"Empty trash result: {deleted_count} deleted, {len(errors)} errors.")
                if errors:
                    messagebox.showerror("清空错误",
                                         f"清空回收站时发生错误，{len(errors)} 个项目可能未删除:\n" + "\n".join(
                                             errors[:5]) + ("..." if len(errors) > 5 else ""), parent=self.root)
                elif deleted_count > 0:
                    messagebox.showinfo("成功", f"回收站已清空，{deleted_count} 个项目被永久删除。", parent=self.root)
                else:
                    # This case means count was > 0 initially, but delete count is 0 (all failed?)
                    messagebox.showwarning("清空回收站", "尝试清空回收站，但没有项目被删除 (可能发生错误)。",
                                           parent=self.root)

            except Exception as e:
                messagebox.showerror("清空错误", f"清空回收站时发生严重错误:\n{e}", parent=self.root)

    # --- Context Menu Handlers ---

    # MODIFICATION: Enhanced category context menu logic
    def show_category_menu(self, event):
        """Show the context menu for categories."""
        # Ensure listbox exists
        if not self.category_listbox.winfo_exists(): return

        # Select the item under the cursor *before* showing the menu
        # This makes the menu act on the item clicked on.
        clicked_index = self.category_listbox.nearest(event.y)
        if clicked_index >= 0:
            # Check if click is actually within the item's bounds (optional but good)
            bbox = self.category_listbox.bbox(clicked_index)
            on_item = bbox and (bbox[0] <= event.x < bbox[0] + bbox[2]) and (bbox[1] <= event.y < bbox[1] + bbox[3])

            if on_item:
                # If the clicked item is not already selected, select it exclusively
                if not self.category_listbox.selection_includes(clicked_index):
                    self.category_listbox.selection_clear(0, tk.END)
                    self.category_listbox.selection_set(clicked_index)
                    self.category_listbox.activate(clicked_index)
                    # Manually trigger select event logic AFTER menu closes if needed,
                    # but usually selection itself is enough context.
                    # Let's trigger it here to load entries immediately.
                    self.on_category_select(None)

            else:  # Click was in empty space
                # Optionally clear selection when clicking empty space
                # self.category_listbox.selection_clear(0, tk.END)
                # self.on_category_select(None) # Update UI based on cleared selection
                pass  # Or just show the default menu

        self.category_menu.delete(0, tk.END)  # Clear previous items

        # Always add "New Category"
        self.category_menu.add_command(label="新建分类...", command=self.on_new_category)

        # Add item-specific options ONLY if a single item is selected
        current_selection = self.category_listbox.curselection()
        if len(current_selection) == 1:
            selected_index = current_selection[0]
            # Verify the click was on or near the selected item if needed (already handled above)
            try:
                selected_category = self.category_listbox.get(selected_index)
                self.category_menu.add_separator()
                self.category_menu.add_command(label=f"重命名 '{selected_category}'...",
                                               command=self.on_rename_category)
                self.category_menu.add_command(label=f"删除 '{selected_category}' (移至回收站)",
                                               command=self.on_delete_selected_category)  # Removed ellipsis
            except tk.TclError:
                pass  # Item might have disappeared

        # Post the menu
        try:
            self.category_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.category_menu.grab_release()

    # MODIFICATION: Enhanced entry context menu logic
    def show_entry_menu(self, event):
        """Show the context menu for entries based on selection."""
        # Ensure listbox exists
        if not self.entry_listbox.winfo_exists(): return

        # --- Selection Logic ---
        clicked_index = self.entry_listbox.nearest(event.y)
        on_item = False
        actual_item_clicked = False  # Track if click was on text, not just row

        if clicked_index >= 0:
            # Check if click is actually within the item's text bounds
            bbox = self.entry_listbox.bbox(clicked_index)
            if bbox and (bbox[0] <= event.x < bbox[0] + bbox[2]) and (bbox[1] <= event.y < bbox[1] + bbox[3]):
                on_item = True
                # Check if the item text is placeholder
                try:
                    item_text = self.entry_listbox.get(clicked_index)
                    if not item_text.startswith("("):
                        actual_item_clicked = True  # Clicked on a real entry
                except tk.TclError:
                    pass  # Ignore if item disappears

                # Get current selection *before* potentially changing it
                current_selection = self.entry_listbox.curselection()

                # If clicking on a valid item THAT IS NOT SELECTED, select ONLY that item.
                # If clicking on a valid item THAT IS ALREADY SELECTED (part of multi-select), keep selection.
                # If clicking on empty space or placeholder, do nothing to selection here.
                if actual_item_clicked and (clicked_index not in current_selection):
                    self.entry_listbox.selection_clear(0, tk.END)
                    self.entry_listbox.selection_set(clicked_index)
                    self.entry_listbox.activate(clicked_index)
                    # Trigger select event to load editor immediately
                    self.on_entry_select(None)

        # --- Menu Building ---
        self.entry_menu.delete(0, tk.END)

        # Get the potentially updated selection
        selected_indices = self.entry_listbox.curselection()
        num_selected = len(selected_indices)

        # Add "New Entry" only if a category is selected (context allows it)
        if self.current_category:
            self.entry_menu.add_command(label="新建条目", command=self.on_new_entry)
            self.entry_menu.add_separator()

        # Populate menu based on the number of selected *valid* items
        # We only add context items if the click was actually on an item row
        if num_selected > 0 and on_item:
            # Check if *any* selected item is a placeholder - disable actions if so
            has_placeholder = False
            valid_titles = []
            if actual_item_clicked:  # Only check if click was on a potentially valid item
                for idx in selected_indices:
                    try:
                        txt = self.entry_listbox.get(idx)
                        if txt.startswith("("):
                            has_placeholder = True
                            break
                        else:
                            valid_titles.append(txt)
                    except tk.TclError:
                        has_placeholder = True  # Treat error as invalid item
                        break

            if not has_placeholder and valid_titles:  # Only add if selection is valid
                if num_selected == 1:
                    # Single item selected
                    selected_title = valid_titles[0]
                    self.entry_menu.add_command(label=f"编辑 '{selected_title}'", command=self.on_edit_selected_entry)
                    self.entry_menu.add_command(label=f"重命名 '{selected_title}'...", command=self.on_rename_entry)
                    self.entry_menu.add_separator()
                    self.entry_menu.add_command(label=f"删除 '{selected_title}' (移至回收站)",
                                                command=self.on_delete_selected_entries)  # Use plural handler
                    self.entry_menu.add_command(label=f"移动 '{selected_title}' 到分类...",
                                                command=self.on_move_selected_entries)  # Use plural handler
                else:
                    # Multiple items selected
                    self.entry_menu.add_command(label=f"删除 {len(valid_titles)} 个条目 (移至回收站)",
                                                command=self.on_delete_selected_entries)
                    self.entry_menu.add_command(label=f"移动 {len(valid_titles)} 个条目到分类...",
                                                command=self.on_move_selected_entries)

        # Post the menu if it has items
        if self.entry_menu.index(tk.END) is not None:
            try:
                self.entry_menu.tk_popup(event.x_root, event.y_root)
            finally:
                self.entry_menu.grab_release()

    # --- Theme Switching ---
    def switch_theme(self, theme_name):
        """Switch the application theme using sv-ttk."""
        if not sv_ttk:
            # messagebox.showinfo("主题切换", "sv-ttk 主题库未找到，无法切换主题。", parent=self.root)
            print("sv-ttk not found, cannot switch theme.")
            return
        try:
            print(f"Switching theme to: {theme_name}")
            sv_ttk.set_theme(theme_name)
            # Force update of styles on specific widgets if needed
            # E.g., re-apply listbox selection color based on new theme
            self._setup_style()
            self.root.update_idletasks()
        except Exception as e:
            print(f"Error switching theme to '{theme_name}': {e}")
            messagebox.showwarning("主题错误", f"无法切换到主题 '{theme_name}'.\n错误: {e}", parent=self.root)

    # --- Adicionar este método à classe NovelManagerGUI ---

    def on_refresh(self):
        """Refresh categories and files from disk."""
        print("Refreshing from filesystem...")

        # Store current selections before refresh
        current_category = self.current_category
        current_entry_path = self.current_entry_path

        # Force reload of categories from disk
        try:
            self.manager.categories = self.manager._load_categories()  # Reload categories from disk
            self.load_categories()  # Update UI with refreshed categories

            # Try to reselect the category that was selected before
            if current_category:
                if self._select_listbox_item_by_text(self.category_listbox, current_category):
                    # Category was found and reselected

                    # If we had an entry path, try to find and select it again
                    if current_entry_path:
                        try:
                            path_obj = Path(current_entry_path)
                            if path_obj.exists() and path_obj.is_file():
                                # File still exists, reload the same file
                                self.current_entry_path = current_entry_path

                                # Find the title in the listbox to reselect it
                                entry_data = self.manager.get_entry_by_path(current_entry_path, read_content=False)
                                if entry_data and entry_data.get("metadata"):
                                    title = entry_data["metadata"].get("title", path_obj.stem)
                                    self._select_listbox_item_by_text(self.entry_listbox, title)
                        except Exception as e:
                            print(f"Error reselecting entry after refresh: {e}")

            messagebox.showinfo("刷新完成", "已从文件系统刷新分类和条目。", parent=self.root)
        except Exception as e:
            messagebox.showerror("刷新错误", f"刷新时发生错误:\n{e}", parent=self.root)


# --- Main Execution ---
if __name__ == "__main__":
    root = tk.Tk()
    # Ensure the NovelManager directory exists before GUI starts fully
    try:
        manager = NovelManager()  # Initialise manager once to create dirs
    except Exception as e:
        messagebox.showerror("Initialization Error", f"Failed to initialize data storage:\n{e}")
        root.destroy()  # Close if storage fails
        exit()

    app = NovelManagerGUI(root)
    root.mainloop()