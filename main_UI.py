from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QPushButton, QLabel,
    QFileDialog, QHBoxLayout, QVBoxLayout, QTextEdit, QCheckBox,
    QListWidget, QListWidgetItem, QSplitter, QSizePolicy, QFrame, QTreeWidgetItem,
    QLineEdit, QGridLayout, QProgressDialog, QComboBox
)
from PyQt5.QtGui import QIcon, QPixmap, QDragEnterEvent, QDropEvent, QTextCursor, QFontMetrics
from PyQt5.QtCore import Qt, QSize, QEvent, pyqtSignal, QObject, QThread
import sys
import os
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)

import re
from collections import OrderedDict

# Default value used when Add Meta tab's Negative prompt is left empty.
DEFAULT_NEGATIVE_PROMPT = (
    "logo, source pony, beard, (yellow skin:0.8), ((long hair:1.5)), "
    "((child male, minor)), ((underage)), (childish), (adolescent), ((young girl))"
)


class ImageDropLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.image_dropped_callback = None

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
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
                _meta_for_tree, meta_key, meta_text = self.parent_window._load_image_metadata(image_path)
                original_text = meta_text or ""
                updated_text = original_text.replace(self.find_text, self.replace_text)
                if updated_text != original_text:
                    self.parent_window._write_metadata_text(image_path, updated_text, meta_key)
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
        self.setGeometry(100, 100, 1100, 750)

        self.folder_path = ""
        self.current_image_path = ""
        self.current_pixmap = QPixmap()
        self.current_metadata_dict = OrderedDict()
        self.current_meta_key = None
        self.current_metadata_text = ""
        self.replace_thread = None
        self.replace_worker = None
        self.default_negative_prompt = DEFAULT_NEGATIVE_PROMPT
        self._image_type_filter = 'all'

        self.init_ui()
        self.statusBar().showMessage("Ready")

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)

        main_layout = QVBoxLayout()
        main_widget.setLayout(main_layout)

        folder_layout = QHBoxLayout()
        self.btn_browse = QPushButton("Open Folder")
        self.btn_browse.setIcon(QIcon.fromTheme("folder"))
        self.btn_browse.clicked.connect(self.choose_folder)

        self.lbl_folder = QLabel("Chưa chọn thư mục")
        self.lbl_folder.setStyleSheet("font-weight: bold; color: #FFFFFF; background-color: #333333; padding: 5px;")
        self.lbl_folder.setTextInteractionFlags(Qt.TextSelectableByMouse)

        folder_layout.addWidget(self.btn_browse)
        folder_layout.addWidget(self.lbl_folder)

        self.main_splitter = QSplitter(Qt.Horizontal)

        # ----- IMAGE PANEL (LEFT) -----
        image_widget = QWidget()
        image_layout = QVBoxLayout()
        image_widget.setLayout(image_layout)
        image_widget.setMinimumWidth(420)

        self.lbl_image = ImageDropLabel("Kéo ảnh vào đây hoặc chọn từ danh sách")
        self.lbl_image.setAlignment(Qt.AlignCenter)
        self.lbl_image.setFrameShape(QFrame.Box)
        self.lbl_image.setMinimumHeight(420)
        self.lbl_image.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.lbl_image.image_dropped_callback = self.handle_dropped_images
        self.lbl_image.installEventFilter(self)

        self.list_images = QListWidget()
        self.list_images.setMinimumHeight(200)
        self.list_images.setViewMode(QListWidget.IconMode)
        self.list_images.setIconSize(QSize(100, 100))
        self.list_images.setResizeMode(QListWidget.Adjust)
        self.list_images.setMovement(QListWidget.Static)
        self.list_images.setSpacing(8)
        self.list_images.setUniformItemSizes(True)
        self.list_images.itemClicked.connect(self.display_selected_image)

        image_layout.addWidget(self.lbl_image, 3)
        image_layout.addWidget(self.list_images, 1)

        # ----- PROMPT PANEL (RIGHT) -----
        from PyQt5.QtWidgets import QTabWidget, QTreeWidget, QPlainTextEdit
        self.tab_prompt = QTabWidget()
        self.tab_prompt.setMinimumWidth(340)

        # Tab Content (readonly)
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

        # Tab Edit (legacy)
        self.tab_edit = QWidget()
        edit_layout = QVBoxLayout()
        self.tab_edit.setLayout(edit_layout)

        self.txt_metadata = QTextEdit()
        self.txt_metadata.setPlaceholderText("Metadata (original parse block)")
        self.txt_metadata.setAcceptRichText(False)

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

        edit_layout.addWidget(self.txt_metadata)
        edit_layout.addWidget(replace_widget)
        edit_layout.addWidget(self.chk_autosave)
        edit_layout.addWidget(self.btn_save)

        # Tab Add Meta
        self.tab_add_meta = QWidget()
        add_layout = QVBoxLayout()
        self.tab_add_meta.setLayout(add_layout)

        self.lbl_add_filter = QLabel("Filter images")
        self.cbo_add_image = QComboBox()
        self.cbo_add_image.addItem("All images", "all")
        self.cbo_add_image.addItem("PNG (*.png)", "png")
        self.cbo_add_image.addItem("JPG/JPEG (*.jpg;*.jpeg)", "jpg")
        self.cbo_add_image.addItem("WEBP (*.webp)", "webp")
        self.cbo_add_image.addItem("BMP (*.bmp)", "bmp")
        self.cbo_add_image.addItem("Non-PNG (everything except .png)", "non_png")
        self.cbo_add_image.addItem("Other formats", "other")
        self.cbo_add_image.currentIndexChanged.connect(self.on_add_meta_filter_changed)

        self.lbl_add_pos = QLabel("Positive prompt")
        self.txt_add_pos = QPlainTextEdit()
        self.txt_add_pos.setPlaceholderText("Nhập Positive prompt...")

        self.lbl_add_neg = QLabel("Negative prompt")
        self.txt_add_neg = QPlainTextEdit()
        self.txt_add_neg.setPlaceholderText("Nhập Negative prompt... (để trống sẽ dùng mặc định)")

        self.lbl_add_size = QLabel("Size (from image)")
        self.txt_add_size = QLineEdit()
        self.txt_add_size.setReadOnly(True)

        self.lbl_add_png_status = QLabel("")
        self.lbl_add_png_status.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.btn_save_meta_to_image = QPushButton("Save Meta to Image")
        self.btn_save_meta_to_image.clicked.connect(self.save_meta_to_image)
        self.btn_save_meta_to_image.setEnabled(False)

        add_layout.addWidget(self.lbl_add_filter)
        add_layout.addWidget(self.cbo_add_image)

        add_layout.addWidget(self.lbl_add_pos)
        add_layout.addWidget(self.txt_add_pos, 2)
        add_layout.addWidget(self.lbl_add_neg)
        add_layout.addWidget(self.txt_add_neg, 2)
        add_layout.addWidget(self.lbl_add_size)
        add_layout.addWidget(self.txt_add_size)
        add_layout.addWidget(self.lbl_add_png_status)
        add_layout.addWidget(self.btn_save_meta_to_image)

        self.tab_prompt.addTab(self.tab_content, "Content")
        self.tab_prompt.addTab(self.tab_edit, "Edit")
        self.tab_prompt.addTab(self.tab_add_meta, "Add Meta")

        self.main_splitter.addWidget(image_widget)
        self.main_splitter.addWidget(self.tab_prompt)
        self.main_splitter.setSizes([650, 450])
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 0)

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
            progress = QProgressDialog("Loading Image", "Hủy", 0, total, self)
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


        self._apply_image_type_filter()

        if self.list_images.count() > 0:
            for i in range(self.list_images.count()):
                item = self.list_images.item(i)
                if item and not item.isHidden():
                    self.list_images.setCurrentRow(i)
                    self.display_selected_image(item)
                    break
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
            scaled = self.current_pixmap.scaled(self.lbl_image.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
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

    def _prepare_metadata_for_tree(self, meta, image_path):
        prepared = OrderedDict(meta or {})
        if not prepared.get("Size") and image_path:
            inferred_size = self._infer_size_from_image(image_path)
            if inferred_size:
                prepared["Size"] = inferred_size
        return prepared

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
        meta, meta_key, meta_text = self._load_image_metadata(image_path)
        self.current_metadata_dict = meta
        self.current_meta_key = meta_key
        self.current_metadata_text = meta_text or ""

        self.txt_metadata.blockSignals(True)
        self.txt_metadata.setPlainText(self.current_metadata_text)
        self.txt_metadata.blockSignals(False)
        self._populate_metadata_tree(meta)

        self._update_add_meta_tab(meta, meta_key, meta_text)

    def _load_image_metadata(self, image_path):
        meta_text, meta_key = self._extract_metadata_text(image_path)
        parsed_meta = self.parse_metadata(meta_text) if meta_text else OrderedDict()

        prompt_path = os.path.splitext(image_path)[0] + ".txt"
        sidecar_text = None
        if os.path.exists(prompt_path):
            try:
                with open(prompt_path, "r", encoding="utf-8") as f:
                    sidecar_text = f.read()
            except Exception:
                sidecar_text = None

        if (not meta_text or not meta_text.strip()) and sidecar_text:
            candidate = sidecar_text.strip()
            if candidate.count("###") >= 2:
                parts = candidate.split("###")
                parsed_meta = OrderedDict()
                parsed_meta["Positive prompt"] = parts[0].strip()
                parsed_meta["Negative prompt"] = parts[1].strip() if len(parts) > 1 else ""
                if len(parts) > 2 and parts[2].strip():
                    parsed_meta["Size"] = parts[2].strip()
                meta_text = self._format_metadata_text(parsed_meta)
            elif candidate:
                meta_text = candidate
                parsed_meta = self.parse_metadata(meta_text)

        parsed_meta = OrderedDict(parsed_meta) if parsed_meta else OrderedDict()
        meta_for_tree = self._prepare_metadata_for_tree(parsed_meta, image_path)

        if meta_text is None:
            meta_text = self._format_metadata_text(parsed_meta) if parsed_meta else ""

        return meta_for_tree, meta_key, meta_text

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
        if self._find_in_text_edit(self.txt_metadata, query):
            self.tab_prompt.setCurrentWidget(self.tab_edit)
            self.statusBar().showMessage("Đã tìm thấy trong metadata")
            return
        self.statusBar().showMessage("Không tìm thấy nội dung cần tìm")

    def replace_in_prompts(self):
        find_text = self.txt_find.text().strip()
        replace_text = self.txt_replace.text()
        if not find_text:
            self.statusBar().showMessage("Nhập nội dung cần thay thế")
            return
        content = self.txt_metadata.toPlainText()
        if find_text not in content:
            self.statusBar().showMessage("Không tìm thấy nội dung để thay thế")
            return
        new_content = content.replace(find_text, replace_text)
        if new_content == content:
            self.statusBar().showMessage("Không tìm thấy nội dung để thay thế")
            return
        self.txt_metadata.blockSignals(True)
        self.txt_metadata.setPlainText(new_content)
        self.txt_metadata.blockSignals(False)
        self.current_metadata_text = new_content
        parsed_meta = self.parse_metadata(new_content)
        self.current_metadata_dict = self._prepare_metadata_for_tree(parsed_meta, self.current_image_path)
        self._populate_metadata_tree(self.current_metadata_dict)
        self.statusBar().showMessage("Đã thay thế nội dung")
        if self.chk_autosave.isChecked() and self.current_image_path:
            used_key = self._write_metadata_text(self.current_image_path, new_content, self.current_meta_key)
            if used_key and used_key != self.current_meta_key:
                self.current_meta_key = used_key

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

        progress = QProgressDialog, QComboBox("Đang thay thế nội dung trong ảnh...", "Hủy", 0, total, self)
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

    def _size_string_from_dimensions(self, width, height):
        if not width or not height:
            return "832x1216"
        if width > height:
            return f"{width}x{height}"
        if width < height:
            return f"{width}x{height}"
        return f"{width}x{height}"

    def _infer_size_from_image(self, image_path):
        try:
            from PIL import Image
            with Image.open(image_path) as img:
                width, height = img.size
        except Exception:
            return "832x1216"
        return self._size_string_from_dimensions(width, height)

    def _write_metadata_text(self, image_path, text, meta_key=None):
        if text is None:
            text = ""

        ext = os.path.splitext(image_path)[1].lower()
        target_key = meta_key
        if meta_key is None:
            _, target_key = self._extract_metadata_text(image_path)

        if ext == '.png':
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
                    pnginfo.add_text(key_to_use or 'parameters', text)
                    img.save(image_path, pnginfo=pnginfo)
                return key_to_use or 'parameters'
            except Exception:
                pass

        prompt_path = os.path.splitext(image_path)[0] + ".txt"
        with open(prompt_path, "w", encoding="utf-8") as f:
            f.write(text)
        return None

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

        text = self.txt_metadata.toPlainText()
        self.current_metadata_text = text
        parsed_meta = self.parse_metadata(text)
        self.current_metadata_dict = self._prepare_metadata_for_tree(parsed_meta, self.current_image_path)
        used_key = self._write_metadata_text(self.current_image_path, text, self.current_meta_key)
        if used_key and used_key != self.current_meta_key:
            self.current_meta_key = used_key
        self._populate_metadata_tree(self.current_metadata_dict)
        self._update_add_meta_tab(self.current_metadata_dict, self.current_meta_key, self.current_metadata_text)
        self.statusBar().showMessage("Đã lưu metadata vào ảnh")

    # ---------- Add Meta ----------
    def _is_meaningful_metadata(self, meta: OrderedDict) -> bool:
        """Meaningful = has any parsed prompt/data beyond inferred Size-only."""
        if not meta:
            return False
        positive = (meta.get("Positive prompt") or "").strip()
        negative = (meta.get("Negative prompt") or "").strip()
        if positive or negative:
            return True
        for key, value in meta.items():
            if key in ("Positive prompt", "Negative prompt", "Size"):
                continue
            if value is None:
                continue
            if str(value).strip():
                return True
        return False


    def _update_add_meta_tab(self, meta_for_tree, meta_key, meta_text):
        if not self.current_image_path:
            self.btn_save_meta_to_image.setEnabled(False)
            self.lbl_add_png_status.setText("")
            return

        size = self._infer_size_from_image(self.current_image_path)
        self.txt_add_size.setText(size)

        positive = (meta_for_tree.get("Positive prompt") or "").strip() if meta_for_tree else ""
        negative = (meta_for_tree.get("Negative prompt") or "").strip() if meta_for_tree else ""
        self.txt_add_pos.setPlainText(positive)
        self.txt_add_neg.setPlainText(negative)

        is_png = self.current_image_path.lower().endswith(".png")
        if is_png:
            self.lbl_add_png_status.setStyleSheet("font-weight: bold; color: #17a24b;")
            self.lbl_add_png_status.setText("PNG detected: metadata will be embedded into the image.")
        else:
            self.lbl_add_png_status.setStyleSheet("font-weight: bold; color: #d11b1b;")
            self.lbl_add_png_status.setText("Not PNG: file will be converted & saved as PNG with embedded metadata.")

        enable = (not is_png) or (is_png and (not self._is_meaningful_metadata(meta_for_tree)))
        self.btn_save_meta_to_image.setEnabled(enable)

    def on_add_meta_filter_changed(self, _index: int):
        """Filter the left thumbnail list by image type (PNG/JPG/...)."""
        self._image_type_filter = self.cbo_add_image.currentData() or "all"
        self._apply_image_type_filter()

    def _apply_image_type_filter(self):
        wanted = getattr(self, "_image_type_filter", "all") or "all"

        def match(path: str) -> bool:
            ext = os.path.splitext(path)[1].lower()
            if wanted == "all":
                return True
            if wanted == "png":
                return ext == ".png"
            if wanted == "jpg":
                return ext in (".jpg", ".jpeg")
            if wanted == "webp":
                return ext == ".webp"
            if wanted == "bmp":
                return ext == ".bmp"
            if wanted == "non_png":
                return ext != ".png"
            if wanted == "other":
                return ext not in (".png", ".jpg", ".jpeg", ".webp", ".bmp")
            return True

        any_visible = False
        for i in range(self.list_images.count()):
            item = self.list_images.item(i)
            if not item:
                continue
            path = item.data(Qt.UserRole)
            visible = bool(path) and match(path)
            item.setHidden(not visible)
            any_visible = any_visible or visible

        # Ensure current selection stays visible
        current = self.list_images.currentItem()
        if current is None or current.isHidden():
            for i in range(self.list_images.count()):
                item = self.list_images.item(i)
                if item and not item.isHidden():
                    self.list_images.setCurrentRow(i)
                    self.display_selected_image(item)
                    break

        if not any_visible:
            self.lbl_image.setText("No images match the selected filter.")


    def _ensure_unique_png_path(self, src_path: str) -> str:
        folder = os.path.dirname(src_path)
        stem = os.path.splitext(os.path.basename(src_path))[0]
        candidate = os.path.join(folder, f"{stem}.png")
        if not os.path.exists(candidate):
            return candidate
        i = 1
        while True:
            candidate = os.path.join(folder, f"{stem}_meta_{i}.png")
            if not os.path.exists(candidate):
                return candidate
            i += 1

    def _build_stable_diffusion_metadata_text(self, positive: str, negative: str, size: str) -> str:
        """
        Stable Diffusion (A1111-style) prompt format:
            <positive>
            Negative prompt: <negative>
            Steps: ..., Sampler: ..., CFG scale: ..., Seed: ..., Size: WxH, Version: ...
        """
        positive = (positive or "").strip()
        negative = (negative or "").strip()
        size = (size or "").strip()

        extras_defaults = OrderedDict([
            ("Steps", "25"),
            ("Sampler", "Euler a"),
            ("Schedule type", "Automatic"),
            ("CFG scale", "7"),
            ("Seed", "0"),
            ("Size", size or "832x1216"),
            ("Version", "v1.10.1"),
        ])

        lines = []
        if positive:
            lines.append(positive)
        if negative:
            lines.append(f"Negative prompt: {negative}")
        else:
            lines.append("Negative prompt:")

        extras_line = ", ".join([f"{k}: {v}" for k, v in extras_defaults.items() if v is not None and str(v).strip()])
        if extras_line:
            lines.append(extras_line)
        return "\n".join(lines).strip()

    def save_meta_to_image(self):
        if not self.current_image_path:
            return

        positive = self.txt_add_pos.toPlainText().strip()
        negative = self.txt_add_neg.toPlainText().strip()
        if not negative:
            negative = (self.default_negative_prompt or "").strip()

        size = self._infer_size_from_image(self.current_image_path)
        self.txt_add_size.setText(size)

        metadata_text = self._build_stable_diffusion_metadata_text(positive, negative, size)

        src_path = self.current_image_path
        src_ext = os.path.splitext(src_path)[1].lower()
        dst_path = src_path if src_ext == ".png" else self._ensure_unique_png_path(src_path)

        try:
            from PIL import Image, PngImagePlugin

            with Image.open(src_path) as img:
                if img.mode not in ("RGB", "RGBA"):
                    img = img.convert("RGBA")

                pnginfo = PngImagePlugin.PngInfo()
                if src_ext == ".png":
                    existing_info = getattr(img, "info", {}) or {}
                    for key, value in existing_info.items():
                        if not isinstance(value, str):
                            continue
                        if key == "parameters":
                            continue
                        pnginfo.add_text(key, value)

                pnginfo.add_text("parameters", metadata_text)
                img.save(dst_path, format="PNG", pnginfo=pnginfo)

            # Refresh UI / list & reselect
            if dst_path != src_path:
                try:
                    if os.path.exists(src_path):
                        os.remove(src_path)
                except Exception:
                    pass
                folder = os.path.dirname(dst_path)
                self.load_images_from_folder(folder)
                self._select_image_by_path(dst_path)
            else:
                self._load_and_apply_metadata(dst_path)
            self.statusBar().showMessage(f"Đã lưu PNG + metadata: {os.path.basename(dst_path)}")
        except Exception as exc:
            self.statusBar().showMessage(f"Lỗi khi lưu PNG metadata: {exc}")

    def _add_or_select_image_in_list(self, new_path: str):
        # Ensure current folder list includes the new PNG and select it
        folder = os.path.dirname(new_path)
        if not self.folder_path or os.path.normpath(self.folder_path) != os.path.normpath(folder):
            self.folder_path = folder
            self.lbl_folder.setText(folder)
            self.load_images_from_folder(folder)
            self._select_image_by_path(new_path)
            return

        for i in range(self.list_images.count()):
            item = self.list_images.item(i)
            if item and item.data(Qt.UserRole) == new_path:
                self.list_images.setCurrentRow(i)
                self.display_selected_image(item)
                return

        metrics = QFontMetrics(self.list_images.font())
        icon = QIcon(new_path)
        display_name = metrics.elidedText(os.path.basename(new_path), Qt.ElideMiddle, 140)
        item = QListWidgetItem(icon, display_name)
        item.setData(Qt.UserRole, new_path)
        item.setToolTip(os.path.basename(new_path))
        self.list_images.addItem(item)
        self.list_images.setCurrentItem(item)
        self.display_selected_image(item)

    def _select_image_by_path(self, path: str):
        for i in range(self.list_images.count()):
            item = self.list_images.item(i)
            if item and item.data(Qt.UserRole) == path:
                self.list_images.setCurrentRow(i)
                self.display_selected_image(item)
                return

    # ---------- Drag&Drop ----------
    def handle_dropped_images(self, image_paths):
        if not image_paths:
            return

        folder = os.path.dirname(image_paths[0])
        self.folder_path = folder
        self.lbl_folder.setText(folder)

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


        self._apply_image_type_filter()

        for i in range(self.list_images.count()):
            item = self.list_images.item(i)
            if item and not item.isHidden():
                self.list_images.setCurrentRow(i)
                self.display_selected_image(item)
                break
    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key_Right, Qt.Key_D):
            self.navigate_image(1)
        elif key in (Qt.Key_Left, Qt.Key_A):
            self.navigate_image(-1)

    def navigate_image(self, step):
        current_row = self.list_images.currentRow()
        total = self.list_images.count()
        if total <= 0:
            return
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
    except Exception:
        pass
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
