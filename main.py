import os
import re
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog

# ===== 内置主题配置 =====
THEMES = {
    "柔和深灰蓝": {
        "bg_main": "#1e1e2a",
        "bg_table": "#262635",
        "bg_heading": "#2a2a3a",
        "bg_button": "#2e2e3e",
        "bg_button_hover": "#3a3a4e",
        "bg_input": "#262635",
        "bg_select": "#3a4a6b",
        "fg_text": "#e0e0ea",
        "fg_white": "#ffffff",
        "border": "#3a3a4e",
    },
    "纯黑": {
        "bg_main": "#0d0d0d",
        "bg_table": "#141414",
        "bg_heading": "#1a1a1a",
        "bg_button": "#1f1f1f",
        "bg_button_hover": "#2a2a2a",
        "bg_input": "#141414",
        "bg_select": "#2b3a5a",
        "fg_text": "#e8e8e8",
        "fg_white": "#ffffff",
        "border": "#333333",
    },
    "浅色": {
        "bg_main": "#f0f0f0",
        "bg_table": "#ffffff",
        "bg_heading": "#e0e0e0",
        "bg_button": "#d0d0d0",
        "bg_button_hover": "#c0c0c0",
        "bg_input": "#ffffff",
        "bg_select": "#a0c0e0",
        "fg_text": "#000000",
        "fg_white": "#000000",
        "border": "#b0b0b0",
    },
}
DEFAULT_THEME = "柔和深灰蓝"
DEFAULT_ROOT_PATH = r"C:\Users\Administrator\Desktop\编程经验"

# 虚拟列表每行高度（像素）
ROW_HEIGHT = 24
# 预创建的行组件数量（通常为可视区域行数的2倍以上，确保滚动缓冲）
VISIBLE_POOL_SIZE = 80


