from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QPushButton, QLabel,
    QFileDialog, QHBoxLayout, QVBoxLayout, QTextEdit, QCheckBox,
    QListWidget, QListWidgetItem, QSplitter, QSizePolicy, QFrame, QTreeWidgetItem,
    QLineEdit, QGridLayout, QScrollArea, QFormLayout, QProgressDialog
)
from PyQt5.QtGui import QIcon, QPixmap, QDragEnterEvent, QDropEvent, QTextCursor, QFontMetrics
from PyQt5.QtCore import Qt, QSize, QEvent, pyqtSignal, QObject, QThread
import sys
import os
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
import re
from collections import OrderedDict

class ImageDropLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.image_dropped_callback = None

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.webp']
        image_paths = []
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if os.path.isfile(path) and any(path.lower().endswith(ext) for ext in image_extensions):
                image_paths.append(path)
        if image_paths and self.image_dropped_callback:
            self.image_dropped_callback(image_paths)


class ReplaceWorker(QObject):
    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal(int, list)
    error = pyqtSignal(str)

    def __init__(self, parent_window, image_paths, find_text, replace_text):
        super().__init__()
        self.parent_window = parent_window
        self.image_paths = list(image_paths)
        self.find_text = find_text
        self.replace_text = replace_text
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        replacements = 0
        changed_paths = []
        total = len(self.image_paths)
        try:
            for index, image_path in enumerate(self.image_paths, start=1):
                if self._cancelled:
                    break
                meta, meta_key = self.parent_window._load_image_metadata(image_path)
                positive = meta.get("Positive prompt", "")
                negative = meta.get("Negative prompt", "")
                new_positive = positive.replace(self.find_text, self.replace_text)
                new_negative = negative.replace(self.find_text, self.replace_text)
                if new_positive != positive or new_negative != negative:
                    meta = OrderedDict(meta)
                    meta["Positive prompt"] = new_positive
                    meta["Negative prompt"] = new_negative
                    if not meta.get("Size"):
                        meta["Size"] = self.parent_window._infer_size_from_image(image_path)
                    self.parent_window._write_prompt_file(image_path, meta, meta_key)
                    replacements += 1
                    changed_paths.append(image_path)
                self.progress.emit(index, total, os.path.basename(image_path))
            self.finished.emit(replacements, changed_paths)
        except Exception as exc:
            self.error.emit(str(exc))
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Image Prompt Manager")
        self.setGeometry(100, 100, 1000, 700)

        self.folder_path = ""
        self.current_image_path = ""
        self.current_pixmap = QPixmap()
        self.current_metadata = OrderedDict()
        self.current_meta_key = None
        self.metadata_inputs = {}
        self.metadata_keys_order = []
        self.replace_thread = None
        self.replace_worker = None

        self.init_ui()
        self.statusBar().showMessage("Ready")

    def init_ui(self):
        # Widget trung tâm
        main_widget = QWidget()
        self.setCentralWidget(main_widget)

        # Layout chính
        main_layout = QVBoxLayout()
        main_widget.setLayout(main_layout)

        # Layout cho thanh chọn thư mục
        folder_layout = QHBoxLayout()

        self.btn_browse = QPushButton("Open Folder")
        self.btn_browse.setIcon(QIcon.fromTheme("folder"))
        # self.btn_browse.setFixedSize(32, 32)
        self.btn_browse.clicked.connect(self.choose_folder)

        self.lbl_folder = QLabel("Chưa chọn thư mục")
        self.lbl_folder.setStyleSheet("font-weight: bold; color: #FFFFFF; background-color: #333333; padding: 5px;")
        self.lbl_folder.setTextInteractionFlags(Qt.TextSelectableByMouse)

        folder_layout.addWidget(self.btn_browse)
        folder_layout.addWidget(self.lbl_folder)

        # Split panel chính chia làm 2: Trái (ảnh) - Phải (prompt)
        self.main_splitter = QSplitter(Qt.Horizontal)

        # ----- KHU HÌNH ẢNH (TRÁI) -----
        image_widget = QWidget()
        image_layout = QVBoxLayout()
        image_widget.setLayout(image_layout)
        image_widget.setMinimumWidth(400)

        self.lbl_image = ImageDropLabel("Kéo ảnh vào đây hoặc chọn từ danh sách")
        self.lbl_image.setAlignment(Qt.AlignCenter)
        self.lbl_image.setFrameShape(QFrame.Box)
        self.lbl_image.setMinimumHeight(400)
        self.lbl_image.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.lbl_image.image_dropped_callback = self.handle_dropped_images
        self.lbl_image.installEventFilter(self)

        self.list_images = QListWidget()
        self.list_images.setMinimumHeight(180)
        self.list_images.setViewMode(QListWidget.IconMode)
        self.list_images.setIconSize(QSize(100, 100))
        self.list_images.setResizeMode(QListWidget.Adjust)
        self.list_images.setMovement(QListWidget.Static)
        self.list_images.setSpacing(8)
        self.list_images.setUniformItemSizes(True)
        self.list_images.itemClicked.connect(self.display_selected_image)

        image_layout.addWidget(self.lbl_image, 3)
        image_layout.addWidget(self.list_images, 1)

        # ----- KHU PROMPT (PHẢI) -----
        # Tab Layout cho Prompt
        from PyQt5.QtWidgets import QTabWidget, QTreeWidget, QTreeWidgetItem
        self.tab_prompt = QTabWidget()
        self.tab_prompt.setMinimumWidth(300)

        # Tab Content (chỉ đọc metadata)
        self.tab_content = QWidget()
        content_layout = QVBoxLayout()
        self.tab_content.setLayout(content_layout)
        self.tree_metadata = QTreeWidget()
        self.tree_metadata.setHeaderLabels(["Keyword", "Content"])
        self.tree_metadata.setColumnCount(2)
        self.tree_metadata.setRootIsDecorated(False)
        self.tree_metadata.setEditTriggers(QTreeWidget.NoEditTriggers)
        self.tree_metadata.setWordWrap(True)
        content_layout.addWidget(self.tree_metadata)

        # Tab Edit (giữ layout cũ)
        self.tab_edit = QWidget()
        edit_layout = QVBoxLayout()
        self.tab_edit.setLayout(edit_layout)
        self.txt_positive = QTextEdit()
        self.txt_positive.setPlaceholderText("Positive Prompt (e.g. masterpiece, 8k, detailed)")
        self.txt_negative = QTextEdit()
        self.txt_negative.setPlaceholderText("Negative Prompt (e.g. low quality, blurry)")
        self.meta_scroll = QScrollArea()
        self.meta_scroll.setWidgetResizable(True)
        self.meta_scroll.setMinimumHeight(160)
        self.meta_form_container = QWidget()
        self.meta_form_layout = QFormLayout()
        self.meta_form_container.setLayout(self.meta_form_layout)
        self.meta_scroll.setWidget(self.meta_form_container)
        replace_widget = QWidget()
        replace_layout = QGridLayout()
        replace_widget.setLayout(replace_layout)
        replace_layout.setColumnStretch(0, 1)
        replace_layout.setColumnStretch(1, 1)
        self.txt_find = QLineEdit()
        self.txt_find.setPlaceholderText("Find text")
        self.txt_replace = QLineEdit()
        self.txt_replace.setPlaceholderText("Replace with")
        self.btn_find = QPushButton("Find")
        self.btn_find.clicked.connect(self.find_in_prompts)
        self.btn_replace = QPushButton("Replace")
        self.btn_replace.clicked.connect(self.replace_in_prompts)
        self.btn_replace_all = QPushButton("Replace All")
        self.btn_replace_all.clicked.connect(self.replace_all_in_prompts)
        replace_layout.addWidget(self.txt_find, 0, 0, 1, 2)
        replace_layout.addWidget(self.btn_find, 0, 2)
        replace_layout.addWidget(self.txt_replace, 1, 0, 1, 2)
        replace_layout.addWidget(self.btn_replace, 1, 2)
        replace_layout.addWidget(self.btn_replace_all, 2, 0, 1, 3)
        self.chk_autosave = QCheckBox("Auto Save")
        self.btn_save = QPushButton("Save")
        self.btn_save.clicked.connect(self.save_prompt_file)
        edit_layout.addWidget(self.txt_positive)
        edit_layout.addWidget(self.txt_negative)
        edit_layout.addWidget(self.meta_scroll)
        edit_layout.addWidget(replace_widget)
        edit_layout.addWidget(self.chk_autosave)
        edit_layout.addWidget(self.btn_save)

        self.tab_prompt.addTab(self.tab_content, "Content")
        self.tab_prompt.addTab(self.tab_edit, "Edit")

        # Thêm vào splitter
        self.main_splitter.addWidget(image_widget)
        self.main_splitter.addWidget(self.tab_prompt)
        self.main_splitter.setSizes([600, 400])
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 0)

        # Đặt tỉ lệ cho layout
        main_layout.addLayout(folder_layout, 0)
        main_layout.addWidget(self.main_splitter, 1)

    def choose_folder(self):
        initial_dir = self.folder_path if os.path.isdir(self.folder_path) else os.getcwd()
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục chứa ảnh", initial_dir)
        if folder:
            self.folder_path = folder
            self.lbl_folder.setText(folder)
            self.load_images_from_folder(folder)

    def load_images_from_folder(self, folder):
        self.list_images.clear()
        image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.webp']

        image_files = [f for f in os.listdir(folder) if any(f.lower().endswith(ext) for ext in image_extensions)]
        image_files.sort()
        metrics = QFontMetrics(self.list_images.font())

        total = len(image_files)
        progress = None
        if total:
            progress = QProgressDialog("Đang tải danh sách ảnh...", "Hủy", 0, total, self)
            progress.setWindowTitle("Đang tải ảnh")
            progress.setWindowModality(Qt.ApplicationModal)
            progress.setMinimumDuration(0)
            progress.setValue(0)

        for idx, file in enumerate(image_files, start=1):
            if progress and progress.wasCanceled():
                break
            full_path = os.path.join(folder, file)
            icon = QIcon(full_path)
            display_name = metrics.elidedText(file, Qt.ElideMiddle, 140)
            item = QListWidgetItem(icon, display_name)
            item.setData(Qt.UserRole, full_path)
            item.setToolTip(file)
            self.list_images.addItem(item)
            if progress:
                progress.setValue(idx)
                progress.setLabelText(f"Đang tải {file} ({idx}/{total})")
                QApplication.processEvents()

        if progress:
            progress.close()

        if self.list_images.count() > 0:
            self.list_images.setCurrentRow(0)
            self.display_selected_image(self.list_images.item(0))

    def display_selected_image(self, item):
        if self.chk_autosave.isChecked():
            self.save_prompt_file()

        image_path = item.data(Qt.UserRole)
        self.display_image_from_path(image_path)
        self._load_and_apply_metadata(image_path)

    def display_image_from_path(self, path):
        self.current_image_path = path
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            self.current_pixmap = pixmap
            self.update_image_display()
            self.statusBar().showMessage(path)
        else:
            self.current_pixmap = QPixmap()
            self.lbl_image.setText("Không thể hiển thị ảnh")
            self.statusBar().showMessage("Không thể hiển thị ảnh")

    def update_image_display(self):
        if not self.current_pixmap.isNull() and not self.lbl_image.size().isEmpty():
            scaled = self.current_pixmap.scaled(
                self.lbl_image.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self.lbl_image.setPixmap(scaled)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_image_display()

    def eventFilter(self, obj, event):
        if obj == self.lbl_image and event.type() == QEvent.Resize:
            self.update_image_display()
        return super().eventFilter(obj, event)

    def _extract_metadata_text(self, image_path):
        meta_text = None
        meta_key = None
        try:
            from PIL import Image
            import PIL

            with Image.open(image_path) as img:
                info = getattr(img, "info", {}) or {}
                for key in ['parameters', 'Description', 'prompt', 'Comment', 'Software']:
                    value = info.get(key)
                    if isinstance(value, str) and len(value) > 10:
                        meta_text = value
                        meta_key = key
                        break
                if meta_text is None and hasattr(img, '_getexif') and img._getexif():
                    exif = img._getexif()
                    if exif:
                        for tag, value in exif.items():
                            decoded = PIL.ExifTags.TAGS.get(tag, tag)
                            if decoded in ['UserComment', 'ImageDescription', 'XPComment', 'XPSubject'] and isinstance(value, str) and len(value) > 10:
                                meta_text = value
                                meta_key = decoded
                                break
        except Exception:
            meta_text = None
            meta_key = None
        return meta_text, meta_key

    def _format_metadata_text(self, meta):
        if not meta:
            return ""
        positive = (meta.get("Positive prompt") or "").strip()
        negative = (meta.get("Negative prompt") or "").strip()

        lines = []
        if positive:
            lines.append(positive)
        if negative:
            lines.append(f"Negative prompt: {negative}")

        extras = []
        for key, value in meta.items():
            if key in ("Positive prompt", "Negative prompt"):
                continue
            if value is None:
                continue
            value_str = str(value).strip()
            if not value_str:
                continue
            extras.append(f"{key}: {value_str}")
        if extras:
            lines.append(", ".join(extras))
        return "\n".join(lines).strip()

    def _looks_like_metadata(self, line):
        if not line:
            return False
        lower = line.strip().lower()
        if not lower or lower.startswith("negative prompt:"):
            return False
        if ": " in line:
            return True
        known_prefixes = [
            "steps:", "sampler:", "schedule type:", "cfg scale:", "seed:", "size:",
            "model:", "model hash:", "model version:", "clip skip:", "lora",
            "loras:", "lora hashes:", "lorahash:", "hash:", "vae:", "vae hash:",
            "h-nag:", "version:", "face restoration:", "denoising strength:",
            "token merging ratio:", "hires", "upscaler:", "tiling:", "ensd:",
            "refiner:", "refiner switch:", "controlnet", "cfg rescale:", "scheduler:",
            "clip skip:", "vae hash:"
        ]
        return any(lower.startswith(prefix) for prefix in known_prefixes)

    def _split_metadata_pairs(self, text):
        segments = []
        current = []
        depth_round = depth_square = depth_curly = 0
        for ch in text:
            if ch == ',' and depth_round == depth_square == depth_curly == 0:
                segment = ''.join(current).strip()
                if segment:
                    segments.append(segment)
                current = []
                continue
            current.append(ch)
            if ch == '(':
                depth_round += 1
            elif ch == ')':
                depth_round = max(0, depth_round - 1)
            elif ch == '[':
                depth_square += 1
            elif ch == ']':
                depth_square = max(0, depth_square - 1)
            elif ch == '{':
                depth_curly += 1
            elif ch == '}':
                depth_curly = max(0, depth_curly - 1)
        if current:
            segment = ''.join(current).strip()
            if segment:
                segments.append(segment)

        pairs = []
        for segment in segments:
            if ':' not in segment:
                continue
            key, value = segment.split(':', 1)
            pairs.append((key.strip(), value.strip().strip(',')))
        return pairs

    def _to_int(self, value):
        if value is None:
            return None
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return None

    def _clear_metadata_form(self):
        while self.meta_form_layout.count():
            item = self.meta_form_layout.takeAt(0)
            if item:
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
        self.metadata_inputs = {}
        self.metadata_keys_order = []

    def _populate_metadata_inputs(self, meta):
        self._clear_metadata_form()
        added_field = False
        for key, value in meta.items():
            if key in ("Positive prompt", "Negative prompt"):
                continue
            widget = QTextEdit() if isinstance(value, str) and ("\n" in value or len(value) > 160) else QLineEdit()
            if isinstance(widget, QTextEdit):
                widget.setPlainText(str(value))
                widget.setFixedHeight(80)
            else:
                widget.setText(str(value))
            self.meta_form_layout.addRow(f"{key}", widget)
            self.metadata_inputs[key] = widget
            self.metadata_keys_order.append(key)
            added_field = True
        if not added_field:
            placeholder = QLabel("No additional metadata fields")
            self.meta_form_layout.addRow("", placeholder)

    def _gather_metadata_from_inputs(self):
        meta = OrderedDict()
        meta["Positive prompt"] = self.txt_positive.toPlainText().strip()
        meta["Negative prompt"] = self.txt_negative.toPlainText().strip()
        for key in self.metadata_keys_order:
            widget = self.metadata_inputs.get(key)
            if widget is None:
                continue
            if isinstance(widget, QTextEdit):
                value = widget.toPlainText().strip()
            else:
                value = widget.text().strip()
            meta[key] = value
        return meta

    def _update_prompt_editors(self, meta):
        positive = meta.get("Positive prompt", "") if meta else ""
        negative = meta.get("Negative prompt", "") if meta else ""
        self.txt_positive.blockSignals(True)
        self.txt_positive.setPlainText(positive)
        self.txt_positive.blockSignals(False)
        self.txt_negative.blockSignals(True)
        self.txt_negative.setPlainText(negative)
        self.txt_negative.blockSignals(False)

    def _populate_metadata_tree(self, meta):
        self.tree_metadata.clear()
        if not meta:
            return
        import textwrap
        wrap_len = 80
        for key, value in meta.items():
            if value is None:
                continue
            display_value = str(value)
            if len(display_value) > wrap_len:
                display_value = '\n'.join(textwrap.wrap(display_value, wrap_len))
            item = QTreeWidgetItem([key, display_value])
            self.tree_metadata.addTopLevelItem(item)

    def _load_and_apply_metadata(self, image_path):
        meta, meta_key = self._load_image_metadata(image_path)
        self.current_metadata = meta
        self.current_meta_key = meta_key
        self._update_prompt_editors(meta)
        self._populate_metadata_inputs(meta)
        self._populate_metadata_tree(meta)

    def _load_image_metadata(self, image_path):
        meta_text, meta_key = self._extract_metadata_text(image_path)
        parsed_meta = self.parse_metadata(meta_text) if meta_text else OrderedDict()

        prompt_path = os.path.splitext(image_path)[0] + ".txt"
        txt_positive = txt_negative = txt_size = None
        if os.path.exists(prompt_path):
            try:
                with open(prompt_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                parts = content.split("###")
                if parts:
                    txt_positive = parts[0].strip()
                if len(parts) > 1:
                    txt_negative = parts[1].strip()
                if len(parts) > 2 and parts[2].strip():
                    txt_size = parts[2].strip()
            except Exception:
                txt_positive = txt_negative = txt_size = None

        meta = OrderedDict()
        meta["Positive prompt"] = txt_positive if txt_positive is not None else parsed_meta.get("Positive prompt", "")
        meta["Negative prompt"] = txt_negative if txt_negative is not None else parsed_meta.get("Negative prompt", "")

        for key, value in parsed_meta.items():
            if key in ("Positive prompt", "Negative prompt"):
                continue
            meta[key] = value

        if txt_size:
            meta["Size"] = txt_size
        if not meta.get("Size"):
            meta["Size"] = self._infer_size_from_image(image_path)

        if "Seed" not in meta:
            seed_value = parsed_meta.get("Seed") if parsed_meta else None
            if seed_value:
                meta["Seed"] = seed_value

        return meta, meta_key

    def _find_in_text_edit(self, text_edit, query):
        if not query:
            return False
        original_cursor = text_edit.textCursor()
        cursor = text_edit.textCursor()
        cursor.movePosition(QTextCursor.Start)
        text_edit.setTextCursor(cursor)
        found = text_edit.find(query)
        if not found:
            text_edit.setTextCursor(original_cursor)
            return False
        text_edit.setFocus()
        return True

    def find_in_prompts(self):
        query = self.txt_find.text().strip()
        if not query:
            self.statusBar().showMessage("Nhập nội dung cần tìm")
            return
        if self._find_in_text_edit(self.txt_positive, query):
            self.tab_prompt.setCurrentWidget(self.tab_edit)
            self.statusBar().showMessage("Đã tìm thấy trong Positive Prompt")
            return
        if self._find_in_text_edit(self.txt_negative, query):
            self.tab_prompt.setCurrentWidget(self.tab_edit)
            self.statusBar().showMessage("Đã tìm thấy trong Negative Prompt")
            return
        self.statusBar().showMessage("Không tìm thấy nội dung cần tìm")

    def replace_in_prompts(self):
        find_text = self.txt_find.text().strip()
        replace_text = self.txt_replace.text()
        if not find_text:
            self.statusBar().showMessage("Nhập nội dung cần thay thế")
            return
        replaced = False
        for text_edit in (self.txt_positive, self.txt_negative):
            content = text_edit.toPlainText()
            if find_text in content:
                new_content = content.replace(find_text, replace_text)
                if new_content != content:
                    text_edit.blockSignals(True)
                    text_edit.setPlainText(new_content)
                    text_edit.blockSignals(False)
                    replaced = True
        if replaced:
            self.current_metadata = self._gather_metadata_from_inputs()
            self._populate_metadata_tree(self.current_metadata)
            self.statusBar().showMessage("Đã thay thế nội dung")
            if self.chk_autosave.isChecked() and self.current_image_path:
                meta = OrderedDict(self.current_metadata)
                if not meta.get("Size") and self.current_image_path:
                    meta["Size"] = self._infer_size_from_image(self.current_image_path)
                self._write_prompt_file(self.current_image_path, meta, self.current_meta_key)
        else:
            self.statusBar().showMessage("Không tìm thấy nội dung để thay thế")

    def replace_all_in_prompts(self):
        find_text = self.txt_find.text().strip()
        replace_text = self.txt_replace.text()
        if not find_text:
            self.statusBar().showMessage("Nhập nội dung cần thay thế")
            return
        if not self.folder_path or self.list_images.count() == 0:
            self.statusBar().showMessage("Chưa có thư mục hoặc ảnh để thay thế")
            return

        image_paths = []
        for idx in range(self.list_images.count()):
            item = self.list_images.item(idx)
            if not item:
                continue
            path = item.data(Qt.UserRole)
            if path:
                image_paths.append(path)

        total = len(image_paths)
        if total == 0:
            self.statusBar().showMessage("Không tìm thấy ảnh hợp lệ trong thư mục")
            return

        self.replace_worker = ReplaceWorker(self, image_paths, find_text, replace_text)
        self.replace_thread = QThread(self)
        self.replace_worker.moveToThread(self.replace_thread)

        progress = QProgressDialog("Đang thay thế nội dung trong ảnh...", "Hủy", 0, total, self)
        progress.setWindowTitle("Đang xử lý")
        progress.setWindowModality(Qt.ApplicationModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)

        def on_progress(current, maximum, name):
            progress.setMaximum(maximum)
            progress.setValue(current)
            progress.setLabelText(f"Đang xử lý {name} ({current}/{maximum})")
            QApplication.processEvents()

        def cleanup():
            if self.replace_thread:
                thread = self.replace_thread
                self.replace_thread = None
                thread.quit()
                thread.wait()
                thread.deleteLater()
            if self.replace_worker:
                worker = self.replace_worker
                self.replace_worker = None
                worker.deleteLater()

        def on_finished(replacements, changed_paths):
            cancelled = progress.wasCanceled()
            progress.close()
            cleanup()
            if cancelled:
                self.statusBar().showMessage("Đã hủy thao tác thay thế")
                return
            if replacements:
                self.statusBar().showMessage(f"Đã thay thế trong {replacements} ảnh")
                if self.current_image_path and self.current_image_path in changed_paths:
                    self._load_and_apply_metadata(self.current_image_path)
            else:
                self.statusBar().showMessage("Không tìm thấy nội dung để thay thế trong thư mục")

        def on_error(message):
            progress.close()
            cleanup()
            self.statusBar().showMessage(f"Lỗi khi thay thế: {message}")

        progress.canceled.connect(self.replace_worker.cancel)
        self.replace_thread.started.connect(self.replace_worker.run)
        self.replace_worker.progress.connect(on_progress)
        self.replace_worker.finished.connect(on_finished)
        self.replace_worker.error.connect(on_error)

        self.replace_thread.start()

    def _normalize_prompt_text(self, text):
        if not text:
            return ""
        parts = [segment.strip() for segment in text.split("\n") if segment.strip()]
        if not parts:
            return ""
        return " ".join(parts)

    def _size_string_from_dimensions(self, width, height):
        if not width or not height:
            return "832x1216"
        if width > height:
            return "1216x832"
        if width < height:
            return "832x1216"
        return "1024x1024"

    def _infer_size_from_image(self, image_path):
        try:
            from PIL import Image

            with Image.open(image_path) as img:
                width, height = img.size
        except Exception:
            return "832x1216"
        return self._size_string_from_dimensions(width, height)

    def _write_prompt_file(self, image_path, meta, meta_key=None):
        if meta is None:
            return

        meta = OrderedDict(meta)
        meta["Positive prompt"] = self._normalize_prompt_text(meta.get("Positive prompt", ""))
        meta["Negative prompt"] = self._normalize_prompt_text(meta.get("Negative prompt", ""))

        if not meta.get("Positive prompt"):
            meta["Positive prompt"] = "1boy, 1 man"
        if not meta.get("Negative prompt"):
            meta["Negative prompt"] = "(1girl, woman, female)"
        if not meta.get("Size"):
            meta["Size"] = self._infer_size_from_image(image_path)

        formatted_meta = self._format_metadata_text(meta)

        ext = os.path.splitext(image_path)[1].lower()
        target_key = meta_key
        if meta_key is None:
            _, target_key = self._extract_metadata_text(image_path)
        if ext in ['.png'] and formatted_meta:
            try:
                from PIL import Image, PngImagePlugin

                with Image.open(image_path) as img:
                    pnginfo = PngImagePlugin.PngInfo()
                    existing_info = getattr(img, 'info', {}) or {}
                    key_to_use = target_key or 'parameters'
                    for key, value in existing_info.items():
                        if not isinstance(value, str):
                            continue
                        if key == key_to_use:
                            continue
                        pnginfo.add_text(key, value)
                    pnginfo.add_text(key_to_use, formatted_meta)
                    img.save(image_path, pnginfo=pnginfo)
                return
            except Exception:
                pass

        prompt_path = os.path.splitext(image_path)[0] + ".txt"
        content = f"{meta.get('Positive prompt', '')}###{meta.get('Negative prompt', '')}###{meta.get('Size', '')}"
        with open(prompt_path, "w", encoding="utf-8") as f:
            f.write(content)

    def parse_metadata(self, content):
        if not content:
            return OrderedDict()
        blocks = re.split(r"(?:\r?\n){2,}", content.strip())
        selected_meta = OrderedDict()
        for block in blocks:
            meta, has_tony = self.parse_block(block)
            if meta:
                if has_tony:
                    return meta
                if not selected_meta:
                    selected_meta = meta
        return selected_meta

    def parse_block(self, block):
        lines = [line.strip() for line in block.strip().split("\n") if line.strip()]
        if not lines:
            return OrderedDict(), False

        positive_lines = []
        negative_lines = []
        metadata_pairs = OrderedDict()
        in_negative = False
        has_tony = any(line.lower().endswith("tony") for line in lines)

        for line in lines:
            stripped = line.strip()
            lower_line = stripped.lower()
            if lower_line.startswith("negative prompt:"):
                in_negative = True
                remainder = stripped.split(":", 1)[1].strip()
                if remainder:
                    negative_lines.append(remainder)
                continue
            if in_negative and not self._looks_like_metadata(stripped):
                negative_lines.append(stripped)
                continue
            if self._looks_like_metadata(stripped):
                in_negative = False
                for key, value in self._split_metadata_pairs(stripped):
                    metadata_pairs[key] = value
                continue
            if in_negative:
                negative_lines.append(stripped)
            else:
                positive_lines.append(stripped)

        positive_prompt = " ".join(positive_lines).strip()
        negative_prompt = " ".join(negative_lines).strip()

        meta = OrderedDict()
        meta["Positive prompt"] = positive_prompt
        meta["Negative prompt"] = negative_prompt

        for key, value in metadata_pairs.items():
            meta[key] = value

        width = self._to_int(metadata_pairs.get("Width"))
        height = self._to_int(metadata_pairs.get("Height"))
        if ("Size" not in meta or not meta.get("Size")) and width and height:
            meta["Size"] = self._size_string_from_dimensions(width, height)
        if "Seed" not in meta and metadata_pairs.get("Seed") is not None:
            meta["Seed"] = metadata_pairs.get("Seed")

        return meta, has_tony


    def save_prompt_file(self):
        if not self.current_image_path:
            return

        meta = self._gather_metadata_from_inputs()
        if not meta.get("Size"):
            meta["Size"] = self._infer_size_from_image(self.current_image_path)
        self.current_metadata = meta
        self._write_prompt_file(self.current_image_path, meta, self.current_meta_key)
        self._populate_metadata_tree(meta)
        self.statusBar().showMessage("Đã lưu metadata vào ảnh")

    def handle_dropped_images(self, image_paths):
        if not image_paths:
            return

        # Cập nhật folder_path và label
        folder = os.path.dirname(image_paths[0])
        self.folder_path = folder
        self.lbl_folder.setText(folder)

        # Lưu danh sách ảnh vào thư mục đó (không trùng)
        image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.webp']
        all_images = sorted([f for f in os.listdir(folder) if any(f.lower().endswith(ext) for ext in image_extensions)])

        self.list_images.clear()
        metrics = QFontMetrics(self.list_images.font())
        for file in all_images:
            full_path = os.path.join(folder, file)
            icon = QIcon(full_path)
            display_name = metrics.elidedText(file, Qt.ElideMiddle, 140)
            item = QListWidgetItem(icon, display_name)
            item.setData(Qt.UserRole, full_path)
            item.setToolTip(file)
            self.list_images.addItem(item)

        # Hiển thị ảnh đầu tiên trong danh sách kéo vào
        self.list_images.setCurrentRow(0)
        self.display_image_from_path(image_paths[0])
        self._load_and_apply_metadata(image_paths[0])

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key_Right, Qt.Key_D):
            self.navigate_image(1)
        elif key in (Qt.Key_Left, Qt.Key_A):
            self.navigate_image(-1)

    def navigate_image(self, step):
        current_row = self.list_images.currentRow()
        total = self.list_images.count()
        next_row = (current_row + step) % total
        self.list_images.setCurrentRow(next_row)
        item = self.list_images.item(next_row)
        if item:
            self.display_selected_image(item)

    


if __name__ == '__main__':
    app = QApplication(sys.argv)
    try:
        with open("ElegantDark.qss", "r") as f:
            app.setStyleSheet(f.read())
    except:
        pass
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())