class FolderIndexerApp:
    def __init__(self, master):
        self.master = master
        master.title("规则库目录索引工具")
        master.geometry("800x650")

        self.current_theme = DEFAULT_THEME
        self.style = ttk.Style(master)
        self.style.theme_use('clam')

        self.all_files = []
        self.processed_files = set()
        self.current_filter = ""
        self.review_mode = False
        self.root_path = DEFAULT_ROOT_PATH

        # 文件类型过滤相关
        self.filter_mode = None          # None, 'include', 'exclude'
        self.filter_extensions = set()   # 小写扩展名集合（不含点）

        # 索引字典，加速批量审核匹配
        self._rel_index = {}
        self._name_index = {}

        # 虚拟列表相关
        self.visible_files = []          # 当前显示的文件列表（过滤后）
        self.row_pool = []               # 行组件池
        self.row_windows = []            # 每个行组件对应的 Canvas 窗口项 ID
        self.canvas_width = 0            # 画布宽度
        self.canvas_height = 0           # 画布高度

        # 默认提示词模板
        self.prompt_template = """请基于以下文件列表，结合我当前项目的背景和目标，分析并推荐最有助于项目优化的文档清单。请考虑项目的性能、架构、安全性、可维护性等多个维度。

输出要求：仅以纯文本形式输出推荐的文件相对路径，每行一个，保持路径与文件列表中完全一致（包括目录分隔符），不要添加任何编号、项目符号、反引号或其他格式标记，不要附加解释。

文件列表：
{file_list}
"""

        # ===== 顶部框架 =====
        top_frame = ttk.Frame(master)
        top_frame.pack(fill='x', padx=5, pady=5)

        ttk.Label(top_frame, text="索引任务关键词:").pack(side='left')
        self.keyword_var = tk.StringVar()
        self.keyword_entry = ttk.Entry(top_frame, textvariable=self.keyword_var)
        self.keyword_entry.pack(side='left', fill='x', expand=True, padx=5)
        self.keyword_entry.bind('<KeyRelease>', self.on_filter_change)

        ttk.Button(top_frame, text="复制过滤结果", command=self.copy_filtered).pack(side='left', padx=2)
        ttk.Button(top_frame, text="更改文件夹", command=self.change_root_folder).pack(side='left', padx=2)
        ttk.Button(top_frame, text="刷新", command=self.refresh_files).pack(side='left', padx=2)
        ttk.Button(top_frame, text="过滤设置", command=self.open_filter_settings).pack(side='left', padx=2)

        ttk.Label(top_frame, text="主题:").pack(side='left', padx=(10, 2))
        self.theme_var = tk.StringVar(value=self.current_theme)
        theme_combo = ttk.Combobox(top_frame, textvariable=self.theme_var,
                                   values=list(THEMES.keys()), state="readonly", width=12)
        theme_combo.pack(side='left', padx=2)
        theme_combo.bind("<<ComboboxSelected>>", self.on_theme_change)

        # ===== 可滚动列表区域 =====
        list_container = ttk.Frame(master)
        list_container.pack(fill='both', expand=True, padx=5, pady=5)

        self.canvas = tk.Canvas(list_container, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(list_container, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side='left', fill='both', expand=True)
        self.scrollbar.pack(side='right', fill='y')

        # 绑定画布大小变化和滚动事件
        self.canvas.bind('<Configure>', self._on_canvas_configure)
        self.canvas.bind('<MouseWheel>', self._on_mousewheel)
        self.canvas.bind('<Button-4>', self._on_mousewheel)   # Linux
        self.canvas.bind('<Button-5>', self._on_mousewheel)   # Linux

        # 创建行组件池（同时创建 Canvas 窗口项）
        self._create_row_pool()

        # ===== 底部按钮 =====
        bottom_frame = ttk.Frame(master)
        bottom_frame.pack(fill='x', padx=5, pady=5)

        ttk.Button(bottom_frame, text="批量审核", command=self.batch_review).pack(side='left', padx=2)
        ttk.Button(bottom_frame, text="导出提示词", command=self.export_prompt).pack(side='left', padx=2)
        ttk.Button(bottom_frame, text="编辑模板", command=self.edit_template).pack(side='left', padx=2)
        ttk.Button(bottom_frame, text="重置已处理", command=self.reset_processed).pack(side='left', padx=2)

        # ===== 状态栏 =====
        self.status_var = tk.StringVar()
        self.status_var.set("正在扫描...")
        status_bar = ttk.Label(master, textvariable=self.status_var, relief='sunken', anchor='w')
        status_bar.pack(fill='x', side='bottom')
        self.style.configure('Status.TLabel', background=THEMES[self.current_theme]["bg_heading"],
                             foreground=THEMES[self.current_theme]["fg_text"])
        status_bar.configure(style='Status.TLabel')

        # 搜索防抖定时器
        self._search_after_id = None
        self._update_after_id = None

        # 应用主题并扫描文件
        self.apply_theme(self.current_theme)
        self.scan_files()
        self.refresh_display()

    def _create_row_pool(self):
        """预创建固定数量的行组件，并作为 Canvas 窗口项"""
        for i in range(VISIBLE_POOL_SIZE):
            row = ttk.Frame(self.canvas, style='FileRow.TFrame')
            row.config(height=ROW_HEIGHT)

            container = ttk.Frame(row, style='FileRow.TFrame')
            container.place(relx=0.65, rely=0.5, anchor='e')

            btn = ttk.Button(container, text="复制", width=6,
                             command=lambda r=row: self._on_copy_click(r))
            btn.pack(side='right', padx=(5, 0))

            lbl = ttk.Label(container, text="", style='FileRow.TLabel', anchor='e')
            lbl.pack(side='right', padx=(0, 5))

            row._button = btn
            row._label = lbl
            row._file_path = None  # 当前绑定的文件路径

            # 为行组件及其子组件绑定滚轮事件，确保鼠标在行上滚动也能触发
            for widget in (row, container, btn, lbl):
                widget.bind('<MouseWheel>', self._on_mousewheel)
                widget.bind('<Button-4>', self._on_mousewheel)
                widget.bind('<Button-5>', self._on_mousewheel)

            # 创建 Canvas 窗口项，初始位置放在不可见区域
            window_id = self.canvas.create_window(0, -1000, window=row, anchor='nw',
                                                  width=self.canvas_width, height=ROW_HEIGHT)
            self.row_pool.append(row)
            self.row_windows.append(window_id)

    def _on_copy_click(self, row):
        path = getattr(row, '_file_path', None)
        if path:
            self.copy_single_file(path)

    def _on_canvas_configure(self, event):
        self.canvas_width = event.width
        self.canvas_height = event.height
        # 更新窗口项的宽度
        for win_id in self.row_windows:
            self.canvas.itemconfigure(win_id, width=event.width)
        # 重新计算滚动区域和可见行
        self._update_scrollregion()
        self._update_visible_rows()

    def _update_scrollregion(self):
        """更新 Canvas 的滚动区域"""
        total_rows = len(self.visible_files)
        total_height = total_rows * ROW_HEIGHT
        self.canvas.configure(scrollregion=(0, 0, self.canvas_width, total_height))

    def _on_mousewheel(self, event):
        # 直接滚动，不依赖 Canvas 焦点
        if event.num == 4:
            self.canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self.canvas.yview_scroll(1, "units")
        else:
            delta = -1 * (event.delta // 120)
            self.canvas.yview_scroll(delta, "units")
        # 滚动后更新可见行（使用after_idle合并快速滚动事件）
        if self._update_after_id:
            self.master.after_cancel(self._update_after_id)
        self._update_after_id = self.master.after_idle(self._update_visible_rows)

    def _update_visible_rows(self):
        """根据滚动位置更新可见行窗口项的位置和内容"""
        if not self.visible_files:
            # 隐藏所有窗口项
            for win_id in self.row_windows:
                self.canvas.coords(win_id, 0, -1000)
            return

        total_rows = len(self.visible_files)
        canvas_height = self.canvas.winfo_height()
        if canvas_height <= 0:
            return

        # 获取当前滚动位置（相对比例）
        yview = self.canvas.yview()
        top_fraction = yview[0]
        bottom_fraction = yview[1]

        # 计算可见行索引范围（带缓冲）
        first_visible = max(0, int(top_fraction * total_rows) - 1)
        last_visible = min(total_rows - 1, int(bottom_fraction * total_rows) + 1)

        # 确保最后一行始终可见（如果滚动到底部）
        if bottom_fraction >= 1.0:
            last_visible = total_rows - 1

        # 更新池中每个窗口项
        for i in range(len(self.row_pool)):
            row = self.row_pool[i]
            win_id = self.row_windows[i]
            idx = first_visible + i
            if idx <= last_visible:
                file_info = self.visible_files[idx]
                # 更新内容
                if row._label.cget('text') != file_info['rel']:
                    row._label.config(text=file_info['rel'])
                row._file_path = file_info['full']
                # 设置窗口项位置
                y_position = idx * ROW_HEIGHT
                self.canvas.coords(win_id, 0, y_position)
            else:
                # 移出可视区域
                self.canvas.coords(win_id, 0, -1000)

    def scan_files(self):
        """扫描当前根路径下的所有文件，并建立索引"""
        self.all_files.clear()
        self._rel_index.clear()
        self._name_index.clear()

        if not self.root_path or not os.path.exists(self.root_path):
            self.status_var.set(f"路径不存在: {self.root_path}，请点击“更改文件夹”选择有效目录")
            return

        try:
            for root, dirs, files in os.walk(self.root_path):
                dirs[:] = [d for d in dirs if d.lower() != '.idea']
                for file in files:
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, self.root_path)
                    file_info = {
                        'full': full_path,
                        'rel': rel_path,
                        'name': file
                    }
                    self.all_files.append(file_info)

                    # 构建索引
                    norm_rel = rel_path.replace('\\', '/').lower()
                    self._rel_index.setdefault(norm_rel, []).append(full_path)
                    self._name_index.setdefault(file.lower(), []).append(full_path)

            # 按相对路径排序
            self.all_files.sort(key=lambda x: x['rel'].lower())
        except Exception as e:
            messagebox.showerror("扫描错误", f"无法扫描目录：{e}")
        if not self.all_files:
            self.status_var.set("当前文件夹为空或不可访问")

    def apply_theme(self, theme_name):
        theme = THEMES[theme_name]
        self.current_theme = theme_name
        self.master.configure(bg=theme["bg_main"])
        self.style.configure('TLabel', background=theme["bg_main"], foreground=theme["fg_text"])
        self.style.configure('TFrame', background=theme["bg_main"])
        self.style.configure('TButton', background=theme["bg_button"], foreground=theme["fg_text"],
                             bordercolor=theme["border"])
        self.style.map('TButton',
                       background=[('active', theme["bg_button_hover"]), ('pressed', theme["bg_main"])],
                       foreground=[('active', theme["fg_white"])])
        self.style.configure('TEntry',
                             fieldbackground=theme["bg_input"],
                             foreground=theme["fg_text"],
                             insertcolor=theme["fg_text"])
        self.style.configure('Status.TLabel', background=theme["bg_heading"], foreground=theme["fg_text"])
        self.style.configure('FileRow.TFrame', background=theme["bg_table"])
        self.style.configure('FileRow.TLabel', background=theme["bg_table"], foreground=theme["fg_text"])

        self.canvas.configure(bg=theme["bg_table"])
        # 更新行池样式
        for row in self.row_pool:
            row.configure(style='FileRow.TFrame')
            row._label.configure(style='FileRow.TLabel')

    def on_theme_change(self, event=None):
        selected_theme = self.theme_var.get()
        if selected_theme in THEMES:
            self.apply_theme(selected_theme)
            self.refresh_display()

    def on_filter_change(self, event=None):
        """带防抖的过滤处理"""
        if self._search_after_id:
            self.master.after_cancel(self._search_after_id)
        self._search_after_id = self.master.after(150, self._apply_filter)

    def _apply_filter(self):
        self.current_filter = self.keyword_var.get().strip().lower()
        self.refresh_display()

    def get_visible_files(self):
        visible = []
        for f in self.all_files:
            if f['full'] in self.processed_files:
                continue
            if self.current_filter and self.current_filter not in f['rel'].lower():
                continue
            # 应用文件类型过滤
            if self.filter_mode == 'include':
                ext = os.path.splitext(f['name'])[1].lower().lstrip('.')
                if ext not in self.filter_extensions:
                    continue
            elif self.filter_mode == 'exclude':
                ext = os.path.splitext(f['name'])[1].lower().lstrip('.')
                if ext in self.filter_extensions:
                    continue
            visible.append(f)
        return visible

    def _update_status(self, visible_count=None):
        total = len(self.all_files)
        processed = len(self.processed_files)
        if visible_count is None:
            visible_count = len(self.visible_files)
        mode_info = " [审核模式]" if self.review_mode else ""
        filter_info = f" | 过滤: '{self.current_filter}'" if self.current_filter else ""
        if self.filter_mode == 'include' and self.filter_extensions:
            filter_info += f" [仅显示: {', '.join(sorted(self.filter_extensions))}]"
        elif self.filter_mode == 'exclude' and self.filter_extensions:
            filter_info += f" [排除: {', '.join(sorted(self.filter_extensions))}]"
        path_info = f" | 目录: {self.root_path}" if self.root_path else ""
        self.status_var.set(f"总文件: {total} | 已处理: {processed} | 当前显示: {visible_count}{mode_info}{filter_info}{path_info}")

    def refresh_display(self):
        """刷新虚拟列表数据，更新滚动区域和可见行"""
        # 保存当前滚动位置（相对比例）
        scroll_fraction = self.canvas.yview()

        # 更新可见文件列表
        self.visible_files = self.get_visible_files()
        total_visible = len(self.visible_files)

        # 更新滚动区域
        self._update_scrollregion()

        # 尝试恢复滚动位置
        if total_visible > 0:
            self.canvas.yview_moveto(scroll_fraction[0])
        else:
            self.canvas.yview_moveto(0)

        # 更新可见行
        self._update_visible_rows()
        self._update_status(total_visible)

    def remove_file_row(self, full_path):
        """从可见列表中移除文件（审核模式隐藏后调用）"""
        # 从 visible_files 中移除
        self.visible_files = [f for f in self.visible_files if f['full'] != full_path]
        # 更新滚动区域
        self._update_scrollregion()
        # 更新可见行
        self._update_visible_rows()
        self._update_status()

    def copy_to_clipboard(self, text):
        self.master.clipboard_clear()
        self.master.clipboard_append(text)
        self.master.update_idletasks()

    def copy_single_file(self, full_path):
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
            self.copy_to_clipboard(content)
            if self.review_mode:
                self.processed_files.add(full_path)
                self.remove_file_row(full_path)
                self.status_var.set(f"已复制并隐藏: {os.path.basename(full_path)}（审核模式）")
            else:
                self.status_var.set(f"已复制: {os.path.basename(full_path)}（普通模式，文件保留）")
        except Exception as e:
            messagebox.showerror("错误", f"无法读取文件: {full_path}\n{e}")

    def copy_filtered(self):
        visible = self.visible_files
        if not visible:
            messagebox.showinfo("提示", "当前没有可复制的文件")
            return
        tree_text = self._generate_tree_from_files(visible)
        self.copy_to_clipboard(tree_text)
        self.status_var.set(f"已复制过滤结果（{len(visible)} 个文件）")

    def _generate_tree_from_files(self, files):
        tree = {}
        for f in files:
            parts = f['rel'].split(os.sep)
            node = tree
            for part in parts:
                node = node.setdefault(part, {})
        lines = []
        def build(node, prefix=''):
            items = sorted(node.keys())
            for i, item in enumerate(items):
                is_last = (i == len(items) - 1)
                connector = '└── ' if is_last else '├── '
                lines.append(f"{prefix}{connector}{item}")
                if node[item]:
                    new_prefix = prefix + ('    ' if is_last else '│   ')
                    build(node[item], new_prefix)
        build(tree)
        return '\n'.join(lines)

    # ===== 文件类型过滤设置对话框 =====
    def open_filter_settings(self):
        """打开过滤设置窗口，支持多选扩展名，包含/排除模式"""
        dialog = tk.Toplevel(self.master)
        dialog.title("文件类型过滤设置")
        dialog.geometry("500x600")
        dialog.transient(self.master)
        dialog.grab_set()

        theme = THEMES[self.current_theme]
        dialog.configure(bg=theme["bg_main"])

        # 模式选择
        mode_frame = ttk.Frame(dialog, style='TFrame')
        mode_frame.pack(pady=10, fill='x', padx=10)

        ttk.Label(mode_frame, text="过滤模式:", background=theme["bg_main"],
                  foreground=theme["fg_text"]).pack(side='left', padx=(0,10))

        mode_var = tk.StringVar(value='none' if not self.filter_mode else self.filter_mode)
        modes = [('无过滤', 'none'), ('仅显示选中类型', 'include'), ('隐藏选中类型', 'exclude')]
        for text, value in modes:
            rb = ttk.Radiobutton(mode_frame, text=text, variable=mode_var, value=value,
                                 style='TRadiobutton')
            rb.pack(side='left', padx=5)

        # 扩展名列表
        list_frame = ttk.Frame(dialog, style='TFrame')
        list_frame.pack(fill='both', expand=True, padx=10, pady=5)

        ttk.Label(list_frame, text="选择扩展名（可多选）:", background=theme["bg_main"],
                  foreground=theme["fg_text"]).pack(anchor='w')

        listbox_frame = ttk.Frame(list_frame, style='TFrame')
        listbox_frame.pack(fill='both', expand=True, pady=5)

        scrollbar = ttk.Scrollbar(listbox_frame, orient='vertical')
        scrollbar.pack(side='right', fill='y')

        listbox = tk.Listbox(listbox_frame, selectmode='multiple', yscrollcommand=scrollbar.set,
                             bg=theme["bg_input"], fg=theme["fg_text"],
                             selectbackground=theme["bg_select"], selectforeground=theme["fg_white"],
                             exportselection=False)
        listbox.pack(side='left', fill='both', expand=True)
        scrollbar.config(command=listbox.yview)

        # 提取当前所有扩展名
        extensions = set()
        for f in self.all_files:
            ext = os.path.splitext(f['name'])[1].lower().lstrip('.')
            if ext:  # 忽略无扩展名
                extensions.add(ext)
        extensions = sorted(extensions)

        # 填充列表
        for ext in extensions:
            listbox.insert(tk.END, ext)

        # 根据当前过滤设置选中项
        if self.filter_extensions:
            for i, ext in enumerate(extensions):
                if ext in self.filter_extensions:
                    listbox.selection_set(i)

        # 按钮行：全选/全不选
        btn_frame = ttk.Frame(list_frame, style='TFrame')
        btn_frame.pack(fill='x', pady=5)
        ttk.Button(btn_frame, text="全选", command=lambda: listbox.selection_set(0, tk.END)).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="全不选", command=lambda: listbox.selection_clear(0, tk.END)).pack(side='left', padx=5)

        # 自定义扩展名输入
        custom_frame = ttk.Frame(dialog, style='TFrame')
        custom_frame.pack(fill='x', padx=10, pady=5)

        ttk.Label(custom_frame, text="自定义扩展名（逗号分隔）:", background=theme["bg_main"],
                  foreground=theme["fg_text"]).pack(side='left')

        custom_var = tk.StringVar()
        custom_entry = ttk.Entry(custom_frame, textvariable=custom_var, width=30)
        custom_entry.pack(side='left', padx=5)

        def add_custom():
            raw = custom_var.get().strip()
            if not raw:
                return
            # 分割并清理
            parts = [p.strip().lower().lstrip('.') for p in raw.split(',') if p.strip()]
            for ext in parts:
                if ext and ext not in extensions:
                    extensions.append(ext)
                    listbox.insert(tk.END, ext)
                # 选中该项
                idx = extensions.index(ext)
                listbox.selection_set(idx)
            custom_var.set("")

        ttk.Button(custom_frame, text="添加", command=add_custom).pack(side='left', padx=5)

        # 底部按钮：应用、取消
        bottom = ttk.Frame(dialog, style='TFrame')
        bottom.pack(pady=10)

        def apply():
            mode = mode_var.get()
            if mode == 'none':
                self.filter_mode = None
                self.filter_extensions = set()
            else:
                selected_indices = listbox.curselection()
                selected_exts = {extensions[i] for i in selected_indices}
                self.filter_mode = mode
                self.filter_extensions = selected_exts
            self.refresh_display()
            dialog.destroy()

        ttk.Button(bottom, text="应用", command=apply).pack(side='left', padx=10)
        ttk.Button(bottom, text="取消", command=dialog.destroy).pack(side='left', padx=10)

    def batch_review(self):
        dialog = tk.Toplevel(self.master)
        dialog.title("批量审核 - 粘贴 AI 文档清单")
        dialog.geometry("600x400")
        dialog.transient(self.master)
        dialog.grab_set()

        theme = THEMES[self.current_theme]
        dialog.configure(bg=theme["bg_main"])

        ttk.Label(dialog, text="请粘贴 AI 返回的文档清单（每行一个，支持文件名或路径）：\n（清单中的文件将被保留，不在清单中的本地文件将被隐藏）",
                  background=theme["bg_main"], foreground=theme["fg_text"]).pack(pady=10)

        text_area = scrolledtext.ScrolledText(dialog, wrap='word', width=70, height=15,
                                              bg=theme["bg_input"], fg=theme["fg_text"],
                                              insertbackground=theme["fg_text"])
        text_area.pack(padx=10, pady=5, fill='both', expand=True)

        def confirm():
            content = text_area.get("1.0", tk.END).strip()
            if not content:
                messagebox.showwarning("提示", "请粘贴文档清单", parent=dialog)
                return
            lines = [line.strip() for line in content.splitlines() if line.strip()]
            matched = []
            unmatched = []

            for line in lines:
                cleaned = re.sub(r'^[\d\.\-\*\s`\[\]()]+', '', line).strip()
                if not cleaned:
                    continue
                cleaned_norm = cleaned.replace('\\', '/').lower()

                # 使用索引快速匹配
                if cleaned_norm in self._rel_index:
                    matched.extend(self._rel_index[cleaned_norm])
                    continue
                if cleaned.lower() in self._name_index:
                    matched.extend(self._name_index[cleaned.lower()])
                    continue
                # 完整路径匹配（兼容性）
                full_path_norm = cleaned.replace('\\', '/').lower()
                for f in self.all_files:
                    if f['full'].replace('\\', '/').lower() == full_path_norm:
                        matched.append(f['full'])
                        break
                else:
                    unmatched.append(line)

            matched = list(set(matched))
            matched_set = set(matched)
            for f in self.all_files:
                if f['full'] not in matched_set:
                    self.processed_files.add(f['full'])

            self.review_mode = True
            self.refresh_display()

            msg = f"已保留清单中的 {len(matched)} 个文件，隐藏其他 {len(self.all_files) - len(matched)} 个文件（审核模式）"
            if unmatched:
                msg += f"；未匹配 {len(unmatched)} 行"
            self.status_var.set(msg)
            dialog.destroy()

        btn_frame = ttk.Frame(dialog, style='TFrame')
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="确认", command=confirm).pack(side='left', padx=10)
        ttk.Button(btn_frame, text="取消", command=dialog.destroy).pack(side='left', padx=10)

    def edit_template(self):
        dialog = tk.Toplevel(self.master)
        dialog.title("编辑提示词模板")
        dialog.geometry("600x500")
        dialog.transient(self.master)
        dialog.grab_set()

        theme = THEMES[self.current_theme]
        dialog.configure(bg=theme["bg_main"])

        ttk.Label(dialog, text="自定义提示词模板（可使用占位符 {file_list} 和 {requirement}）：",
                  background=theme["bg_main"], foreground=theme["fg_text"]).pack(pady=10)

        text_area = scrolledtext.ScrolledText(dialog, wrap='word', width=70, height=20,
                                              bg=theme["bg_input"], fg=theme["fg_text"],
                                              insertbackground=theme["fg_text"])
        text_area.pack(padx=10, pady=5, fill='both', expand=True)
        text_area.insert('1.0', self.prompt_template)
        text_area.focus_set()

        def save():
            new_template = text_area.get("1.0", tk.END).strip()
            if not new_template:
                messagebox.showwarning("提示", "模板不能为空", parent=dialog)
                return
            self.prompt_template = new_template
            self.status_var.set("提示词模板已更新")
            dialog.destroy()

        btn_frame = ttk.Frame(dialog, style='TFrame')
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="保存", command=save).pack(side='left', padx=10)
        ttk.Button(btn_frame, text="取消", command=dialog.destroy).pack(side='left', padx=10)

    def export_prompt(self):
        visible = self.visible_files
        if not visible:
            messagebox.showinfo("提示", "当前没有剩余文件可导出")
            return

        has_requirement = '{requirement}' in self.prompt_template

        if has_requirement:
            dialog = tk.Toplevel(self.master)
            dialog.title("导出提示词 - 输入需求")
            dialog.geometry("600x400")
            dialog.transient(self.master)
            dialog.grab_set()

            theme = THEMES[self.current_theme]
            dialog.configure(bg=theme["bg_main"])

            ttk.Label(dialog, text="请输入您的具体需求描述：",
                      background=theme["bg_main"], foreground=theme["fg_text"]).pack(pady=10)

            text_area = scrolledtext.ScrolledText(dialog, wrap='word', width=70, height=15,
                                                  bg=theme["bg_input"], fg=theme["fg_text"],
                                                  insertbackground=theme["fg_text"])
            text_area.pack(padx=10, pady=5, fill='both', expand=True)
            text_area.focus_set()

            def confirm():
                requirement = text_area.get("1.0", tk.END).strip()
                if not requirement:
                    messagebox.showwarning("提示", "需求描述不能为空", parent=dialog)
                    return

                file_list_text = '\n'.join([f['rel'] for f in visible])
                prompt = self.prompt_template.replace('{file_list}', file_list_text).replace('{requirement}', requirement)
                self.copy_to_clipboard(prompt)
                self.status_var.set("已复制提示词到剪贴板，请粘贴给 AI")
                dialog.destroy()

            btn_frame = ttk.Frame(dialog, style='TFrame')
            btn_frame.pack(pady=10)
            ttk.Button(btn_frame, text="确认并复制", command=confirm).pack(side='left', padx=10)
            ttk.Button(btn_frame, text="取消", command=dialog.destroy).pack(side='left', padx=10)
        else:
            file_list_text = '\n'.join([f['rel'] for f in visible])
            prompt = self.prompt_template.replace('{file_list}', file_list_text)
            self.copy_to_clipboard(prompt)
            self.status_var.set("已复制提示词到剪贴板，请粘贴给 AI")

    def reset_processed(self):
        self.processed_files.clear()
        self.review_mode = False
        self.refresh_display()
        self.status_var.set("已重置，所有文件重新显示（普通模式）")

    def change_root_folder(self):
        """更改根文件夹"""
        selected_dir = filedialog.askdirectory(initialdir=self.root_path if os.path.exists(self.root_path) else "/")
        if not selected_dir:
            return
        self.set_root_path(selected_dir)

    def set_root_path(self, new_path):
        """设置新的根路径并重新扫描（过滤设置保留）"""
        if not os.path.isdir(new_path):
            messagebox.showerror("错误", f"路径不是有效文件夹：{new_path}")
            return
        self.root_path = new_path
        self.processed_files.clear()
        self.review_mode = False
        self.keyword_var.set("")
        self.current_filter = ""
        self.scan_files()
        self.refresh_display()
        self.status_var.set(f"已切换到目录: {self.root_path}，共 {len(self.all_files)} 个文件")

    def refresh_files(self):
        """手动刷新当前目录（过滤设置保留）"""
        self.scan_files()
        self.refresh_display()
        self.status_var.set(f"已刷新，共 {len(self.all_files)} 个文件")


if __name__ == '__main__':
    root = tk.Tk()
    app = FolderIndexerApp(root)
    root.mainloop()